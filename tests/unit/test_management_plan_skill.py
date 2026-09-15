import json
from pathlib import Path

from server.domain.management_plan_schema import validate_manifest, validate_patch
from server.domain.management_planning_policy import POLICY_VERSION, SKILL_VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_skill_declares_schema_tables_filters_and_application_gate():
    skill = (ROOT / "server" / "skills" / "management-planning" / "SKILL.md").read_text(encoding="utf-8")
    for token in (
        "server_reward_config", "server_learning_objectives", "server_learning_krs",
        "server_learning_tasks", "server_goals", "server_goal_category_bindings",
        "server_exercise_plan_versions", "server_exercise_plan_items", "server_rewards",
        "user_id=:current_user_id", "校验变更", "确认并应用", "management_plan_non_simplified_chinese",
    ):
        assert token in skill
    assert "server_reward_ledger" in skill
    assert "禁止在输出中提供或覆盖 `evidence`" in skill


def test_skill_contract_fixtures_validate():
    fixtures = json.loads((ROOT / "tests" / "fixtures" / "management_plan_contracts.json").read_text(encoding="utf-8"))
    assert validate_manifest(fixtures["review"])["mode"] == "review"
    assert validate_manifest(fixtures["proposal"])["mode"] == "proposal"
    assert validate_patch(fixtures["patch"])["items"][0]["action"] == "update"
    assert POLICY_VERSION == "management-planning-v3"
    assert SKILL_VERSION == "management-planning-skill-v2"
