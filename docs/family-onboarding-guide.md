# MyTimeLogger 家人首次使用教程

更新时间：2026-07-04（UTC+8）

## 1. 安装和打开

1. 安装部署者提供的桌面客户端。
2. 打开 MyTimeLogger。
3. 首次进入会先看到登录/注册页。
4. 已有账号就登录；没有账号就注册一个自己的账号。

注册名会参与备份路径隔离，请使用稳定、容易识别的名字，例如 `mom`、`dad`、`alice`。

## 2. 登录后可以直接使用的功能

登录成功后可以直接使用：

- 计时
- 时间书
- 学习记录
- 清单本地视图
- 运动记录
- 睡眠记录
- 多端同步到 MyTimeLogger 服务端

这些基础功能不要求你先配置 TickTick、ATIMELOGGER 或 AI API Key。

## 3. 哪些配置是家庭共享的

部署者会在服务端预先配置家庭共享能力：

- S3 容灾备份
- 文本/视觉 AI 模型

这些密钥只保存在服务端。客户端只显示“已启用/未启用”和连接状态，不显示也不保存 S3 access key、S3 secret、AI API Key。

## 4. S3 共享备份路径规则

S3 是共享桶和共享密钥，但路径必须按用户隔离。

标准路径模板：

```text
<environment><local-path><backup-type>/...
```

示例：

```text
testing/users/mom-2/sqlite/mtl_server_20260704_220000.db.gz
testing/users/mom-2/reports/2026-07-04-report.html
testing/users/dad-3/sqlite/mtl_server_20260704_230000.db.gz
```

说明：

- `<environment>` 是 `development`、`testing` 或 `production`。
- `<registered-username>` 是注册账号名。
- `<user-id>` 是服务端数据库里的用户 ID，用来避免同名冲突。
- `<backup-type>` 通常是 `sqlite` 或 `reports`。
- 家人账号不能使用部署者自己的旧备份路径，例如只写 `sqlite/` 或 `reports/`。

## 5. 哪些配置需要每个人自己绑定

以下能力属于个人外部账号，不能复用部署者账号：

- 滴答清单 / TickTick
- ATIMELOGGER

原因很简单：这两个服务里是每个人自己的清单和时间记录。复用部署者 token 会造成数据串号。

## 6. 绑定滴答清单

1. 打开 MyTimeLogger 设置页。
2. 查看“服务端集成状态”里的“滴答清单”。
3. 如果显示“当前用户未绑定”，按部署者提供的方式获取自己的 TickTick token 或登录授权信息。
4. 提交到服务端个人绑定接口后，状态会变成“个人已绑定”。

未绑定时：

- 本地清单仍可使用。
- 不会自动读取部署者或其他家人的 TickTick 数据。
- 同步会返回“当前用户未绑定”类诊断。

## 7. 绑定 ATIMELOGGER

1. 打开 MyTimeLogger 设置页。
2. 查看“个人绑定”里的 ATIMELOGGER 状态。
3. 使用自己的 ATIMELOGGER 账号或 token 完成绑定。
4. 绑定后，计时备份才会同步到自己的 ATIMELOGGER。

未绑定时：

- 本地计时功能不受影响。
- 客户端不会保存 ATIMELOGGER 密码、token 或 refresh token。
- 服务端不会使用部署者或其他用户的 ATIMELOGGER 凭据。

## 8. AI 能力怎么用

AI API Key 由部署者配置在服务端。

家人用户可以直接使用服务端开放的 AI 能力；客户端不会要求填写 API Key，也不会在配置导出文件里带出 API Key。

## 9. 隐私边界

- 每个 MyTimeLogger 账号有自己的用户 ID。
- TickTick 和 ATIMELOGGER 绑定按用户 ID 保存。
- S3 共享备份按注册名和用户 ID 分路径。
- 客户端导出的配置不包含第三方密钥和服务端登录 token。
- 部署者仍然拥有服务器和数据库管理权限；如果需要更强隔离，后续应引入家庭成员权限模型和独立存储桶。

## 10. 常见问题

**登录后提示滴答清单未绑定，是不是配置丢了？**

不是。滴答清单是个人绑定，每个用户都要绑定自己的账号。服务端不会把部署者 token 自动给家人使用。

**我不配置 TickTick 能用吗？**

能。只有 TickTick 同步不可用，本地清单和其他功能仍可用。

**我不配置 ATIMELOGGER 能用计时吗？**

能。计时数据先保存在 MyTimeLogger，本地功能不依赖 ATIMELOGGER。

**S3 是共享的，会不会覆盖别人的备份？**

不会。路径必须按 `<registered-username>-<user-id>` 分目录。部署和测试时要检查状态页里的路径模板。

**导出配置能发给别人吗？**

可以作为偏好配置参考。导出文件不会包含服务端 token、ATIMELOGGER 密码/token、AI API Key 或 S3 secret。
