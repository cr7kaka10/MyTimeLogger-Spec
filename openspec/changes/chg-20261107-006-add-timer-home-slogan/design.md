## Context

`TimerPage` 将 `totalTodayMinutes` 与最近同步文案交给共享的 `TimerStats`。该组件在手机宽度下用纵向布局，依次显示总时长、日期、同步文案；在 PC 宽度下单行显示，总时长与日期后有弹性空位。`SettingsPage` 通过 `useSettings.updateSetting` 写入账号本地 `system_config`，已有同步链路会推拉未屏蔽的配置键。

## Goals / Non-Goals

**Goals:** 在同一账号的 PC 与安卓计时首页显示可编辑标语；手机端将日期与同步信息移到总时长右侧；长标语在两端完整换行显示。

**Non-Goals:** 原生桌面小组件、计时业务逻辑和服务端接口变更。

## Decisions

1. **单一配置键**：使用 `system_config.home_slogan` 保存纯文本，默认空字符串。`SystemSettings`、`useSettings` 加载和 `App → TimerPage → TimerStats` 传参复用既有设置路径。设置页提供多行输入、保存与清空；保存失败时保留草稿并提示。与仅存设备本地相比，沿用现有账号同步满足两端展示同一标语；不新增服务端 API。
2. **跨端刷新**：本机保存通过现有设置状态刷新立即显示；`sync-pull-complete` 后只重新读取标语配置并更新设置状态，使另一设备同步到的新值无需重启即可显示。监听器按组件生命周期解绑。
3. **响应式布局**：手机端 `TimerStats` 首行左右两列，左列今日总时长，右列纵向显示日期和最近同步文案；标语放在下一行，占满宽度。PC 端在总时长与日期后放标语区域，最近同步状态仍在右侧；标语可自动换行，顶部区域随内容增高。标语文本按纯文本渲染，保留用户输入的换行并允许长连续字符串断行；页面内容在高度不足时可滚动，不能裁断标语。
4. **文本规则**：允许清空；保存时去除首尾空白，内部换行保留。无标语时不渲染占位文案。React 文本节点负责转义，不按 HTML 解释。

### UI 规范说明

- 参考界面：现有 `TimerStats`（`ui/src/components/Timer/TimerStats.tsx`）及设置页计时设置区（`ui/src/components/Settings/SettingsPage.tsx`）。
- 规范遵循：已读 `openspec/specs/fluent-ui-guide/spec.md`；该文档的 PyQt6 独立窗口条款不适用于当前 React 内嵌页面。
- 主题适配：白天/暗黑均验证；新增文字使用现有主题令牌/暗色变体，不新增硬编码颜色。
- 新窗口：否；在现有设置页内编辑。

## Risks / Trade-offs

- [PC 顶部多行可能挤占计时页高度] → 顶部按内容增高，视口不足时允许纵向滚动；在常见 PC 窗口高度与窄窗口验证。
- [手机顶部三项信息横向拥挤] → 日期、同步状态置于右列并允许自身换行，总时长不压缩；在截图对应宽度及更窄宽度验证。
- [同步后设置状态仍显示旧值] → 响应 `sync-pull-complete` 刷新标语，并验证 PC/安卓双端同步后页面更新。

## Migration Plan

旧账号未设置 `home_slogan` 时读取为空，不需数据迁移。发布后保存即写入现有配置表；回滚客户端界面与设置接线即可，旧版会忽略该配置键。

## Open Questions

无；按用户截图中的设备内容识别安卓与 PC，不依赖图片编号。
