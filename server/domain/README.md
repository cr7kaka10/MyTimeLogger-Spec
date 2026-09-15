# server/domain

这里放服务端业务规则入口，不直接暴露给 UI。

## 主调用链路

- REST：`server.py` 路由 -> `ServerSleepStore` 兼容门面 -> `domain/*Service` -> SQLite SQL。
- SyncHub：`sync_hub.py` 同步仲裁 -> 同步表白名单/字段白名单 -> 必要时调用 domain 服务更新钱包快照。

## 当前已治理

- `RewardWalletService`：奖励流水、钱包快照、背包使用、外部奖励领取。
- `HabitDomainService`：习惯打卡/取消，并通过 `RewardWalletService` 追加奖励流水。

## 定位规则

- 金币余额不对：先看 `RewardWalletService.rebuild_wallet_snapshot()` 和 `verify_wallet_consistency()`。
- 兑换失败或背包异常：先看 `RewardWalletService.buy_reward()`、`list_backpack()`、`use_backpack_item()`。
- 习惯取消误扣：先看 `HabitDomainService.cancel_checkin_habit()` 的 `target_date` 与 `source_id`。

