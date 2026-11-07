## ADDED Requirements

### Requirement: 本地启动准确识别服务端端口归属

一键启动 SHALL 根据实际绑定能力判断 8000 是否空闲；占用时 MUST 只重启当前工作区的 FastAPI 进程，未知进程 MUST NOT 被终止。

#### Scenario: 重复启动当前项目
- **GIVEN** 当前工作区的 FastAPI 已占用 8000，且 TCP 记录的 `State` 为空
- **WHEN** 用户再次运行 `start-all.bat`
- **THEN** 启动器 SHALL 识别旧进程、只停止该项目进程并启动新进程
- **AND** 最终 `/ping` SHALL 返回当前构建版本且就绪检查通过

#### Scenario: 未知进程占用
- **GIVEN** 8000 被命令行或工作目录不属于当前项目的进程占用
- **WHEN** 用户运行 `start-all.bat`
- **THEN** 启动器 SHALL 报告端口和 PID，MUST NOT 终止该进程

#### Scenario: 端口被系统排除但无可识别进程
- **GIVEN** 绑定 8000 失败且无法确认本项目占用进程
- **WHEN** 启动器检查端口
- **THEN** 启动器 SHALL 拒绝启动并明确报告端口不可用

### Requirement: 就绪预检与端口绑定结果一致

`-RequirePortsFree` 预检 SHALL 对目标地址实际试绑，MUST NOT 仅依赖 TCP 记录的 `State` 字段。

#### Scenario: 状态字段缺失
- **GIVEN** 8000 已被占用，但 `Get-NetTCPConnection` 的 `State` 为空
- **WHEN** 运行空闲端口预检
- **THEN** 预检 SHALL 判定端口不可用
