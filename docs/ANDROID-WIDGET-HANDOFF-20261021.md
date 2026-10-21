# Android 今日清单小组件：跨机器交接（北京时间 2026-10-21）

## 当前结论

- 功能开发已完成，代码在 `dev`：`f53e4264` 新增今日清单桌面小组件；`d8168d18` 修复 `start-all.bat` 的安卓日志占用和旧版 ADB 冲突。计时小组件保留。没有待提交的功能代码。
- 今日清单显示今天的习惯、今天及已过期的清单任务；列表可上下滑动，勾选可完成。按需求没有添加任务框。
- 已通过习惯日期投影测试 6 assertions、Android JVM 测试 4/4、TypeScript typecheck 和 Debug APK 构建。2026-10-20 曾在隔离 API 35 AVD `CodexWidgetSmoke_API35` 实机验证两个小组件、滑动、任务/习惯勾选、冷启动、窄尺寸和空态。
- `start-all.bat` 的 PC、FastAPI、Vite 可启动。安卓 Debug APK 曾成功安装，HTTP reverse 与 `MainActivity` 曾启动，但笔记本上的最终可交互检查没有通过；最新完整重跑停在 `boot_wait`：`System UI / Pixel Launcher` 无响应，稳定样本 0/2。目标 AVD 和隔离 AVD 后来都出现系统 ANR，暂不能据此判定应用代码有故障。未清除 AVD 用户数据。

## 台式机接手

1. 获取 `dev` 分支的最新提交；此文档所在提交也必须同步。笔记本原有 `.vite/vitest/results.json` 是未提交改动，未纳入交接。
2. 配置 Android SDK（`ANDROID_SDK_ROOT` 或 `ANDROID_HOME`）、JDK 21（`JAVA_HOME`）。启动脚本要求 API 35 AVD 名为 `aTimeLogger_Extraction_API35`，目标序列号 `emulator-5554`；SDK ADB 单独使用端口 `5038`。
3. 在 PowerShell 中运行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-android-dev.ps1 -PreflightOnly`，随后运行 `start-all.bat`。真正完成的标准是安卓摘要 `success/input_ready`、前台 `com.mytimelogger.app/.MainActivity` 有可见 Surface、输入可用。
4. 如需复测代码，运行 `python -m pytest tests/unit/test_start_all_android_emulator.py -q` 和 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-all.contract.test.ps1`。APK 产物 `deploy/artifacts/MyTimeLogger-debug.apk` 未跟踪，台式机需重新构建。
5. 若台式机仍遇系统 ANR，先看 `tests/runtime/startup-logs/android-*.summary.json` 的最新摘要，并检查目标 AVD 本身是否能稳定显示 Launcher。不要把 `boot_completed=1` 或 Activity 前台单独当作应用可用；也不要用清除用户数据来跳过诊断。

## 笔记本上的验证证据

- `tests/runtime/start-all-android-fix-validation3.log`：APK 安装 `Success`，随后 `failed/activity_readiness`，App 前台但 Surface 不可见。
- `tests/runtime/start-all-avd-anr-validation.log` 与 `tests/runtime/startup-logs/android-20261020-234326.summary.json`：最新原入口重跑为 `failed/boot_wait`，System UI / Launcher ANR。
- `openspec/changes/chg-20261020-001-新增安卓今日清单桌面小组件/verification.md`、`chg-20261020-002-修复安卓启动日志争用/verification.md`、`chg-20261020-003-恢复安卓模拟器界面稳定性/verification.md` 存在于笔记本本地；`openspec/` 和 `tests/runtime/` 被 Git 忽略，不会随普通提交传输。
- 原目标 AVD 在 `-gpu host` 冷启动后仍 ANR；隔离 AVD 在笔记本后续冷启动也出现 System UI ANR，之后两台 AVD 均已停止。当前没有从这个实验得到有效的脚本参数，因此未把 `-gpu host` 固化进代码。

另有独立的 V5 运动计划登录态视觉验收断点；它与本次 Android 小组件代码无关。
