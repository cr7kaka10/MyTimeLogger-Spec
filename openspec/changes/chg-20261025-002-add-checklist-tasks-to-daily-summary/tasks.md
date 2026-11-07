## 1. 数据接入

- [x] 1.1 将 `useChecklist` 的任务数组从 App 传入时间簿页面并转交每日摘要；仅修改 `ui/src/App.tsx` 与 `ui/src/components/TimeBook/TimeBookPage.tsx`，最多 2 个文件、50 行。DoD：每日摘要接收到与清单相同的 `TaskItem` 状态和 `is_overdue` 值。

## 2. 任务摘要

- [x] 2.1 在每日摘要中显示摘要当天到期任务及未完成超期任务；完成状态复用 `status === 2`，仅超期未完成项标题加 `【超期】`；仅修改 `TimeBookDailySummary.tsx`，最多 1 个文件、50 行。DoD：当天任务与清单状态一致，超期任务可见且已完成任务不带超期标记。

## 3. 状态排序

- [x] 3.1 将摘要排序改为状态优先、类别次序次之；待完成和逾期项排在已完成/失败项之前，习惯仍使用摘要当天的打卡状态；仅修改 `TimeBookDailySummary.tsx`，最多 1 个文件、50 行。DoD：不同状态组按规格排序，同状态组保持现有类别顺序。
