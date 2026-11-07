## 1. 精简每日摘要奖励内容

- [x] 1.1 为每日摘要调用增加紧凑奖励显示，只保留金币数量和已配置物品图标/名称；隐藏奖励前缀、进度/库存/期限、未设置、加载/错误文字，并移除任务/习惯类型副标题；仅修改 `ui/src/components/TimeBook/TimeBookDailySummary.tsx` 与 `ui/src/components/Rewards/SourceRewardSummary.tsx`，最多 2 个文件、50 行。DoD：摘要任务/习惯只显示 `xx🪙` 和可选物品名，无其他奖励补充文字或类别副标题；清单模块完整奖励展示及摘要名称、状态、导航不变。
