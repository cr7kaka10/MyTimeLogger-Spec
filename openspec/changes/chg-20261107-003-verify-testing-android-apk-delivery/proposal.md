## Why

当前测试部署的“全部部署”先打桌面包，桌面打包停滞会挡住 Android APK；桌面包和 Android 包仍标为 1.0/1.0.0，难以判断手机拿到的是哪次代码。用户要求每次运行 `deploy-test.bat` 均从当前本地源码生成最新测试产物，并统一显示 2.0 版。

## What Changes

- “全部部署”在桌面打包前构建 Android APK；构建失败立即报错，不把旧产物当作本次产物。
- 对本次 APK 和桌面包显示源码 Git 修订、工作树是否有未提交改动、构建时间及产物路径；明确本地 APK 生成不等于手机已安装。
- 将桌面应用版本改为 `2.0.0`、Android `versionName` 改为 `2.0` 并递增 `versionCode`，保证可覆盖旧版。
- 排除项：不自动拉取或重置远端代码，不自动向手机安装 APK，不修改选餐转盘业务，不扩展额外设备测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `deployment`：测试部署产物必须来自本次本地源码构建，版本号和构建来源可核对。

## Impact

- Android：`deploy/deploy-test.bat`、`deploy/build-android.ps1`、`ui/android/app/build.gradle`；桌面：`desktop/package.json`、`desktop/package-lock.json`；服务端部署顺序不变。
- 回滚：回退部署脚本及版本文件即可恢复原打包方式；不涉及数据库迁移或手机数据删除。
