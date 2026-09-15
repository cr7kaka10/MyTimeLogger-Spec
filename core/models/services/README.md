# 客户端业务服务层

本目录承载 `Database.ts` 中超过直接 CRUD 的业务入口。

## 调用链路约定

```text
UI Hook / SyncWorker
  -> Database 兼容门面
  -> services/XxxService
  -> repositories/XxxRepository
  -> SQLite SQL
```

## 职责边界

- `HabitService`：习惯打卡、取消、连续天数、习惯奖励归属日。
- `RewardLedgerService`：金币流水、钱包快照、幂等键、余额重算。
- `TaskService`：任务状态、防降级、任务奖励。
- `GoalService`：目标进度、目标自动结算。
- `ConfigService`：系统配置读写、JSON 父配置与扁平 key 映射。

## 注释要求

每个 public 业务方法必须用中文注释写清：

- 调用链路：谁调用本方法，本方法再调用谁。
- 写入边界：是否开启事务，影响哪些表。
- 返回数据：返回字段来自哪些表，是否已做重算或同步标记。

禁止把多个领域混在一个“万能 Service”里。
