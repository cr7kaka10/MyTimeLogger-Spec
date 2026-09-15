# -*- coding: utf-8 -*-

import pytest

from server.domain.reward_config_service import RewardConfigMissingError
from server.domain.reward_rule_service import RewardRuleService


def _service(today="2026-06-12 10:00:00", config=None):
    def get_item_reward(user_id, item_type, item_id):
        configured = (config or {}).get((item_type, item_id))
        if configured is None:
            raise RewardConfigMissingError(f"reward_config_missing:{item_type}:{item_id}")
        return configured

    return RewardRuleService(lambda: today, get_item_reward)


def test_habit_success_same_day_not_makeup():
    service = _service(today="2026-06-13 10:00:00", config={("habit", "h1"): {"reward": 1.0, "penalty": 1.0}})

    result = service.calculate_habit_success(
        1, "h1", "慎独", "easy", "2026-06-12", "2026-06-12 23:59:00"
    )

    assert result.amount == 1.0
    assert result.title == "慎独"
    assert result.is_makeup is False
    assert result.days_late == 0


def test_habit_success_one_day_makeup_discount():
    service = _service(today="2026-06-30 10:00:00", config={("habit", "h1"): {"reward": 1.0, "penalty": 1.0}})

    result = service.calculate_habit_success(
        1, "h1", "慎独", "easy", "2026-06-11", "2026-06-12 00:01:00"
    )

    assert result.amount == 0.5
    assert result.title == "[补]慎独"
    assert result.is_makeup is True
    assert result.days_late == 1


def test_habit_success_two_day_makeup_discount_rounds_to_one_decimal():
    service = _service(config={("habit", "h1"): {"reward": 1.0, "penalty": 1.0}})

    result = service.calculate_habit_success(
        1, "h1", "慎独", "easy", "2026-06-10", "2026-06-12 08:00:00"
    )

    assert result.amount == 0.5
    assert result.title == "[补]慎独"
    assert result.days_late == 2


def test_habit_failure_does_not_use_makeup_discount():
    service = _service(config={("habit", "h1"): {"reward": 1.0, "penalty": 2.5}})

    result = service.calculate_habit_fail(1, "h1", "慎独", "easy")

    assert result.amount == 2.5
    assert result.title == "慎独"
    assert result.is_makeup is False
    assert result.days_late == 0


def test_missing_config_is_not_replaced_with_a_default():
    with pytest.raises(RewardConfigMissingError, match="reward_config_missing:task:missing"):
        _service().calculate_task_success(1, "missing", "清单")


@pytest.mark.parametrize(("score", "amount"), [(59, -50), (60, 10), (75, 30), (85, 50), (95, 80)])
def test_weekday_exercise_score_uses_five_fixed_bands(score, amount):
    result = RewardRuleService.calculate_exercise_score_band("v1 周一", score, "周一", 5, 6)
    assert result.amount == amount


def test_weekend_exercise_only_rewards_all_checkins_without_penalty():
    assert RewardRuleService.calculate_exercise_score_band("v1 六", 100, "六", 4, 4).amount == 10
    assert RewardRuleService.calculate_exercise_score_band("v1 日", 20, "日", 3, 4).amount == 0
