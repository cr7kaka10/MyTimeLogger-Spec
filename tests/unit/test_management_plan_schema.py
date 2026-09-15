import pytest

from server.domain.management_plan_schema import (
    ManagementPlanValidationError,
    digest_payload,
    validate_manifest,
    validate_patch,
    validate_simplified_chinese,
)


def test_validate_mixed_manifest_and_digest_is_order_independent():
    first = {
        "schema_version": "1",
        "items": [
            {"logical_key": "task.pay-electricity", "type": "existing_task_reward", "action": "bind", "reward": {"coins": 5}},
            {"logical_key": "habit.morning-brush", "type": "local_habit", "action": "create", "repeat_rule": "FREQ=DAILY"},
        ],
    }
    second = {"items": list(reversed(first["items"])), "schema_version": "1"}
    assert validate_manifest(first)["schema_version"] == "1"
    assert digest_payload(validate_manifest(first)) == digest_payload(validate_manifest(second))


@pytest.mark.parametrize("payload", [
    {"items": [{"logical_key": "task.bad", "type": "unknown", "action": "create"}]},
    {"items": [{"logical_key": "task.bad", "type": "goal", "action": "create", "token": "secret"}]},
    {"items": [{"logical_key": "task.bad", "type": "goal", "action": "create", "reward": {"coins": -1}}]},
    {"items": [{"logical_key": "task.bad", "type": "goal", "action": "create", "calendar_events": []}]},
])
def test_manifest_rejects_unsafe_or_invalid_items(payload):
    with pytest.raises(ManagementPlanValidationError):
        validate_manifest(payload)


def test_patch_only_allows_stable_actions():
    patch = validate_patch({
        "items": [
            {"logical_key": "reward.weekend-game", "action": "update", "value": {"coins": 8}, "reason": "鼓励周末运动"}
        ]
    })
    assert patch["items"][0]["action"] == "update"

    with pytest.raises(ManagementPlanValidationError) as error:
        validate_patch({"items": [{"logical_key": "reward.weekend-game", "action": "delete_ledger"}]})
    assert error.value.code == "unsupported_plan_patch"


def test_proposal_cannot_be_empty_but_review_requires_structured_content():
    with pytest.raises(ManagementPlanValidationError) as empty:
        validate_manifest({"mode": "proposal", "items": []})
    assert empty.value.code == "empty_plan_proposal"

    review = validate_manifest({
        "mode": "review",
        "items": [],
        "review": {"strengths": ["已有习惯"], "risks": ["睡眠不足"], "recommendations": ["先保证睡眠"]},
    })
    assert review["mode"] == "review"

    with pytest.raises(ManagementPlanValidationError) as invalid_review:
        validate_manifest({"mode": "review", "items": [], "review": {"strengths": []}})
    assert invalid_review.value.code == "invalid_review"


def test_review_evidence_is_stripped_from_external_payload():
    review = validate_manifest({
        "mode": "review", "items": [],
        "review": {"strengths": [], "risks": [], "recommendations": [], "evidence": {"coins": 999}},
    })
    assert "evidence" not in review["review"]


def test_simplified_chinese_contract_allows_mixed_technical_name():
    validate_simplified_chinese({"title": "React 学习计划", "summary": "使用 SQL 汇总金币"})


def test_simplified_chinese_contract_rejects_pure_english_natural_text():
    with pytest.raises(ManagementPlanValidationError) as error:
        validate_simplified_chinese({"summary": "Build a better routine"})
    assert error.value.code == "management_plan_non_simplified_chinese"
