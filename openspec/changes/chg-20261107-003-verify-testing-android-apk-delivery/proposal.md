## Why

图 1 的手机没有选餐转盘 🎡 及“转盘设置”，但本机 2026-11-07 10:33 生成的 APK 内含这两个入口。`deploy-test.bat` 的“全部部署”先打包桌面 EXE，桌面步骤卡住时 Android 步骤尚未运行；Android 脚本即使成功也只生成 APK，不会更新手机，因此“本机已构建”和“手机已安装”被误认为同一状态。

## What Changes

- “全部部署”先完成 Android APK 构建，再进入桌面 EXE 打包；各产物分别报告成功、失败或未执行，不能把 APK 已生成表述为手机已更新。
- Android 构建后显示 APK 路径、构建版本和校验值；仅在唯一 ADB 目标且用户选择安装时执行覆盖安装并核验结果。无设备或多个设备时明确提示待安装及人工安装路径。
- 用同一构建产物验证手机上 🎡 和设置中的“转盘设置”；记录实际安装设备与版本。当前 `adb devices` 为空，实机验收须待手机接入或用户手工安装。
- 排除项：不修改转盘业务与同步逻辑、不改服务端发布内容、不卸载 App 或清除手机数据、不自动选择多个 ADB 目标。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `deployment`：测试部署须区分 Android APK 构建与设备安装，报告可核验的版本和产物状态；桌面打包停滞不能使 Android 产物始终缺席。

## Impact

- 影响现有模块：`deploy/deploy-test.bat`、`deploy/build-android.ps1` 及其定向验证；Android 手机安装与桌面打包流程。PC 和 Android 业务代码、服务端 API 不变。
- 回滚：回退部署脚本提交，恢复原顺序及仅生成 APK 的行为；不涉及数据库迁移。
