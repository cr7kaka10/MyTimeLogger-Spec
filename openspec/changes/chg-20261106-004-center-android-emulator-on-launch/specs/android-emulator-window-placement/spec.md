## ADDED Requirements

### Requirement: 启动目标模拟器时立即居中

本地 Android 启动流程 SHALL 在核实目标模拟器进程且其 GUI 窗口出现后、等待设备启动完成前，将目标窗口完整放入当前屏幕工作区中央。

#### Scenario: 冷启动目标 AVD
- **GIVEN** 目标 AVD 的 QEMU 进程已启动，窗口位置部分位于屏幕外
- **WHEN** GUI 窗口句柄出现
- **THEN** 启动流程 SHALL 在进入 ADB/系统就绪等待前将该窗口居中并置于前台

#### Scenario: 复用已运行的目标 AVD
- **GIVEN** 目标 AVD 已运行，但窗口停在屏幕外
- **WHEN** 用户再次运行本地启动流程
- **THEN** 启动流程 SHALL 立即把该目标窗口移至工作区中央

#### Scenario: 后续设备检查失败
- **GIVEN** 目标 AVD 窗口可显示，但后续 ADB 或系统就绪检查失败
- **WHEN** 启动流程报告失败
- **THEN** 已执行的居中 SHALL 不依赖检查成功，且错误摘要 SHALL 保留实际失败原因

#### Scenario: 目标 GUI 窗口未出现
- **GIVEN** 已核实的目标 QEMU 在有界等待期间没有 GUI 句柄
- **WHEN** 定位重试结束
- **THEN** 启动流程 SHALL 记录窗口不可用的诊断，且不得移动其他进程的窗口
