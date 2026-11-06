## ADDED Requirements

### Requirement: 目标模拟器传输端口识别

Android 本地启动脚本 SHALL 在 Windows 连接记录缺少 `State` 时，以监听端口的进程归属和 ADB 身份判断目标 AVD 是否就绪。

#### Scenario: 监听状态为空但目标正常
- **GIVEN** 目标 QEMU 拥有 5554 与 5555，两个监听记录的 `State` 为空
- **WHEN** ADB serial 和 AVD 名称均匹配目标
- **THEN** 脚本 SHALL 进入系统就绪和 APK 启动步骤，不触发传输恢复

#### Scenario: 其他模拟器占用端口
- **GIVEN** 5554 或 5555 的监听 PID 不属于目标 QEMU
- **WHEN** 脚本检查目标传输
- **THEN** 脚本 SHALL 拒绝将该端口标记为目标可用，且不得终止未知进程

#### Scenario: 端口或 ADB 身份缺失
- **GIVEN** 任一端口无目标监听，或 ADB 报告的 AVD 名称不符
- **WHEN** 脚本等待目标启动
- **THEN** 脚本 SHALL 沿用有限等待与恢复，并在失败时给出非零退出码和诊断
