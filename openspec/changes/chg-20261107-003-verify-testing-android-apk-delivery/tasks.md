## 1. 当前源码构建

- [ ] 1.1 调整 `deploy-test.bat` 的 [1] 顺序，使 Android 构建先于桌面打包，打印本地 Git 修订、改动标记和北京时间；DoD：桌面阶段开始前已有本次 APK 结果。（≤1 文件/≤50 行）
- [ ] 1.2 调整 `build-android.ps1` 固定产物的清理与本次构建核验，输出 APK 路径和 SHA256；DoD：构建失败不会遗留被报为新包的旧 APK。（≤1 文件/≤50 行）

## 2. 版本 2.0

- [ ] 2.1 同步 `desktop/package.json` 与 `desktop/package-lock.json` 根版本为 `2.0.0`；DoD：桌面打包产物名称和应用版本为 2.0.0。（≤2 文件/≤50 行）
- [ ] 2.2 设置 `ui/android/app/build.gradle` 的 `versionName=2.0`、`versionCode=2`；DoD：APK 元数据为 2.0/code 2。（≤1 文件/≤50 行）

## 3. 定向核对

- [ ] 3.1 只核对部署菜单流程、打包版本、APK 本次时间/哈希及 OpenSpec strict；DoD：日志可区分本次构建与手机安装状态，不扩展设备测试。（≤3 文件/≤50 行）
