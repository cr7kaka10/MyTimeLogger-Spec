## ADDED Requirements

### Requirement: 启动阶段可观测

安卓端 SHALL 记录不含账号隐私的启动阶段耗时，并 SHALL 区分原生显示、数据库就绪、资料恢复及首页可操作。

#### Scenario: 冷启动诊断
- **GIVEN** 安卓应用进程未运行
- **WHEN** 用户打开应用
- **THEN** 诊断日志 SHALL 记录各阶段毫秒耗时与总耗时
- **AND** 日志 MUST NOT 包含 token、密码或个人记录内容

### Requirement: 启动等待有可见反馈

安卓端在必要本地初始化期间 SHALL 显示可读的启动状态；初始化失败 SHALL 显示错误与重试入口。

#### Scenario: 本地数据库初始化中
- **GIVEN** 数据库尚未就绪
- **WHEN** 用户打开应用
- **THEN** 屏幕 SHALL 显示启动状态而非纯白屏

#### Scenario: 初始化失败
- **GIVEN** 数据库初始化失败
- **WHEN** 启动画面显示错误
- **THEN** 用户 SHALL 能重试且不会进入不完整首页

### Requirement: 保存会话快速恢复

本地存在完整账号身份与 token 时，安卓端 SHALL 在必要本地数据就绪后进入首页，网络校验 SHALL 后台运行；只有服务端明确返回无效身份才清理会话。

#### Scenario: 保存会话且网络慢
- **GIVEN** 本地有有效账号身份、token 与缓存数据
- **WHEN** 网络请求仍在进行或超时
- **THEN** 应用 SHALL 展示本地首页且不短暂显示登录页

#### Scenario: 无保存会话
- **GIVEN** 本地无 token
- **WHEN** 启动完成
- **THEN** 应用 SHALL 显示登录页

#### Scenario: 服务端确认失效
- **GIVEN** 本地会话已恢复
- **WHEN** 服务端明确返回身份无效
- **THEN** 应用 SHALL 清理该账号会话并显示登录页

### Requirement: 首屏与后台初始化边界

首屏 SHALL 等待账号库选择、必要数据库迁移与计时恢复；不影响首屏数据正确性的提醒和通知初始化 SHALL 不阻塞首页绘制。

#### Scenario: 旧版数据库升级
- **GIVEN** 本地存在需要兼容迁移的数据库
- **WHEN** 应用升级后启动
- **THEN** 首页 SHALL 在迁移完成后展示且历史数据保持可读

#### Scenario: 首屏后的服务初始化
- **GIVEN** 必要本地数据已就绪
- **WHEN** 提醒或通知初始化耗时
- **THEN** 首页 SHALL 先可操作且这些服务 SHALL 随后正确启用

### Requirement: 冷启动回归验收

性能验收 SHALL 在同设备同账号同数据与网络条件下对比至少五次冷启动；目标为中位数较原始约 20 秒基线下降至少 50%，并报告未达到目标的阶段。

#### Scenario: 实机验收
- **GIVEN** 有基线和修复后各至少五次分段记录
- **WHEN** 对比首页可操作时间
- **THEN** 验证报告 SHALL 给出中位数、最慢一次与每段耗时
- **AND** 未达目标时 SHALL 明确标记未完成
