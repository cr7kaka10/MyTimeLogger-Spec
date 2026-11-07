## ADDED Requirements

### Requirement: 测试部署使用当前本地源码并标明 2.0 版

`deploy-test.bat` SHALL 在每次被选择的客户端部署阶段重新构建当前本地工作树，标明 Git 修订及未提交改动状态。Android APK 和桌面 EXE SHALL 分别标为 2.0 和 2.0.0；Android `versionCode` SHALL 大于现有值 1。构建失败 SHALL 不得将旧产物报告为本次产物。

#### Scenario: 全部部署时桌面打包停滞

- **GIVEN** 用户选择 [1] 且服务端阶段成功
- **WHEN** 桌面打包阶段开始
- **THEN** Android 已从当前工作树完成本次构建，日志可核对 APK 路径、修订与 SHA256

#### Scenario: 本次 Android 构建失败

- **GIVEN** 固定产物路径存在上次 APK
- **WHEN** 本次 Android 构建失败
- **THEN** 部署任务失败且不宣称上次 APK 是本次的新包

#### Scenario: 版本和安装状态

- **GIVEN** 客户端构建成功
- **WHEN** 用户读取构建日志及产物元数据
- **THEN** 桌面显示 2.0.0，Android 显示 2.0/code 2，日志仅宣称 APK 已构建而不宣称手机已安装
