import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from server.domain.management_plan_service import ManagementPlanService, ManagementPlanError
from server.models.server_schema import ensure_server_schema


def _service(tmp_path):
    db_path = tmp_path / "management-plan.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES ('a','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES ('b','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'输入','增益'),(1,'输出','增益'),(2,'输入','增益'),(2,'输出','增益')")
    conn.commit()
    conn.close()
    def connect():
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection
    return ManagementPlanService(connect), db_path


def _payload():
    return {
        "schema_version": "1",
        "plan_key": "self-management",
        "title": "夏季自我管理方案",
        "items": [
            {"logical_key": "habit.morning-brush", "type": "local_habit", "action": "create", "expected_minutes": 5},
            {"logical_key": "reward.weekend-game", "type": "reward_item", "action": "create", "reward": {"coins": 8}},
        ],
    }


def test_draft_preview_apply_is_idempotent_and_exportable(tmp_path):
    service, db_path = _service(tmp_path)
    draft = service.create_draft(1, "帮我安排一套能坚持的生活方案", generated_payload=_payload())
    preview = service.preview(1, draft["draft_id"])
    first = service.apply(1, draft["draft_id"], preview["plan_digest"], "apply-1")
    second = service.apply(1, draft["draft_id"], preview["plan_digest"], "apply-1")

    assert first["status"] == "applied"
    assert second["application_id"] == first["application_id"]
    revisions = service.list_revisions(1)
    assert revisions[0]["version"] == "v1.0"
    conn = sqlite3.connect(db_path)
    revision_row = conn.execute("SELECT parent_revision_id,manifest_json FROM server_management_plan_revisions WHERE id=?", (revisions[0]["id"],)).fetchone()
    assert revision_row[0] is None
    assert json.loads(revision_row[1])["skill_version"] == "management-planning-skill-v2"
    change = conn.execute("SELECT actor_id,request_summary FROM server_management_plan_change_log WHERE revision_id=? LIMIT 1", (revisions[0]["id"],)).fetchone()
    assert change[0] == "management-plan-service"
    assert json.loads(change[1])["language_contract"] == "simplified_chinese"
    conn.close()
    exported = service.export_revision(1, revisions[0]["id"])
    assert exported["manifest_digest"] == preview["plan_digest"]
    assert "夏季自我管理方案" in exported["markdown"]

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_management_plan_revisions WHERE user_id=2").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM server_habits WHERE user_id=1 AND id LIKE 'local_%'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=1 AND id LIKE 'reward_%'").fetchone()[0] == 1
    conn.close()


def test_second_revision_records_parent_and_preview_warning(tmp_path):
    service, db_path = _service(tmp_path)
    first = service.create_draft(1, "第一版", generated_payload=_payload())
    first_preview = service.preview(1, first["draft_id"])
    applied = service.apply(1, first["draft_id"], first_preview["plan_digest"], "parent-1")
    second_payload = {"items": [{"logical_key": "habit.morning-brush", "type": "local_habit", "action": "update", "title": "早起刷牙"}]}
    second = service.create_draft(1, "微调方案", generated_payload=second_payload)
    preview = service.preview(1, second["draft_id"])
    assert preview["warnings"] == ["habit.morning-brush 尚未绑定稳定记录，应用前会重新匹配"]
    second_applied = service.apply(1, second["draft_id"], preview["plan_digest"], "parent-2")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT parent_revision_id FROM server_management_plan_revisions WHERE id=?", (second_applied["result"]["revision"]["revision_id"],)).fetchone()
    assert row[0] == applied["result"]["revision"]["revision_id"]
    conn.close()


def test_apply_publish_failure_leaves_business_and_revision_counts_unchanged(tmp_path, monkeypatch):
    service, db_path = _service(tmp_path)
    draft = service.create_draft(1, "失败回滚", generated_payload=_payload())
    preview = service.preview(1, draft["draft_id"])
    monkeypatch.setattr(service, "publish_manifest", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("模拟发布失败")))
    with pytest.raises(RuntimeError):
        service.apply(1, draft["draft_id"], preview["plan_digest"], "rollback-1")
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_management_plan_revisions WHERE user_id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM server_habits WHERE user_id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=1").fetchone()[0] == 0
    conn.close()


def test_learning_materialization_rejects_invalid_category_without_partial_rows(tmp_path):
    service, db_path = _service(tmp_path)
    manifest = {"schema_version": "1", "plan_key": "learning-plan", "title": "学习方案", "items": [{
        "logical_key": "learning.ai", "type": "learning", "action": "create", "title": "学习人工智能",
        "krs": [{"title": "关键结果", "tasks": [{"title": "合法任务", "category_id": 1}, {"title": "非法任务"}]}],
    }]}
    with pytest.raises(ManagementPlanError) as error:
        service.publish_manifest(1, manifest)
    assert error.value.code == "invalid_learning_category"
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_learning_objectives").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM server_learning_krs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM server_learning_tasks").fetchone()[0] == 0


def test_stale_context_and_cross_user_access_are_rejected(tmp_path):
    service, _ = _service(tmp_path)
    draft = service.create_draft(1, "方案", generated_payload=_payload())
    try:
        service.preview(2, draft["draft_id"])
    except ManagementPlanError as exc:
        assert exc.code == "draft_not_found"
    else:
        raise AssertionError("跨用户读取草案未被拒绝")


def test_get_draft_returns_only_current_user_unexpired_draft(tmp_path):
    service, db_path = _service(tmp_path)
    draft = service.create_draft(1, "读取方案", generated_payload=_payload())
    before = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM server_management_plan_drafts").fetchone()[0]

    loaded = service.get_draft(1, draft["draft_id"])
    assert loaded["draft_id"] == draft["draft_id"]
    assert loaded["payload"] == draft["payload"]
    assert sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM server_management_plan_drafts").fetchone()[0] == before

    with pytest.raises(ManagementPlanError, match="方案草案不存在") as cross_user:
        service.get_draft(2, draft["draft_id"])
    assert cross_user.value.code == "draft_not_found"

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE server_management_plan_drafts SET expires_at='2026-01-01 00:00:00' WHERE id=?", (draft["draft_id"],))
    conn.commit(); conn.close()
    with pytest.raises(ManagementPlanError, match="方案草案已过期") as expired:
        service.get_draft(1, draft["draft_id"])
    assert expired.value.code == "draft_expired"


def test_invalid_payload_has_no_draft_record(tmp_path):
    service, db_path = _service(tmp_path)
    try:
        service.create_draft(1, "坏方案", generated_payload={"items": [{"logical_key": "x", "type": "goal"}]})
    except ManagementPlanError as exc:
        assert exc.code == "invalid_logical_key"
    else:
        raise AssertionError("非法方案未被拒绝")
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_management_plan_drafts").fetchone()[0] == 0
    conn.close()


def test_draft_generation_supports_version_identity_and_rejects_missing_identity(tmp_path):
    service, db_path = _service(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO server_exercise_plan_versions(version,user_id,title,created_at,updated_at) VALUES('v1',1,'力量计划','2026-08-06 02:00:00','2026-08-06 02:00:00')")
    conn.commit(); conn.close()
    calls = []
    draft = service.create_draft(1, "生成方案", model_runner=lambda request, context: calls.append((request, context)) or _payload())
    assert calls and draft["draft_id"]

    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE server_huawei_sleep_data")
    conn.execute("CREATE TABLE server_huawei_sleep_data (user_id INTEGER, date TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO server_huawei_sleep_data(user_id,date,updated_at) VALUES(1,NULL,'2026-08-06 03:00:00')")
    conn.commit(); conn.close()
    try:
        service.create_draft(1, "不能生成", generated_payload=_payload())
    except ManagementPlanError as exc:
        assert exc.code == "planning_context_unavailable"
    else:
        raise AssertionError("缺少稳定标识的记录未被拒绝")
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_management_plan_drafts WHERE user_id=1").fetchone()[0] == 1
    conn.close()


def test_import_patch_and_compare_return_deterministic_changes(tmp_path):
    service, _ = _service(tmp_path)
    draft = service.create_draft(1, "方案", generated_payload=_payload())
    preview = service.preview(1, draft["draft_id"])
    applied = service.apply(1, draft["draft_id"], preview["plan_digest"], "apply-import")
    revision_id = applied["result"]["revision"]["revision_id"]

    patch = service.patch_preview(1, revision_id, {
        "items": [{"logical_key": "reward.weekend-game", "action": "update", "value": {"reward": {"coins": 12}}, "reason": "提高周末激励"}]
    })
    second = service.publish_manifest(1, patch["manifest"], revision_kind="minor", parent_revision_id=revision_id, reason="奖励微调")
    comparison = service.compare_revisions(1, revision_id, second["revision_id"])
    assert any(item["logical_key"] == "reward.weekend-game" and item["change_type"] == "changed" for item in comparison["changes"])

    imported = service.import_preview(1, patch["manifest"])
    assert imported["manifest_digest"] == patch["manifest_digest"]


def test_external_ticktick_item_stops_in_reconcile_without_internal_write(tmp_path):
    service, db_path = _service(tmp_path)
    payload = {"items": [{"logical_key": "task.new-ticktick", "type": "ticktick_task", "action": "create", "title": "临时任务"}]}
    draft = service.create_draft(1, "创建一个滴答任务", generated_payload=payload)
    preview = service.preview(1, draft["draft_id"])
    result = service.apply(1, draft["draft_id"], preview["plan_digest"], "external-1")
    assert result["status"] == "needs_reconcile"
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_management_plan_revisions WHERE user_id=1").fetchone()[0] == 0
    conn.close()


def test_confirmed_external_binding_publishes_provider_id_once(tmp_path):
    service, db_path = _service(tmp_path)
    payload = {
        "items": [{"logical_key": "task.provider", "type": "ticktick_task", "action": "create", "title": "临时外部任务"}]
    }
    draft = service.create_draft(1, "创建并绑定滴答任务", generated_payload=payload)
    preview = service.preview(1, draft["draft_id"])
    confirmed = service.apply(
        1,
        draft["draft_id"],
        preview["plan_digest"],
        "external-confirmed-1",
        {"task.provider": {"status": "confirmed", "result_task_id": "provider-task-1", "project_id": "inbox"}},
    )
    assert confirmed["status"] == "applied"
    assert confirmed["result"]["items"][0]["result_task_id"] == "provider-task-1"
    conn = sqlite3.connect(db_path)
    binding = conn.execute(
        "SELECT record_id,binding_status FROM server_management_plan_bindings WHERE user_id=1"
    ).fetchone()
    assert binding == ("provider-task-1", "confirmed")
    assert conn.execute("SELECT COUNT(*) FROM server_management_plan_revisions WHERE user_id=1").fetchone()[0] == 1
    conn.close()


def test_review_draft_is_read_only_and_empty_proposal_is_not_saved(tmp_path):
    service, db_path = _service(tmp_path)
    review_payload = {
        "summary": "当前奖励规则已经覆盖日常习惯",
        "items": [],
        "review": {"strengths": ["有明确目标"], "risks": ["睡眠恢复不足"], "recommendations": ["先稳定作息"]},
    }
    review = service.create_draft(1, "总结我当前的管理方案", generated_payload=review_payload)
    assert review["payload"]["mode"] == "review"
    assert review["payload"]["policy_version"] == "management-planning-v3"
    assert review["payload"]["skill_version"] == "management-planning-skill-v2"
    preview = service.preview(1, review["draft_id"])
    with pytest.raises(ManagementPlanError) as error:
        service.apply(1, review["draft_id"], preview["plan_digest"], "review-apply")
    assert error.value.code == "review_not_applicable"

    with pytest.raises(ManagementPlanError) as empty:
        service.create_draft(1, "帮我制定方案", generated_payload={"items": []})
    assert empty.value.code == "empty_plan_proposal"
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_management_plan_drafts WHERE user_id=1").fetchone()[0] == 1
    conn.close()


def test_review_evidence_uses_current_user_reward_and_store_rules(tmp_path):
    service, db_path = _service(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,updated_at) VALUES('task-a',1,'整理书桌',0,'2026-08-07 01:00:00')")
    conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'task','task-a',2.5,1.5,'2026-08-07 01:00:00')")
    conn.execute("INSERT INTO server_goals(id,user_id,title,metric,target_value,period,operator,reward_coins,penalty_coins,is_active,created_at,updated_at) VALUES('goal-a',1,'每日输出','duration',90,'daily','>=',8,3,1,'2026-08-07 01:00:00','2026-08-07 01:00:00')")
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,unlock_source_type,unlock_source_id,inventory_mode,unlock_required_count,is_active,created_at,updated_at) VALUES('reward-a',1,'周末游戏',0,'goal','goal-a','weekly',1,1,'2026-08-07 01:00:00','2026-08-07 01:00:00')")
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,unlock_source_type,unlock_source_id,inventory_mode,unlock_required_count,is_active,created_at,updated_at) VALUES('reward-b',1,'历史商品',20,'habit','gone','unlimited',3,1,'2026-08-07 01:00:00','2026-08-07 01:00:00')")
    conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(2,'task','task-a',99,99,'2026-08-07 01:00:00')")
    conn.commit(); conn.close()
    review = service.create_draft(1, "总结当前管理方案", generated_payload={"items": [], "review": {"strengths": [], "risks": [], "recommendations": [], "evidence": {"coins": 999}}})
    evidence = review["payload"]["review"]["evidence"]
    assert {rule["source_title"] for rule in evidence["reward_rules"]} >= {"整理书桌", "每日输出"}
    assert {(item["title"], item["source_title"]) for item in evidence["store_items"]} == {("周末游戏", "每日输出"), ("历史商品", "来源已不存在")}
    assert all(rule["coins"] != 99 for rule in evidence["reward_rules"])
    assert "wallet" not in evidence


def test_mindmap_snapshot_uses_current_user_facts_and_never_exposes_sensitive_fields(tmp_path):
    service, db_path = _service(tmp_path)
    conn = sqlite3.connect(db_path)
    now = "2026-08-09 12:00:00"
    today = datetime.now(timezone(timedelta(hours=8))).date()
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,due_date,updated_at) VALUES('task-a',1,'整理书桌',0,?,?)", (today.isoformat(), now))
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,due_date,updated_at) VALUES('task-overdue',1,'逾期任务',0,?,?)", ((today - timedelta(days=1)).isoformat(), now))
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,due_date,updated_at) VALUES('task-future',1,'未来任务',0,?,?)", ((today + timedelta(days=1)).isoformat(), now))
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,updated_at) VALUES('task-undated',1,'无时间任务',0,?)", (now,))
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,due_date,updated_at) VALUES('task-complete',1,'已完成任务',2,?,?)", (today.isoformat(), now))
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,deleted_at,due_date,updated_at) VALUES('task-deleted',1,'已删除任务',0,?, ?,?)", (now, today.isoformat(), now))
    conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,created_at,updated_at) VALUES('habit-a',1,'晨间刷牙',0,?,?)", (now, now))
    conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,created_at,updated_at) VALUES('habit-old',1,'归档习惯',1,?,?)", (now, now))
    conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('objective-a',1,'掌握 TypeScript',0,?,?)", (now, now))
    conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('kr-a',1,'objective-a','完成类型系统学习',10,2,?,?)", (now, now))
    conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,reward,created_at,updated_at) VALUES('learn-a',1,'kr-a','学习 TypeScript',0,3,?,?)", (now, now))
    conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('objective-empty',1,'空目标',0,?,?)", (now, now))
    conn.execute("INSERT INTO server_goals(id,user_id,title,metric,target_value,period,operator,reward_coins,penalty_coins,is_active,created_at,updated_at) VALUES('goal-a',1,'每日输出','duration',90,'daily','>=',8,2,1,?,?)", (now, now))
    conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'task','task-a',2.5,1.5,?)", (now,))
    conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'learning','learn-a',4,2,?)", (now,))
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,unlock_source_type,unlock_source_id,inventory_mode,unlock_required_count,is_active,created_at,updated_at) VALUES('reward-a',1,'周末游戏',0,'goal','goal-a','weekly',1,1,?,?)", (now, now))
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,unlock_source_type,unlock_source_id,inventory_mode,unlock_required_count,is_active,created_at,updated_at) VALUES('reward-inactive',1,'停用旧商品',0,'goal','goal-a','weekly',1,0,?,?)", (now, now))
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,unlock_source_type,unlock_source_id,unlock_task_title,inventory_mode,unlock_required_count,is_active,created_at,updated_at) VALUES('reward-b',1,'历史商品',20,'habit','gone','旧习惯','unlimited',1,1,?,?)", (now, now))
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,inventory_mode,unlock_required_count,is_active,created_at,updated_at) VALUES('reward-c',1,'自由兑换',12,'unlimited',1,1,?,?)", (now, now))
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,updated_at,raw_json) VALUES('task-b',2,'其他账号任务',0,?,'secret')", (now,))
    conn.commit(); conn.close()

    snapshot = service.mindmap_snapshot(1)
    domains = {domain["key"]: domain["items"] for domain in snapshot["domains"]}
    assert [domain["key"] for domain in snapshot["domains"]] == ["goal", "sleep", "learning_task", "habit", "checklist_task"]
    task = next(item for item in domains["checklist_task"] if item["source_id"] == "task-a")
    assert {item["source_id"] for item in domains["checklist_task"]} == {"task-a", "task-overdue"}
    objective = next(item for item in domains["learning_task"] if item["source_id"] == "objective-a")
    kr = next(item for item in objective["children"] if item["source_id"] == "kr-a")
    learning = next(item for item in kr["children"] if item["source_id"] == "learn-a")
    goal = next(item for item in domains["goal"] if item["source_id"] == "goal-a")
    assert task["reward"] == {"coins": 2.5, "penalty": 1.5, "status": "configured", "editable": True}
    assert learning["reward"] == {"coins": 4.0, "penalty": 2.0, "status": "configured", "editable": True}
    assert goal["reward"]["coins"] == 8
    assert [product["title"] for product in goal["items"]] == ["周末游戏"]
    assert all(item["source_id"] != "gone" for item in domains["habit"])
    assert snapshot["unbound_products"][0]["id"] == "reward-c"
    assert snapshot["unbound_products"][0]["source_status"] == "none"
    assert all(item["source_id"] != "task-b" for item in domains["checklist_task"])
    assert all(item["source_id"] != "task-complete" for item in domains["checklist_task"])
    assert all(item["source_id"] != "habit-old" for item in domains["habit"])
    assert all(item["source_id"] != "objective-empty" for item in domains["learning_task"])
    assert "exercise_checkin" not in domains
    assert "raw_json" not in json.dumps(snapshot, ensure_ascii=False)
    assert "wallet" not in json.dumps(snapshot, ensure_ascii=False)


def test_review_retries_once_when_model_misses_the_contract(tmp_path):
    service, _ = _service(tmp_path)
    contexts = []
    def runner(_request, context):
        contexts.append(context)
        return {"items": [], "review": {"strengths": []}} if len(contexts) == 1 else {"items": [], "review": {"strengths": ["有目标"], "risks": ["需关注"], "recommendations": ["先执行"]}}
    draft = service.create_draft(1, "总结当前管理方案", model_runner=runner)
    assert draft["payload"]["review"]["strengths"] == ["有目标"]
    assert contexts[1]["review_contract_retry"] is True


def test_proposal_retries_once_for_english_and_never_saves_second_failure(tmp_path):
    service, db_path = _service(tmp_path)
    calls = []

    def runner(_request, context):
        calls.append(context)
        if len(calls) == 1:
            return {"items": [{"logical_key": "habit.routine", "type": "local_habit", "action": "create", "title": "Build a routine"}]}
        return {"items": [{"logical_key": "habit.routine", "type": "local_habit", "action": "create", "title": "建立日常习惯"}]}

    draft = service.create_draft(1, "制定日常习惯方案", model_runner=runner)
    assert draft["payload"]["items"][0]["title"] == "建立日常习惯"
    assert calls[1]["language_contract_retry"] is True

    failing_calls = []

    def failing_runner(_request, context):
        failing_calls.append(context)
        return {"items": [{"logical_key": "habit.routine", "type": "local_habit", "action": "create", "title": "Build a routine"}]}

    with pytest.raises(ManagementPlanError) as error:
        service.create_draft(1, "再次制定方案", model_runner=failing_runner)
    assert error.value.code == "management_plan_non_simplified_chinese"
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_management_plan_drafts WHERE user_id=1").fetchone()[0] == 1
    conn.close()
