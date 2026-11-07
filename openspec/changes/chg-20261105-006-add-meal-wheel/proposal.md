## Why

每天选餐缺少快速决策入口。老板指定在截图顶部快捷操作区加入选餐转盘，并要求设置可编辑候选及概率，且 PC 与安卓看到同一份配置。

## What Changes

- 在顶部快捷操作区加入“选餐转盘”图标；点击后打开主题适配的转盘面板，旋转结束显示结果，可再次抽取。
- 设置页加入“转盘设置”，支持候选餐名的新增、改名、删除、排序及权重编辑；显示各项实际概率并校验总配置有效。
- 配置按账号通过现有 `system_config` 双向同步链路传播；离线可用本地配置，重连后收敛，多设备编辑按既有服务端版本仲裁；登出或切账号不串数据。
- 抽取使用权重随机选择，动画只展示已选结果；默认候选为可编辑示例，不与金币、奖励或真实抽奖交易关联。

## Capabilities

### New Capabilities

- `meal-wheel`: 选餐转盘、权重概率、配置编辑及多端一致性。

### Modified Capabilities

- `page-quick-actions`: 顶部快捷操作增加选餐转盘入口并维持窄屏可用。

## Impact

- **PC 与安卓端**：`ui/src/components/common/PageQuickActions.tsx`、`ui/src/pages/MainLayout.tsx`、`ui/src/App.tsx`、`ui/src/components/Settings/SettingsPage.tsx`，新增转盘组件及纯逻辑模块；`core/models/Database.ts` 已有 `system_config` 入队能力，优先复用。
- **服务端**：复用 `server_system_config` 和现有同步接口，实施前核实新 key 可推拉且不被设备本地配置过滤；若现有过滤阻止同步，另列最小兼容改动。
- **UI 规范说明**：参考现有 `PageQuickActions` 和 `LedgerSheet`；已读 `fluent-ui-guide/spec.md`，其中 PyQt6 窗口条款与当前 React/Electron/Capacitor 实现不符，采用现有主题类；新独立窗口：否，使用主界面内面板。
- **排除项**：不扣金币、不发奖、不记录可兑换奖品、不接第三方抽奖服务、不自动创建餐食/计时记录。
- **回滚**：撤销本变更客户端提交并重建包；保留已同步的配置 key 以免影响旧客户端，必要时由后续迁移清理。
