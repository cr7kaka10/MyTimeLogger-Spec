# S3 SQLite 容灾备份与恢复

## 备份方式

服务端启用 S3 容灾备份后，会按设置页配置的间隔生成 SQLite 一致性快照，压缩为 `.db.gz` 后上传到 S3 兼容对象存储，同时上传同名 manifest。manifest 记录文件大小、sha256、生成时间和表清单。

备份文件是可直接恢复的 SQLite 数据库快照，不是 MySQL 镜像表。

S3 endpoint、bucket、access key、secret key 和 AI API Key 属于部署级共享配置；账号级配置只记录 owner、路径来源、启用状态等元数据。默认 owner 不在仓库中公开。所有新写入对象使用最新账号级路径：

```text
<environment>/users/<registered-username>-<user-id>/<backup-type>/...
```

旧的 `database_prefix`、`sqlite_prefix`、`reports_prefix` 只作为兼容读取或界面展示来源，不再作为新写入目标。

## 恢复步骤

1. 停止服务端，避免恢复期间继续写入。
2. 从 S3 对象存储下载目标 `.db.gz` 和同名 `.manifest.json`。
3. 备份当前主库，例如 `server/data/mtl_server.db`。
4. 运行校验和解压：

```powershell
python server/restore_s3_snapshot.py --snapshot .\mtl_server_20260626_120000.db.gz --manifest .\mtl_server_20260626_120000.db.gz.manifest.json --output server/data/mtl_server.restored.db
```

5. 脚本成功后，人工确认快照时间点，再将 `mtl_server.restored.db` 替换为正式 `server/data/mtl_server.db`。
6. 启动服务端并检查 `/ping`、客户端同步和最近数据。

## 回滚

如果恢复后的数据不符合预期，停止服务端，把第 3 步备份的原 SQLite 文件放回原路径，再启动服务端。
