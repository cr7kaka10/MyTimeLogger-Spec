import pytest

from server.domain.management_plan_reward_policy import RewardPolicyError, validate_reward_items


def test_reward_policy_accepts_normal_plan():
    assert validate_reward_items([{"logical_key": "task.a", "reward": {"coins": 5}, "price": 20}])


@pytest.mark.parametrize("item", [
    {"logical_key": "task.a", "reward": {"coins": -1}},
    {"logical_key": "task.a", "reward": {"coins": 101}},
    {"logical_key": "reward.a", "price": 100001},
])
def test_reward_policy_rejects_out_of_range_values(item):
    with pytest.raises(RewardPolicyError):
        validate_reward_items([item])


def test_reward_policy_rejects_daily_total():
    with pytest.raises(RewardPolicyError) as error:
        validate_reward_items([{"logical_key": f"task.{index}", "reward": {"coins": 100}} for index in range(6)])
    assert error.value.code == "daily_reward_out_of_range"
