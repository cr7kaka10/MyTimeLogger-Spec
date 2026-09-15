# server/repositories

这里预留服务端 Repository 层，目标是把 `store.py` 中分散的 SQL 按表或聚合根拆出来。

当前阶段为了降低改动风险，只先建立边界说明，复杂业务已经先进入 `server/domain/`：

- REST 路由仍调用 `ServerSleepStore`，保持旧 API 兼容。
- `ServerSleepStore` 逐步变成门面，后续迁移时只负责连接、事务和老方法转发。
- 真正的 SQL Repository 后续建议按 `reward_repository.py`、`habit_repository.py`、`sync_repository.py` 拆分。

禁止新增新的大段业务 SQL 到 `server.py`。新增业务规则应优先进入 `server/domain/`。

