## Why

`start-all.bat` 的服务端端口误判修复后，Android 阶段仍在 `transport_wait` 失败。目标 AVD 已启动、`adb devices` 和 `sys.boot_completed=1` 均正常，但 `start-android-dev.ps1` 用 `Get-NetTCPConnection -State Listen` 判断 5554/5555；本机监听记录的 `State` 为空，被误判为两个端口都不存在。

## What Changes

- Android 启动脚本改用不依赖 `State` 字段的端口归属判断，结合目标 AVD 运行进程和 ADB 身份确认，仅在真实不可用时进入传输恢复。
- 增加 PowerShell 回归：监听 `State` 为空、目标 AVD 正常、其他进程占用和端口缺失；连续运行一键启动验证自动安装与输入就绪。
- 排除项：不改 Android App/服务端业务逻辑、APK 权限、模拟器镜像或真实设备配置，不终止未知进程。
- 回滚方案：恢复 `start-android-dev.ps1` 的端口探测与对应测试；保留已运行的服务和 APK。

## Capabilities

### New Capabilities

- `android-startup-transport-detection`: 一键启动在 Windows 监听状态缺失时仍准确识别目标模拟器 ADB 传输。

### Modified Capabilities

无。

## Impact

- 只影响本地 `scripts/start-android-dev.ps1`、其 PowerShell 测试和启动验证记录；`start-all.bat` 的 PC、服务端及 Android 自动联调受益。
- 当前已手动在目标 `aTimeLogger_Extraction_API35` 安装最新 APK 并运行，首页显示“已同步”；此提案解决后续自动启动失败。
