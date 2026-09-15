"""管理方案奖励建议的确定性边界。"""
from __future__ import annotations

import math


class RewardPolicyError(ValueError):
    def __init__(self, code: str, message: str, logical_key: str):
        super().__init__(message)
        self.code = code
        self.logical_key = logical_key


MAX_ITEM_COINS = 100.0
MAX_ITEM_PRICE = 100000.0
MAX_DAILY_COINS = 500.0


def validate_reward_items(items: list[dict]) -> list[dict]:
    total = 0.0
    for item in items:
        key = str(item.get("logical_key") or "")
        reward = item.get("reward") if isinstance(item.get("reward"), dict) else {}
        coins = reward.get("coins", item.get("reward_coins", 0))
        if not isinstance(coins, (int, float)) or isinstance(coins, bool) or not math.isfinite(float(coins)) or float(coins) < 0 or float(coins) > MAX_ITEM_COINS:
            raise RewardPolicyError("reward_out_of_range", "单项奖励必须在 0 到 100 金币之间", key)
        price = item.get("price")
        if price is not None and (not isinstance(price, (int, float)) or isinstance(price, bool) or not math.isfinite(float(price)) or float(price) < 0 or float(price) > MAX_ITEM_PRICE):
            raise RewardPolicyError("price_out_of_range", "商品价格超出允许范围", key)
        total += float(coins)
    if total > MAX_DAILY_COINS:
        raise RewardPolicyError("daily_reward_out_of_range", "单份方案奖励总额超过每日上限", "plan")
    return items
