# 验收记录（2026-11-06，北京时间）

## 已完成的验证与部署

- `openspec validate chg-20261106-005-fix-goal-save-and-sleep-automation-status --strict`：valid。
- `python -m pytest tests/unit/test_compensation_credit.py -q`：9 passed；覆盖新账户、旧说明回填、重复补偿与流水。
- `npm run typecheck` 与 `npm run build`：通过。
- `tsx src/platform/contextualNotifications.test.ts`、`notificationRuntime.test.ts`、`sleepAutomation.test.ts`：均通过。
- `node scripts/verify-reward-purchase-steps.mjs`：浏览器实际点击金额→备注；空备注不提交，填写“午餐”后提交 18.5 金币和备注，通过。
- Gradle `:app:testDebugUnitTest` 定向睡眠测试与 `:app:assembleDebug`：退出码 0；调试 APK 已在本机模拟器以 `adb install -r` 安装。
- 模拟器冷启动原文：`Status: ok`、`LaunchState: COLD`、`Activity: com.mytimelogger.app/.MainActivity`、`TotalTime: 1893`、`WaitTime: 1915`、`Complete`；已目视确认首页正常。
- 测试服务 `/ping`：HTTP 200。`git diff --check`：通过。代码提交 `6db623a6`。
- 继续部署前已在测试机手动运行现有备份脚本：`app-2026-11-06-222740.db` 的 SQLite `integrity=ok`，`s3_upload=ok`，`s3_verify=ok`；脚本退出码 0。备份不切换服务。
- 老板手动启动 Docker Desktop 后，Engine 29.2.1 可用。修正安全预检触发的测试夹具绝对路径，原测试通过，`deploy/security-preflight.ps1 -Environment testing` 返回 `[OK] Security preflight passed.`；修复提交 `478edd81`。
- 测试机旧镜像 `sha256:ba63fecc05aaa8f00602dbb6a375263a159085d334ba19feb26f5bbde889e1c6` 已保留为 `mytimelogger-server:before-chg-20261106-005`。新镜像归档 SHA256 `fc498a20a4a12a7c204dc40842a98e5dc620a286a2c8504615bbd65bc0bde1d9`，上传前后相同；`remote_deploy.sh` 退出码 0。
- 测试机新容器 `mytimelogger-sleep-server` 运行中，镜像 ID `sha256:f8e76eeb69616185908716dff0b18c27fd5b2294c7fd02bc3cb0d4ebcb3ee91c`；外网 `/ping=200`、`/docs=200`，SQLite `integrity_check=ok`。容器代码含四条范围、第五条例子及“扣金币”修正；调用现有商品列表逻辑后，2 个账户的 2 条固定补偿商品说明均与新文案一致。

## 尚未完成的现场验收

- `adb devices` 仅见 `emulator-5554`；老板明确回复“暂不连接”截图所用 Android 手机。因此无法读取该手机测试/开发环境 URL、目标 PUT 日志、睡眠本次 request_id 或验证修复在该手机上的结果。不能把本地数据库损坏或 WebView 网络策略认定为最终根因。
- 本次睡眠任务的 OCR→报告推进、目标编辑后重开数值、08:40 体重体脂通知的升级设备实测，均待截图手机连接后验证；旧报告不能代替本次成功证据。
- 测试机服务端已部署并确认固定补偿商品回填。现有 Android 模拟器安装的是本地调试 APK，截图手机仍是其原安装版本；客户端目标保存、睡眠状态和通知修复不能由服务端上线代替验收。
