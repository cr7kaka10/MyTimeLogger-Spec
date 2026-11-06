## Why

2026-11-07 00:19 的一键启动中，目标模拟器已运行、ADB 最终可识别，5554/5555 由目标 QEMU 进程占用，但 `start-android-dev.ps1` 的 `Get-NetTCPConnection -State Listen` 返回空，误报端口缺失并在 `transport_wait` 退出。退出发生在 APK 安装和 `adb reverse tcp:8000` 前；ADB 后续重连还会清除手动转发，使安卓 App 无法稳定访问本机服务。

## What Changes

- Android 启动就绪以目标 AVD 进程身份、ADB 目标序列号及系统就绪结果为准，不再把 Windows TCP `State=Listen` 当作必要条件；保留端口诊断，但不得误报成功的 ADB 连接。
- 在安装和启动 App 前配置并核验 `tcp:8000 → tcp:8000` 转发；若启动期间目标传输重连，重新核验转发后才报告就绪。
- 用故障样例和目标模拟器验证启动流程可完成 Web 构建、APK 安装、转发和 App 前台启动，并记录服务端 `/ping` 与实际客户端同步状态。
- 排除项：不修改学习 OKR 业务逻辑、服务端 API、实体手机的网络配置，也不处理其他 AVD。

## Capabilities

### New Capabilities

- `android-emulator-startup-connectivity`：目标模拟器的启动就绪与本机服务连接验证。

### Modified Capabilities

无。

## Impact

- 影响 Android 本地开发启动脚本 `scripts/start-android-dev.ps1` 和定向启动回归；PC 客户端与服务端代码不变。
- 现有模块：目标 AVD 身份检测、ADB 传输恢复、Android Web 构建/安装、HTTP reverse 和启动摘要。
- 回滚方案：回退脚本与测试提交，恢复旧启动判定；不涉及数据库或客户端数据迁移。
