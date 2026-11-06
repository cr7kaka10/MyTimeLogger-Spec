## Why

测试环境 Android 编辑目标的金币奖励后保存显示 `Failed to fetch`，但 PC 与开发环境 Android 正常。客户端目标写操作直接使用 WebView `fetch`，未使用已有的 Android 原生 HTTP 通道；测试环境的本地配置、服务器地址或网络策略也可能参与故障，须先对比两套环境的请求链路，不将本地数据库损坏当成已确认根因。睡眠自动化上传后，页面仅按本机 `phase` 显示“等待 OCR”，排队、重试期间状态不更新。商店补偿说明有错字、旧账户文案不会自动更新；自填金额消费的备注步骤和体重体脂提醒也与当前需求不符。

## What Changes

- 对比测试/开发环境 Android 的本地环境配置、服务器地址、网络请求和服务端日志，再将目标新增、编辑、删除统一接入受保护平台请求通道；正确处理认证失效、网络异常及保存成功后的同步失败。
- 睡眠自动化按真实阶段、失败原因与下次重试时间及时展示进度；服务端任务完成后推进 OCR、报告请求和成功状态，避免旧提示滞留。
- 对照同日期的任务编号与服务端状态验证本次报告，补充 Android 回归验证。
- 修正补偿金币说明中的“不可行力”与“口金币”；按独立段落列明四条使用范围，第五条为举例；同步更新已有账户的固定补偿商品说明。
- “消费”等自填金额商品在确认金额后进入单独的必填备注步骤，提交后在流水中保存备注。
- 停止发送“测量体重体脂”每日通知，并取消已排程的同类通知；保留其他提醒。

## Capabilities

### New Capabilities

- `goal-mutation-transport`: Android 和 PC 目标写操作通过统一平台通道保存，并向用户展示准确结果。
- `compensation-credit-guidance`: 补偿金币的规则说明、既有账户更新及人工补偿边界。
- `contextual-body-reminder`: 取消体重体脂提醒并清理已排程通知。

### Modified Capabilities

- `sleep-analysis-workflow`: 自动化上传后的阶段状态、重试提示及报告完成状态必须与本次任务一致。
- `custom-amount-store-purchases`: 自填金额商品改为金额确认后单独填写必填备注。

## Impact

- 影响 Android 目标页、睡眠自动化、每日通知及 PC/Android 商店；PC 目标页复用共享 hook，需回归。
- 现有模块：`ui/src/hooks/useGoals.ts`、`ui/src/platform/protectedRequest.ts`、`ui/src/components/Sleep/SleepPage.tsx`、Android `SleepAutomationRunnerService`/状态存储/桥接、`server/store.py`、`ui/src/components/Rewards/RewardsPage.tsx`、`ui/src/platform/contextualNotifications.ts`/通知运行时。
- 服务端现有 `/api/goals/{id}`、`/upload`、`/status/{request_id}`、`/generate_report` 不计划改协议；先以同日期、同 request_id 的证据核实具体卡点。
- 排除项：奖励结算算法、OCR 模型、历史报告重算、自动发放启动金币或副业收入金币、其他页面重构。新增两项是现有手动补偿入口的允许用途；收入金额由用户填写备注并自行核对。
- 回滚：撤回客户端提交并重新安装前一 APK；已有账户商品文案如需回退，按变更前文案定向回写并同步。不改变奖励流水与数据库结构。
