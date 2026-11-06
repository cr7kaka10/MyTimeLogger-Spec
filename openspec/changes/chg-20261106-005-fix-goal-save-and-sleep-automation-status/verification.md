# 验收记录（2026-11-06，北京时间）

## 已完成的本地验证

- `openspec validate chg-20261106-005-fix-goal-save-and-sleep-automation-status --strict`：valid。
- `python -m pytest tests/unit/test_compensation_credit.py -q`：9 passed；覆盖新账户、旧说明回填、重复补偿与流水。
- `npm run typecheck` 与 `npm run build`：通过。
- `tsx src/platform/contextualNotifications.test.ts`、`notificationRuntime.test.ts`、`sleepAutomation.test.ts`：均通过。
- `node scripts/verify-reward-purchase-steps.mjs`：浏览器实际点击金额→备注；空备注不提交，填写“午餐”后提交 18.5 金币和备注，通过。
- Gradle `:app:testDebugUnitTest` 定向睡眠测试与 `:app:assembleDebug`：退出码 0；调试 APK 已在本机模拟器以 `adb install -r` 安装。
- 模拟器冷启动原文：`Status: ok`、`LaunchState: COLD`、`Activity: com.mytimelogger.app/.MainActivity`、`TotalTime: 1893`、`WaitTime: 1915`、`Complete`；已目视确认首页正常。
- 测试服务 `/ping`：HTTP 200。`git diff --check`：通过。代码提交 `6db623a6`。
- 继续部署前已在测试机手动运行现有备份脚本：`app-2026-11-06-222740.db` 的 SQLite `integrity=ok`，`s3_upload=ok`，`s3_verify=ok`；脚本退出码 0。备份不切换服务。

## 尚未完成的现场验收

- `adb devices` 仅见 `emulator-5554`；老板明确回复“暂不连接”截图所用 Android 手机。因此无法读取该手机测试/开发环境 URL、目标 PUT 日志、睡眠本次 request_id 或验证修复在该手机上的结果。不能把本地数据库损坏或 WebView 网络策略认定为最终根因。
- 本次睡眠任务的 OCR→报告推进、目标编辑后重开数值、08:40 体重体脂通知的升级设备实测，均待截图手机连接后验证；旧报告不能代替本次成功证据。
- 服务端改动尚未部署到测试机；测试机当前 HTTP 200 仅证明现有服务可达，不代表新补偿文案已上线。现有 Android 模拟器安装的是本地调试 APK，截图手机仍是其原安装版本。
- 测试机 SSH 只读连接正常；本机 Docker Desktop 后台启动未成功，Linux Engine 命名管道不存在，现有部署脚本需要本机 Docker 构建镜像。已请老板手动启动 Docker Desktop；在引擎和备份条件都满足前不切换现有容器。
