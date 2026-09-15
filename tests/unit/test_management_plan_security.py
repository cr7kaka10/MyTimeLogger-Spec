import sqlite3

from server.domain.management_plan_service import ManagementPlanService
from server.models.server_schema import ensure_server_schema


def test_context_excludes_provider_secrets_and_private_payload(tmp_path):
    path = tmp_path / "security.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('safe','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO server_tasks(id,user_id,title,raw_json,updated_at) VALUES('task-1',1,'缴费','{\"token\":\"secret\"}','2026-08-06 02:00:00')")
    conn.commit(); conn.close()
    def connect():
        item = sqlite3.connect(path)
        item.row_factory = sqlite3.Row
        return item
    service = ManagementPlanService(connect)
    context = service.context(1)
    text = str(context)
    assert "secret" not in text
    assert "raw_json" not in text


def test_context_uses_version_and_legacy_sleep_date_as_record_identity(tmp_path):
    path = tmp_path / "context-identity.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("DROP TABLE server_huawei_sleep_data")
    conn.execute("CREATE TABLE server_huawei_sleep_data (user_id INTEGER, date TEXT, total_sleep_min INTEGER, updated_at TEXT)")
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('identity','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO server_exercise_plan_versions(version,user_id,title,created_at,updated_at) VALUES('v1',1,'力量计划','2026-08-06 02:00:00','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO server_huawei_sleep_data(user_id,date,total_sleep_min,updated_at) VALUES(1,'2026-08-05',420,'2026-08-06 02:00:00')")
    conn.commit(); conn.close()
    def connect():
        item = sqlite3.connect(path); item.row_factory = sqlite3.Row; return item
    service = ManagementPlanService(connect)
    before = service.context(1)["context_version"]
    conn = sqlite3.connect(path)
    conn.execute("UPDATE server_huawei_sleep_data SET updated_at='2026-08-06 03:00:00' WHERE user_id=1")
    conn.commit(); conn.close()
    assert service.context(1)["context_version"] != before


def test_context_includes_active_plan_and_decision_fields_without_private_data(tmp_path):
    path = tmp_path / "complete-context.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('context','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO server_goals(id,user_id,title,metric,target_value,period,operator,reward_coins,is_active,created_at,updated_at) VALUES('g1',1,'每周学习','minutes',600,'weekly','>=',30,1,'2026-08-06 02:00:00','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,description,is_active,created_at,updated_at) VALUES('r1',1,'看电影',40,'完成周目标后解锁',1,'2026-08-06 02:00:00','2026-08-06 02:00:00')")
    conn.commit(); conn.close()
    def connect():
        item = sqlite3.connect(path); item.row_factory = sqlite3.Row; return item
    service = ManagementPlanService(connect)
    before = service.context(1)["context_version"]
    manifest = {"items": [{"logical_key": "goal.weekly-study", "type": "goal", "action": "create", "target_value": 600}]}
    service.publish_manifest(1, manifest, revision_kind="major", reason="上下文测试")
    context = service.context(1)
    assert context["context_version"] != before
    assert context["active_management_plan"]["manifest"]["items"][0]["logical_key"] == "goal.weekly-study"
    assert context["domains"]["server_goals"]["items"][0]["target_value"] == 600
    assert context["domains"]["server_rewards"]["items"][0]["price"] == 40
    assert "raw_json" not in str(context)
    assert "password_hash" not in str(context)
