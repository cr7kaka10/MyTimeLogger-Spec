## 1. 每日摘要奖励展示

- [x] 1.1 为每日摘要的任务和习惯条目接入对应奖励来源，复用奖励摘要读取并支持只读行内显示金币、物品奖励及加载/错误态；仅修改 `ui/src/components/TimeBook/TimeBookDailySummary.tsx` 与 `ui/src/components/Rewards/SourceRewardSummary.tsx`，最多 2 个文件、50 行。DoD：任务和习惯均显示各自配置的完成奖励；无物品时显示“未设置”；外层摘要导航可用；奖励配置、实际入账和结算规则不变。
