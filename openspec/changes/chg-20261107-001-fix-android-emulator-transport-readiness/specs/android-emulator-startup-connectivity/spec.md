## ADDED Requirements

### Requirement: 目标模拟器传输就绪判定
启动脚本 MUST 在目标 AVD 进程身份已确认、ADB 将目标序列号报告为 `device` 且系统稳定时继续启动，不得仅因 Windows TCP 连接的 `State` 为空而报告传输不可用。

#### Scenario: 端口存在但 State 为空
- **GIVEN** 5554/5555 由目标 QEMU 进程持有，PowerShell 返回空 `State`
- **WHEN** ADB 显示 `emulator-5554 device` 且系统稳定
- **THEN** 脚本继续构建、安装和启动阶段，不报 `adb_transport_unavailable`

#### Scenario: 目标 ADB 未连接
- **GIVEN** 目标进程存在但 `emulator-5554` 未处于 `device`
- **WHEN** 传输等待到期
- **THEN** 脚本执行限定目标的恢复并在仍失败时给出准确诊断

### Requirement: 本机服务转发先于应用启动
启动脚本 MUST 在报告 Android 就绪前配置并核验目标模拟器的 `tcp:8000 → tcp:8000` reverse；发生 ADB 重连后 MUST 再次核验。

#### Scenario: 正常启动
- **GIVEN** 本机服务 `/ping` 可访问
- **WHEN** 脚本准备启动 MainActivity
- **THEN** 目标模拟器的 reverse 列表包含 `tcp:8000 tcp:8000`，然后启动应用

#### Scenario: 传输重连后转发丢失
- **GIVEN** 先前建立的 reverse 因重连消失
- **WHEN** 脚本继续或恢复应用启动
- **THEN** 脚本重建并核验转发，不把旧的“已同步”显示作为本次连通的证据
