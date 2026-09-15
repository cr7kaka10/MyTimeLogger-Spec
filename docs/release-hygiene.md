# 发布卫生基线（011）

- 审计时间：2026-07-12 10:07:12（北京时间，UTC+8）
- 分支：`dev`；HEAD：`30061fb5de388a548298bdf13ac4fa570f51c73b`
- 远端基线：`origin/dev` = `53557330448932134d72686808ec9c5334e87d3b`；本地领先 31 个提交。
- 快照：1702 个 tracked 路径、32 个改动、41 个 untracked 路径；清单只记录路径角色，不读取个人正文。

## 文件分类与精确边界

| 分类 | 路径 | 处置 |
|---|---|---|
| 必须跟踪 | 源码、lockfile、无秘密 `*.example.*`、OpenSpec | scoped 提交 |
| 仅本机保留 | `server/attachments/`、`server/reports/`、`.codegraph/`、私有配置源 | 不复制、不自动删除 |
| 可重建 | `server/log/`、`server/scratch/`、`tests/runtime/`、构建/依赖缓存 | 清理后按需重建 |
| 确认后删除 | `server/data/mtl_server.db*`、`server/mtl_server.db*`、`server/server/data/mtl_server.db*`、`desktop/local_data/`、旧 backup/state/restore candidates | 仅在精确停服和 provider 导出后删除 |
| 禁止发布 | DB/WAL/SHM、`assets/tmp/`、日志/报告、真实配置、附件、个人账号/地址/绝对路径 | 预检命中即阻断 |

- 010 保留项：`ui/public/my_time_logger.db` 本轮不删除，但不得进入 011 发布对象。
- 私有迁移源：根 `config.json`、`server/.env`、`deploy/config.local.env` 暂存本机；仅在 E2E、Docker 和 provider 导入均通过后删除。

## 配置消费者矩阵（不显示值）

| 来源 | 消费者/角色 | fresh clone |
|---|---|---|
| 根 `config.json` | 报告技能旧兼容输入 | 不复制；基础启动不需要 |
| `server/config.json` | `ConfigManager` 的 `runtime/security/cors` | 不复制；缺失自动生成 |
| `server/.env` | Compose 迁移期私有环境 | 不复制；基础 Compose 不强制 |
| 用户 provider-binding | 当前用户 TickTick/S3/AI 权威存储 | 登录后导入 |
| `deploy/config.local.env` | 本机部署目标/SSH/端口 | 不复制；保持 ignored |
| `server/data/*_config.json`、`*_state.json` | provider/备份运行状态 | 不复制；可重建或迁移后删除 |
| `desktop/local_data/` | 客户端 DB、登录态、窗口状态和日志 | 不复制；首次启动创建 |

迁移状态：TickTick=`configured`、S3=`configured`、AI=`configured`；三类旧私有来源均已由当前用户 provider-binding 覆盖，未输出字段值。

## fresh-clone 隔离规则

1. 只从候选提交执行 `git archive` 或真正 fresh clone；禁止复制当前工作目录。
2. 归档前 `git ls-files -ci --exclude-standard` 必须无输出；否则 tracked-but-ignored 阻断。
3. 隔离副本必须不存在根/服务端 `config.json`、`server/.env`、新旧部署 local env、provider state、`desktop/local_data/`、附件、日志、DB 和 `node_modules/`。
4. Docker context 只放行 `server/` 源码；`.dockerignore` 对上述私有/运行路径再次拒绝。
