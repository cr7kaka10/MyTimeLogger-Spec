## Why

Android 编辑目标的金币奖励后保存显示 `Failed to fetch`。客户端目标写操作直接使用 WebView `fetch`，没有采用项目已有的 Android 原生 HTTP 通道；服务端已有对应 PUT 路由，因此最新服务端代码并不能解决这条客户端请求链路。睡眠自动化上传后，页面仅按本机 `phase` 显示“等待 OCR”，排队、重试期间状态不更新，用户无法判断 OCR、报告请求和最终结果；截图中的既有报告不等于本次任务已完成。

## What Changes

- 目标新增、编辑、删除统一使用已存在的受保护平台请求通道，正确处理认证失效、网络异常及保存成功后的同步失败。
- 睡眠自动化按真实阶段、失败原因与下次重试时间及时展示进度；服务端任务完成后推进 OCR、报告请求和成功状态，避免旧提示滞留。
- 对照同日期的任务编号与服务端状态验证本次报告，补充 Android 回归验证。

## Capabilities

### New Capabilities

- `goal-mutation-transport`: Android 和 PC 目标写操作通过统一平台通道保存，并向用户展示准确结果。

### Modified Capabilities

- `sleep-analysis-workflow`: 自动化上传后的阶段状态、重试提示及报告完成状态必须与本次任务一致。

## Impact

- 影响 Android 目标页、Android 睡眠自动化、共享 UI 请求层；PC 目标页复用共享 hook，需回归。
- 现有模块：`ui/src/hooks/useGoals.ts`、`ui/src/platform/protectedRequest.ts`、`ui/src/components/Sleep/SleepPage.tsx`、Android `SleepAutomationRunnerService`/状态存储/桥接。
- 服务端现有 `/api/goals/{id}`、`/upload`、`/status/{request_id}`、`/generate_report` 不计划改协议；先以同日期、同 request_id 的证据核实具体卡点。
- 排除项：奖励结算算法、OCR 模型、历史报告重算、服务器重新部署及其他页面重构。
- 回滚：撤回本变更的客户端提交并重新安装前一 APK；服务端及持久化格式不变。
