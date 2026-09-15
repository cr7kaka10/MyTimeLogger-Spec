# -*- coding: utf-8 -*-
"""服务端金币规则计算服务。

调用链路：
  SyncHub / ServerSleepStore
    -> RewardRuleService 计算 amount/title
    -> RewardSettlementService 写入流水和钱包

本服务不写数据库，只读取配置并返回计算结果，方便后续扩展倍率和规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date

from .reward_config_service import RewardConfigMissingError


@dataclass(frozen=True)
class RewardRuleResult:
    amount: float
    title: str
    is_makeup: bool = False
    days_late: int = 0


class RewardRuleService:
    """金币公式与标题规则的统一入口。"""

    def __init__(self, now_fn, item_reward_fn=None):
        self._now = now_fn
        self._item_reward = item_reward_fn

    def calculate_task_success(self, user_id, task_id, title) -> RewardRuleResult:
        reward = self._configured_reward(user_id, "task", task_id, "reward")
        return RewardRuleResult(amount=reward, title=str(title or "清单"))

    def calculate_habit_success(
        self, user_id, habit_id, title, difficulty, target_date, occurred_at=None
    ) -> RewardRuleResult:
        base = self._configured_reward(user_id, "habit", habit_id, "reward")
        days_late = self.makeup_days(target_date, occurred_at)
        if days_late <= 0:
            return RewardRuleResult(amount=base, title=str(title or "习惯"))
        amount = round(base * 0.5, 1)
        return RewardRuleResult(amount=amount, title=f"[补]{title or '习惯'}", is_makeup=True, days_late=days_late)

    def calculate_habit_fail(self, user_id, habit_id, title, difficulty) -> RewardRuleResult:
        penalty = self._configured_reward(user_id, "habit", habit_id, "penalty")
        return RewardRuleResult(amount=abs(float(penalty)), title=str(title or "习惯"))

    def calculate_exercise_success(self, user_id, item_id, title) -> RewardRuleResult:
        reward = self._configured_reward(user_id, "exercise", item_id, "reward")
        return RewardRuleResult(amount=reward, title=str(title or "运动打卡"))

    def calculate_exercise_score(self, user_id, item_id, title, score_total) -> RewardRuleResult:
        base = self._configured_reward(user_id, "exercise", item_id, "reward")
        try:
            score = max(0.0, min(100.0, float(score_total)))
        except Exception:
            score = 0.0
        reward = round(float(base) * score / 100.0, 2)
        return RewardRuleResult(amount=reward, title=f"{title or '每日运动评分'} {int(round(score))}分")

    @staticmethod
    def calculate_exercise_score_band(title, score_total, day_name, completed_items, total_items) -> RewardRuleResult:
        """按每日总分结算：工作日五档，周末全打卡仅奖励最低正档。"""
        try:
            score = max(0, min(100, int(round(float(score_total)))))
        except (TypeError, ValueError):
            score = 0
        if str(day_name) in {"六", "日"}:
            complete = int(completed_items or 0) >= max(1, int(total_items or 0))
            amount = 10 if complete else 0
            label = "周末全打卡" if complete else "周末未全打卡"
            return RewardRuleResult(amount=amount, title=f"{title or '每日运动评分'} {label}")
        amount = -50 if score < 60 else 10 if score < 70 else 30 if score < 80 else 50 if score < 90 else 80
        return RewardRuleResult(amount=amount, title=f"{title or '每日运动评分'} {score}分")

    def calculate_learning_success(self, user_id, item_id, title) -> RewardRuleResult:
        reward = self._configured_reward(user_id, "learning", item_id, "reward")
        return RewardRuleResult(amount=reward, title=str(title or "学习任务"))

    def makeup_days(self, target_date, occurred_at=None) -> int:
        target = self._parse_date(target_date)
        actual = self._parse_date(occurred_at)
        if target is None or actual is None:
            return 0
        return max(0, (actual - target).days)

    def _configured_reward(self, user_id, item_type, item_id, field) -> float:
        if self._item_reward is None:
            raise RewardConfigMissingError(f"reward_config_reader_missing:{item_type}:{item_id}")
        configured = self._item_reward(user_id, item_type, item_id) or {}
        value = configured.get(field)
        if value is None and field == "reward":
            value = configured.get("coins")
        if value is None and field == "penalty":
            value = configured.get("reward")
        if value is None:
            raise RewardConfigMissingError(f"reward_config_value_missing:{item_type}:{item_id}:{field}")
        return float(value)

    def _parse_date(self, value) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text[:10]).date()
        except Exception:
            return None
