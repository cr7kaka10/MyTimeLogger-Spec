# 客户端数据仓储层

本目录只封装 SQLite 读写，不承载跨表业务决策。

## 调用链路约定

```text
services/XxxService
  -> repositories/XxxRepository
  -> Database 底层 _get/_all/_run 或等价 SQL 执行器
```

## 职责边界

- Repository 可以拼 SQL、转换行数据、处理表字段兼容。
- Repository 不决定金币是否发放、不决定习惯是否撤销、不更新多个领域的业务状态。
- 需要跨表事务时，应由 Service 编排。

## 命名规则

- `RewardLedgerRepository`：只处理 `reward_ledger` 查询和写入。
- `HabitRepository`：只处理 `habits`、`habit_checkins` 基础读写。
- `TaskRepository`：只处理 `tasks` 基础读写。
- `SyncRepository`：只处理 `pushed_at`、待同步记录和通用同步读取。

如果一个 Repository 需要同时理解奖励、习惯、目标三套业务规则，说明它应该拆分。
