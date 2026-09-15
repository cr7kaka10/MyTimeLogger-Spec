# -*- coding: utf-8 -*-
import os
import json
import sqlite3
from pathlib import Path
import pytest
import server.store as store_module
from server.store import ServerSleepStore
from server.domain.sample_data_initialization_service import SampleDataInitializationService
from server.domain.default_timer_categories import DEFAULT_TIMER_CATEGORY_RECORDS
from server.models.server_schema import ensure_server_schema
from server.db_wrapper import ServerDBWrapper
from server.sync_hub import SyncHub
from server.sync_sql_allowlist import SYNC_TABLE_SPECS


SYNC_REGISTRY = json.loads((Path(__file__).parents[2] / "shared/protocol/sync-entities.json").read_text(encoding="utf-8"))
SYNC_TABLE_PAIRS = [
    (entity["clientTable"], entity["serverTable"])
    for entity in SYNC_REGISTRY["entities"]
]

CLIENT_INTERNAL_COLUMNS = {
    "*": {"pulled_at"},
    "categories": {"created_at", "is_active"},
    "system_config": {"pushed_at"},
    "user_wallets": {"pushed_at"},
    "exercise_daily_logs": {"week_num", "day_name", "weight", "body_fat_rate", "completed_items", "total_items"},
    "exercise_checkins": {"note"},
    "learning_objectives": {"duration", "baseline", "target_description"},
    "learning_tasks": {"category_id", "priority", "reward", "due_date"},
}

SERVER_INTERNAL_COLUMNS = {
    "*": {"user_id"},
    "huawei_sleep_data": {"calc_trace", "morning_diary_written_at", "evening_diary_written_at"},
    "reward_ledger": {"occurred_at"},
    "exercise_daily_logs": {"exercise_type", "duration_minutes", "calories", "heart_rate_avg"},
    "exercise_checkins": {"log_id"},
    "rewards": {"inventory_mode", "inventory_limit", "unlock_required_count", "unlock_source_type", "unlock_source_id", "unlock_threshold_started_at", "redemption_mode", "fulfillment_mode", "fragment_target_count", "fragment_rule_version"},
}

CLIENT_TABLE_COLUMNS = {
    "categories": {"id", "name", "icon", "color", "group_name", "sort_order", "is_active", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "study_sessions": {"id", "start_time", "end_time", "net_duration_minutes", "net_duration_seconds", "date", "day_of_week", "pause_count", "pause_reasons", "session_summary", "category_id", "updated_at", "pushed_at", "pulled_at"},
    "tasks": {"id", "title", "priority", "status", "category_id", "due_date", "tags", "raw_json", "source", "source_etag", "source_modified_time", "deleted_at", "updated_at", "pushed_at", "pulled_at"},
    "habits": {"id", "name", "icon", "color", "category_id", "sort_order", "is_active", "difficulty", "repeat_rule", "raw_json", "source", "source_etag", "source_modified_time", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "habit_checkins": {"id", "habit_id", "habit_name", "date", "created_at", "checkin_date", "checkin_time", "status", "note", "raw_json", "source_modified_time", "updated_at", "pushed_at", "pulled_at"},
    "goals": {"id", "title", "category_id", "metric", "target_value", "period", "reward_coins", "reward_id", "operator", "penalty_coins", "is_active", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "goal_category_bindings": {"id", "goal_id", "category_id", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "rewards": {"id", "title", "icon", "price", "description", "unlock_task_id", "unlock_task_title", "is_active", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "reward_ledger": {"id", "amount", "source_type", "source_id", "description", "target_date", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "external_rewards": {"id", "ext_id", "item_type", "item_name", "coins", "status", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "reward_config": {"id", "item_type", "item_id", "coins", "penalty", "updated_at", "pushed_at", "pulled_at"},
    "huawei_sleep_data": {"id", "date", "sleep_score", "total_sleep_min", "deep_sleep_min", "light_sleep_min", "rem_sleep_min", "awake_count", "sleep_start", "sleep_end", "deep_sleep_ratio", "light_sleep_ratio", "rem_sleep_ratio", "sleep_continuity", "breathing_score", "sleep_cycles", "awake_min", "fall_asleep_min", "wake_up_min", "atm_sleep_start", "atm_sleep_end", "analysis_report", "analysis_html", "official_advice", "morning_diary", "evening_diary", "report_status", "full_report_state", "tracked_duration_seconds", "source", "synced_at", "sync_status", "sync_error", "updated_at", "pushed_at", "pulled_at"},
    "system_config": {"id", "key", "value", "value_type", "description", "updated_at", "pushed_at", "pulled_at"},
    "atm_summary": {"id", "date", "updated_at", "pushed_at", "pulled_at"},
    "atm_activities": {"id", "date", "activity_type", "start_time", "end_time", "duration_minutes", "comment", "updated_at", "pushed_at", "pulled_at"},
    "exercise_plan_versions": {"version", "title", "source_name", "is_active", "exercise_points", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_daily_logs": {"id", "date", "plan_version", "week_num", "day_name", "weight", "body_fat_rate", "completed_items", "total_items", "exercise_variant", "score_snapshot", "locked_at", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_checkins": {"id", "date", "plan_version", "item_key", "status", "completed_time", "plan_item_id", "item_name", "note", "locked_at", "lock_reason", "deadline_penalty_source_id", "deadline_penalty_amount", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_item_scores": {"id", "date", "plan_version", "item_key", "earned_points", "max_points", "difficulty", "score_scope", "score_rule_version", "score_reason", "status", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_settlements": {"id", "business_date", "plan_version", "score_snapshot", "score_total", "category_scores", "completed_items", "total_items", "settlement_status", "reason_code", "rule_version", "coin_amount", "is_all_complete", "completion_reward_amount", "completion_reason", "occurred_at", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_plan_items": {"id", "plan_version", "day_key", "variant", "section", "sort_order", "name", "sets", "intensity", "tags_json", "progression", "color", "is_active", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_plan_schedule_items": {"id", "plan_version", "schedule_type", "sort_order", "time", "item", "note", "accent", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_plan_diet_rules": {"id", "plan_version", "sort_order", "rule_key", "time", "content", "note", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_plan_score_rules": {"id", "plan_version", "day_type", "sort_order", "schedule_index", "points", "category", "target_time", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_plan_category_rules": {"id", "plan_version", "sort_order", "category", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "exercise_plan_progress_items": {"id", "plan_version", "sort_order", "when_text", "text", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "learning_objectives": {"id", "title", "status", "duration", "baseline", "target_description", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "learning_krs": {"id", "objective_id", "title", "target_value", "current_value", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "learning_tasks": {"id", "kr_id", "title", "status", "category_id", "priority", "reward", "due_date", "created_at", "updated_at", "pushed_at", "pulled_at"},
    "user_wallets": {"user_id", "balance", "last_ledger_uuid", "updated_at", "pushed_at", "pulled_at"},
}


def test_ticktick_task_operation_ledger_is_user_scoped_and_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "ledger.db")
    ensure_server_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(server_ticktick_task_operations)")}
    assert {"user_id", "request_id", "operation", "status", "attempts", "result_task_id", "title_fingerprint", "expected_fingerprint"} <= columns
    now = "2026-07-31 12:00:00"
    conn.execute("INSERT INTO users(username, password_hash, created_at) VALUES ('ledger-user', 'x', ?)", (now,))
    conn.execute("INSERT INTO server_ticktick_task_operations(user_id, request_id, operation, status, created_at, updated_at) VALUES (1, 'request-1', 'create', 'pending', ?, ?)", (now, now))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO server_ticktick_task_operations(user_id, request_id, operation, status, created_at, updated_at) VALUES (1, 'request-1', 'create', 'pending', ?, ?)", (now, now))


def _allowed(mapping, table):
    return set(mapping.get("*", set())) | set(mapping.get(table, set()))


def test_client_server_sync_schema_contract_is_classified(tmp_path):
    db_path = tmp_path / "sync_schema_contract.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)

    assert len(SYNC_TABLE_PAIRS) == len(SYNC_REGISTRY["entities"])
    registry_clients = {client for client, _ in SYNC_TABLE_PAIRS}
    # Keep the contract exhaustive while allowing newly registered pull-only
    # entities to derive their mirror columns directly from the server schema.
    for client_table, server_table in SYNC_TABLE_PAIRS:
      if client_table not in CLIENT_TABLE_COLUMNS:
        CLIENT_TABLE_COLUMNS[client_table] = {
            row[1] for row in conn.execute(f"PRAGMA table_info({server_table})").fetchall()
            if row[1] != "user_id"
        } | {"pulled_at"}
    assert set(CLIENT_TABLE_COLUMNS) == registry_clients
    unclassified = []
    for client_table, server_table in SYNC_TABLE_PAIRS:
      client_cols = CLIENT_TABLE_COLUMNS[client_table]
      server_cols = {
          row[1]
          for row in conn.execute(f"PRAGMA table_info({server_table})").fetchall()
      }
      server_extra = server_cols - client_cols - _allowed(SERVER_INTERNAL_COLUMNS, client_table)
      client_extra = client_cols - server_cols - _allowed(CLIENT_INTERNAL_COLUMNS, client_table)
      if server_extra or client_extra:
          unclassified.append({
              "table": client_table,
              "server_extra": sorted(server_extra),
              "client_extra": sorted(client_extra),
          })

    conn.close()

    assert unclassified == []


def test_shared_registry_matches_server_allowlist_and_atm_keys():
    expected = {
        entity["clientTable"]: (entity["serverTable"], entity["primaryKey"])
        for entity in SYNC_REGISTRY["entities"]
    }
    actual = {name: (spec.server_table, spec.primary_key) for name, spec in SYNC_TABLE_SPECS.items()}
    assert actual == expected
    assert expected["atm_activities"] == ("server_atm_activities", "id")
    atm = next(entity for entity in SYNC_REGISTRY["entities"] if entity["clientTable"] == "atm_activities")
    assert atm["naturalKeys"] == [] and atm["deletePolicy"] == "hard_delete"
    assert next(e for e in SYNC_REGISTRY["entities"] if e["clientTable"] == "exercise_item_scores")["direction"] == "pull_only"
    assert next(e for e in SYNC_REGISTRY["entities"] if e["clientTable"] == "exercise_settlements")["outbox"] is False
    diet = next(e for e in SYNC_REGISTRY["entities"] if e["clientTable"] == "exercise_diet_checkins")
    assert diet["naturalKeys"] == ["date", "plan_version", "rule_key"]
    assert diet["ownership"] == "client_writable" and diet["outbox"] is True
    deadline = next(e for e in SYNC_REGISTRY["entities"] if e["clientTable"] == "exercise_deadline_facts")
    assert deadline["ownership"] == "server_owned" and deadline["direction"] == "pull_only" and deadline["outbox"] is False


def test_server_schema_initialization(tmp_db_path):
    # 初始化 store，它会自动调用 _initialize
    store = ServerSleepStore(db_path=tmp_db_path)

    # 检查数据库文件是否成功创建
    assert os.path.exists(tmp_db_path)

    # 连接数据库验证表是否存在
    conn = sqlite3.connect(tmp_db_path)
    cursor = conn.cursor()

    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    expected_tables = [
        "users",
        "sessions",
        "server_sleep_jobs",
        "server_categories",
        "server_tasks",
        "server_study_sessions",
        "server_habits",
        "server_habit_checkins",
        "server_rewards",
        "server_goals",
        "server_reward_ledger",
        "server_external_rewards",
        "server_reward_config",
        "server_huawei_sleep_data"
    ]

    for table in expected_tables:
        assert table in tables, f"表 {table} 未在数据库中创建"

    # 验证字段是否存在（以 server_categories 为例）
    cursor.execute("PRAGMA table_info(server_categories)")
    cols = {row[1]: row[2] for row in cursor.fetchall()}
    assert "user_id" in cols
    assert "name" in cols
    assert "group_name" in cols

    conn.close()


def test_live_timer_lease_schema_is_idempotent_and_user_unique(tmp_db_path):
    conn = sqlite3.connect(tmp_db_path)
    ensure_server_schema(conn)
    ensure_server_schema(conn)

    lease_columns = {row[1] for row in conn.execute("PRAGMA table_info(live_timer_lease)")}
    assert {
        "user_id", "session_id", "owner_device_id", "category_id", "category_name",
        "state", "started_at", "segment_started_at", "active_elapsed_ms",
        "timer_mode", "duration_ms", "pause_count", "revision", "last_command_seq",
        "last_idempotency_key", "last_user_intent_id", "last_heartbeat_at", "updated_at",
    } <= lease_columns
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN "
        "('live_timer_lease','live_timer_commands','live_timer_audit','live_timer_segments')"
    ).fetchone()[0] == 4
    lease_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='live_timer_lease'"
    ).fetchone()[0]
    assert "user_id INTEGER PRIMARY KEY" in lease_sql
    assert "每用户唯一当前状态" in lease_sql
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(live_timer_commands)")}
    assert "idx_live_timer_commands_user_session" in indexes
    conn.close()


def test_atimelogger_final_backup_schema_is_idempotent(tmp_db_path):
    conn = sqlite3.connect(tmp_db_path)
    ensure_server_schema(conn)
    ensure_server_schema(conn)

    columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(server_atimelogger_backups)"
    )}
    assert {
        "user_id", "stable_session_id", "remote_activity_id", "remote_interval_id",
        "sync_state", "attempts", "last_error_code", "next_retry_at", "claimed_at",
        "created_at", "updated_at",
    } <= columns
    indexes = {row[1] for row in conn.execute(
        "PRAGMA index_list(server_atimelogger_backups)"
    )}
    assert "idx_atimelogger_backups_due" in indexes
    assert any(name.startswith("sqlite_autoindex_server_atimelogger_backups") for name in indexes)
    conn.close()


def test_server_database_accessors_share_isolated_default(tmp_path, monkeypatch):
    monkeypatch.delenv("SERVER_SLEEP_DB_PATH", raising=False)
    fake_module = tmp_path / "checkout" / "server" / "store.py"
    monkeypatch.setattr(store_module, "__file__", str(fake_module))
    store = ServerSleepStore()
    wrapper = ServerDBWrapper(store.db_path)
    expected = os.path.abspath(fake_module.parent / "data" / "mtl_server.db")
    assert store.db_path == expected == wrapper.log_path
    with sqlite3.connect(expected) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0] == 1

def test_absolute_server_database_env_override_is_normalized(tmp_path, monkeypatch):
    override = tmp_path / "runtime" / "nested" / ".." / "mtl_server.db"
    monkeypatch.setenv("SERVER_SLEEP_DB_PATH", str(override))
    store = ServerSleepStore()
    assert store.db_path == os.path.abspath(override)
    assert ServerDBWrapper(store.db_path).log_path == store.db_path

def test_relative_server_database_env_fails_before_creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SERVER_SLEEP_DB_PATH", "server/data/mtl_server.db")
    with pytest.raises(ValueError, match="SERVER_SLEEP_DB_PATH must be an absolute path"):
        ServerSleepStore()
    assert not (tmp_path / "server" / "data" / "mtl_server.db").exists()

@pytest.mark.skipif(os.name != "nt", reason="Windows compatibility path")
def test_windows_ignores_inherited_app_container_path(tmp_path, monkeypatch):
    fake_module = tmp_path / "checkout" / "server" / "store.py"
    monkeypatch.setattr(store_module, "__file__", str(fake_module))
    monkeypatch.setenv("SERVER_SLEEP_DB_PATH", "/app/server/data/mtl_server.db")
    assert store_module.resolve_server_db_path() == os.path.abspath(fake_module.parent / "data" / "mtl_server.db")

def test_server_database_initialization_failure_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr("server.models.server_schema.ensure_server_schema", lambda _conn: (_ for _ in ()).throw(RuntimeError("schema initialization failed")))
    with pytest.raises(RuntimeError, match="schema initialization failed"):
        ServerSleepStore(str(tmp_path / "failed.db"))

def test_sample_data_initialization_is_idempotent_and_isolated(tmp_path):
    store = ServerSleepStore(str(tmp_path / "seed.db"))
    assert store.create_user("fresh@example.com", "test-password")
    user_id = store.verify_user("fresh@example.com", "test-password")
    assert store.create_user("second@example.com", "test-password")
    second_user_id = store.verify_user("second@example.com", "test-password")
    service = SampleDataInitializationService(store.db_path)
    v2_tables = ("server_exercise_plan_schedule_items", "server_exercise_plan_items", "server_exercise_plan_progress_items", "server_exercise_plan_diet_rules", "server_exercise_plan_score_rules", "server_exercise_plan_category_rules")
    service.ensure_user_sample_data(user_id)
    with sqlite3.connect(store.db_path) as conn:
        first_v2_counts = [conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=? AND plan_version='v2'", (user_id,)).fetchone()[0] for table in v2_tables]
        first_v4_counts = [conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=? AND plan_version='v4'", (user_id,)).fetchone()[0] for table in v2_tables]
        first_v2_events = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND change_id LIKE 'exercise-v2-complete-v1:%'", (user_id,)).fetchone()[0]
        first_v4_events = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND change_id LIKE 'exercise-v4-complete-v1:%'", (user_id,)).fetchone()[0]
    service.ensure_user_sample_data(user_id)
    service.ensure_user_sample_data(second_user_id)
    tables = ("server_categories", "server_learning_objectives", "server_learning_krs", "server_learning_tasks", "server_exercise_plan_versions", "server_sample_data_initializations")
    with sqlite3.connect(store.db_path) as conn:
        counts = [conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (user_id,)).fetchone()[0] for table in tables]
        first_objective = conn.execute("SELECT id FROM server_learning_objectives WHERE user_id=?", (user_id,)).fetchone()[0]
        second_objective = conn.execute("SELECT id FROM server_learning_objectives WHERE user_id=?", (second_user_id,)).fetchone()[0]
        second_kr_ids = {row[0] for row in conn.execute("SELECT id FROM server_learning_krs WHERE user_id=?", (second_user_id,))}
        second_task_kr_ids = {row[0] for row in conn.execute("SELECT kr_id FROM server_learning_tasks WHERE user_id=?", (second_user_id,))}
        first_categories = dict(conn.execute("SELECT c.name,COUNT(*) FROM server_learning_tasks t JOIN server_categories c ON c.id=t.category_id WHERE t.user_id=? GROUP BY c.name", (user_id,)))
        second_category_ids = {row[0] for row in conn.execute("SELECT DISTINCT category_id FROM server_learning_tasks WHERE user_id=?", (second_user_id,))}
        own_second_category_ids = {row[0] for row in conn.execute("SELECT id FROM server_categories WHERE user_id=? AND name IN ('输入','输出')", (second_user_id,))}
    assert counts == [19, 1, 4, 32, 4, 6]
    assert first_v2_counts == [11, 90, 4, 3, 18, 6]
    assert first_v4_counts == [8, 23, 4, 3, 0, 3]
    assert first_v2_events == 133
    assert first_v4_events == 43
    assert first_objective != second_objective
    assert second_task_kr_ids == second_kr_ids
    assert first_categories == {"输入": 20, "输出": 12}
    assert second_category_ids == own_second_category_ids
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT value FROM server_system_config WHERE user_id=? AND key='active_exercise_plan_version'", (user_id,)).fetchone()[0] == "v4"
        assert conn.execute("SELECT exercise_points FROM server_exercise_plan_versions WHERE user_id=? AND version='v1'", (user_id,)).fetchone()[0] == 63
        assert conn.execute("SELECT exercise_points FROM server_exercise_plan_versions WHERE user_id=? AND version='v2'", (user_id,)).fetchone()[0] == 40
        assert conn.execute("SELECT exercise_points FROM server_exercise_plan_versions WHERE user_id=? AND version='v4'", (user_id,)).fetchone()[0] == 75
        assert conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND change_id LIKE 'exercise-v2-complete-v1:%'", (user_id,)).fetchone()[0] == first_v2_events
        assert conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND change_id LIKE 'exercise-v4-complete-v1:%'", (user_id,)).fetchone()[0] == first_v4_events

def _seed_legacy_timer_categories(conn, user_id, names=None):
    names = names or [
        "输入", "输出", "副业生产", "副业营销", "副业研发", "吃饭", "家庭", "娱乐",
        "交通", "个人杂事", "运动", "松鼠病", "状态切换", "睡觉", "拉屎",
    ]
    aliases = {"家庭": "带娃", "车": "交通", "生活杂事": "个人杂事"}
    target = {item["name"]: item for item in DEFAULT_TIMER_CATEGORY_RECORDS}
    for index, name in enumerate(names, 1):
        item = target.get(aliases.get(name, name), target["输入"])
        conn.execute(
            "INSERT INTO server_categories(user_id,name,group_name,icon,color,sort_order,updated_at,pushed_at) VALUES(?,?,?,?,?,?,?,?)",
            (user_id, name, f"legacy-group-{index}", f"legacy-icon-{index}", f"#AA{index:04X}", 100 + index, "2026-08-01 00:00:00", "2026-08-01 00:00:00"),
        )

def test_legacy_timer_categories_upgrade_in_place_preserves_ids_fields_and_history(tmp_path):
    store = ServerSleepStore(str(tmp_path / "legacy-timer-upgrade.db"))
    assert store.create_user("legacy-timer@example.com", "test-password")
    user_id = store.verify_user("legacy-timer@example.com", "test-password")
    service = SampleDataInitializationService(store.db_path)
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        _seed_legacy_timer_categories(conn, user_id)
        before = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM server_categories WHERE user_id=?", (user_id,))}
        traffic_id = next(row_id for row_id, row in before.items() if row["name"] == "交通")
        conn.execute(
            "INSERT INTO server_study_sessions(id,user_id,start_time,end_time,net_duration_minutes,date,category_id,updated_at) VALUES('legacy-session',?,'2026-08-01 08:00','2026-08-01 09:00',60,'2026-08-01',?,'2026-08-01 09:00')",
            (user_id, traffic_id),
        )
        assert service._ensure_timer_categories(conn, user_id) == "upgraded"
        conn.commit()
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        after = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM server_categories WHERE user_id=?", (user_id,))}
        assert len(after) == 19
        assert set(before).issubset(after)
        for row_id, old in before.items():
            assert after[row_id]["icon"] == old["icon"]
            assert after[row_id]["color"] == old["color"]
            assert after[row_id]["group_name"] == old["group_name"]
        assert after[traffic_id]["name"] == "交通"
        assert conn.execute("SELECT category_id FROM server_study_sessions WHERE id='legacy-session'").fetchone()[0] == traffic_id
        names = [row[0] for row in conn.execute("SELECT name FROM server_categories WHERE user_id=? ORDER BY sort_order,id", (user_id,))]
        assert names == [item["name"] for item in DEFAULT_TIMER_CATEGORY_RECORDS]
        snapshot = list(conn.execute("SELECT id,name,icon,color,group_name,sort_order FROM server_categories WHERE user_id=? ORDER BY id", (user_id,)))
        assert service._ensure_timer_categories(conn, user_id) == "upgraded"
        assert snapshot == list(conn.execute("SELECT id,name,icon,color,group_name,sort_order FROM server_categories WHERE user_id=? ORDER BY id", (user_id,)))

@pytest.mark.parametrize(("mutation", "expected"), [
    ("INSERT INTO server_categories(user_id,name,group_name) VALUES(?, '自定义', '自定义')", "skipped_signature_mismatch"),
    ("DELETE FROM server_categories WHERE user_id=? AND name='睡觉'", "skipped_signature_mismatch"),
    ("UPDATE server_categories SET name='未知改名' WHERE user_id=? AND name='睡觉'", "skipped_signature_mismatch"),
    ("UPDATE server_categories SET name='带娃' WHERE user_id=? AND name='娱乐'", "skipped_alias_conflict"),
])
def test_legacy_timer_category_non_strict_sets_are_skipped_without_writes(tmp_path, mutation, expected):
    store = ServerSleepStore(str(tmp_path / f"skip-{expected}.db"))
    assert store.create_user(f"{expected}@example.com", "test-password")
    user_id = store.verify_user(f"{expected}@example.com", "test-password")
    service = SampleDataInitializationService(store.db_path)
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        _seed_legacy_timer_categories(conn, user_id)
        conn.execute(mutation, (user_id,))
        before = list(conn.execute("SELECT id,name,icon,color,group_name,sort_order,updated_at,pushed_at FROM server_categories WHERE user_id=? ORDER BY id", (user_id,)))
        assert service._ensure_timer_categories(conn, user_id) == expected
        assert before == list(conn.execute("SELECT id,name,icon,color,group_name,sort_order,updated_at,pushed_at FROM server_categories WHERE user_id=? ORDER BY id", (user_id,)))
        assert service._ensure_timer_categories(conn, user_id) == expected

def test_legacy_timer_category_upgrade_rolls_back_on_publish_failure(tmp_path, monkeypatch):
    store = ServerSleepStore(str(tmp_path / "timer-upgrade-rollback.db"))
    assert store.create_user("rollback@example.com", "test-password")
    user_id = store.verify_user("rollback@example.com", "test-password")
    service = SampleDataInitializationService(store.db_path)
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        _seed_legacy_timer_categories(conn, user_id)
        conn.commit()
        before = list(conn.execute("SELECT * FROM server_categories WHERE user_id=? ORDER BY id", (user_id,)))
    monkeypatch.setattr(service, "_write_seed_change", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("publish failed")))
    with pytest.raises(RuntimeError, match="publish failed"):
        with sqlite3.connect(store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            service._ensure_timer_categories(conn, user_id)
    with sqlite3.connect(store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert before == list(conn.execute("SELECT * FROM server_categories WHERE user_id=? ORDER BY id", (user_id,)))

def test_learning_seed_missing_category_rolls_back_without_partial_rows(tmp_path):
    store = ServerSleepStore(str(tmp_path / "missing-learning-category.db"))
    assert store.create_user("missing@example.com", "test-password")
    user_id = store.verify_user("missing@example.com", "test-password")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(?,'输入','增益')", (user_id,))
    with pytest.raises(Exception, match="配置缺失"):
        SampleDataInitializationService(store.db_path).ensure_user_sample_data(user_id)
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_learning_objectives WHERE user_id=?", (user_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_learning_tasks WHERE user_id=?", (user_id,)).fetchone()[0] == 0

def test_server_external_rewards_legacy_table_gets_ext_id(tmp_path):
    db_path = tmp_path / "legacy_server_external_rewards.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE server_external_rewards (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            coins REAL NOT NULL,
            status INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute(
        """INSERT INTO server_external_rewards
           (id, user_id, item_type, item_name, coins, status, created_at, updated_at)
           VALUES ('legacy-server-ext-1', 1, 'goal', '旧服务端奖励', 3, 0, '2026-06-06', '2026-06-06')"""
    )
    conn.commit()

    ensure_server_schema(conn)
    row = conn.execute(
        "SELECT ext_id FROM server_external_rewards WHERE id = 'legacy-server-ext-1'"
    ).fetchone()
    conn.close()

    assert row[0] == "legacy-server-ext-1"


def test_legacy_exercise_daily_logs_unique_constraint_is_migrated(tmp_path):
    db_path = tmp_path / "legacy_exercise_daily_logs.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("""
        CREATE TABLE server_exercise_daily_logs (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, date TEXT NOT NULL,
            exercise_type TEXT NOT NULL, duration_minutes INTEGER DEFAULT 0,
            calories REAL DEFAULT 0.0, heart_rate_avg INTEGER,
            created_at TEXT NOT NULL, updated_at TEXT, pushed_at TEXT,
            UNIQUE(user_id, date, exercise_type), FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-06-29')")
    conn.execute("INSERT INTO server_exercise_daily_logs (id,user_id,date,exercise_type,created_at,updated_at) VALUES ('legacy-v0',1,'2026-06-29','sc-0','2026-06-29','2026-06-29')")
    conn.commit()

    ensure_server_schema(conn)
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='server_exercise_daily_logs'").fetchone()[0]
    conn.execute("INSERT INTO server_exercise_daily_logs (id,user_id,date,plan_version,exercise_type,created_at,updated_at) VALUES ('new-v1',1,'2026-06-29','v1','sc-0','2026-06-29','2026-06-29')")
    rows = conn.execute("SELECT id, plan_version FROM server_exercise_daily_logs WHERE exercise_type='sc-0' ORDER BY plan_version").fetchall()
    conn.close()

    assert "UNIQUE(user_id, date, exercise_type)" not in sql
    assert "UNIQUE(user_id, date, plan_version, exercise_type)" in sql
    assert rows == [("legacy-v0", "v0"), ("new-v1", "v1")]


def test_exercise_settlement_completion_columns_are_compatible(tmp_path):
    conn = sqlite3.connect(tmp_path / "exercise_settlement_schema.db")
    ensure_server_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(server_exercise_settlements)")}
    conn.close()
    assert {"is_all_complete", "completion_reward_amount", "completion_reason"} <= columns


def test_sleep_settlement_independent_diary_projection_is_compatible_and_user_scoped(tmp_path):
    conn = sqlite3.connect(tmp_path / "sleep_diary_settlement_schema.db")
    ensure_server_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(server_sleep_score_settlements)")}
    assert {
        "diary_completion_status", "diary_completion_reward_amount",
        "diary_completion_reason", "diary_completion_rule_version",
        "morning_diary_reward_status", "morning_diary_reward_amount",
        "morning_diary_reward_reason", "morning_diary_reward_rule_version",
        "evening_diary_reward_status", "evening_diary_reward_amount",
        "evening_diary_reward_reason", "evening_diary_reward_rule_version",
    } <= columns
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'p', '2026-09-06')")
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (2, 'u2', 'p', '2026-09-06')")
    values = ("{}", "{}", 0, 0, 0, 0, "pending", "", "sleep-score-v2", "2026-09-06", "2026-09-06", "2026-09-06")
    conn.execute("INSERT INTO server_sleep_score_settlements (id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at) VALUES ('s1',1,'2026-09-05',?,?,?,?,?,?,?,?,?,?,?,?)", values)
    conn.execute("INSERT INTO server_sleep_score_settlements (id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at) VALUES ('s2',2,'2026-09-05',?,?,?,?,?,?,?,?,?,?,?,?)", values)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO server_sleep_score_settlements (id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at) VALUES ('s3',1,'2026-09-05',?,?,?,?,?,?,?,?,?,?,?,?)", values)
    ensure_server_schema(conn)
    assert conn.execute("SELECT id,sleep_date FROM server_sleep_score_settlements ORDER BY id").fetchall() == [('s1', '2026-09-05'), ('s2', '2026-09-05')]
    conn.close()


def test_server_version_and_change_log_schema_exists(tmp_path):
    db_path = tmp_path / "versioned_sync_schema.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "server_version_counters" in tables
    assert "server_change_log" in tables
    assert "server_sync_conflicts" in tables

    change_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(server_change_log)").fetchall()
    }
    for col in [
        "server_version",
        "entity_type",
        "entity_id",
        "changed_fields_json",
        "changed_at",
    ]:
        assert col in change_cols

    conflict_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(server_sync_conflicts)").fetchall()
    }
    for col in ["client_base_version", "server_version", "strategy", "result"]:
        assert col in conflict_cols

    conn.close()


def test_sync_hub_accepts_legacy_exercise_checkin_without_log_id(tmp_path):
    db_path = tmp_path / "legacy_exercise_sync.db"
    db = ServerDBWrapper()
    db.log_path = str(db_path)
    conn = sqlite3.connect(db.log_path)
    ensure_server_schema(conn)
    conn.close()

    hub = SyncHub(db)
    ok, rejected = hub.upsert(
        "exercise_checkins",
        {
            "id": "legacy-checkin-1",
            "date": "2026-06-28",
            "plan_version": "v0",
            "item_key": "平板支撑",
            "item_name": "平板支撑",
            "status": 1,
        },
        user_id=1,
    )

    assert ok is True
    assert rejected == []
    conn = sqlite3.connect(db.log_path)
    log_row = conn.execute(
        "SELECT id, exercise_type FROM server_exercise_daily_logs WHERE user_id = 1"
    ).fetchone()
    checkin_row = conn.execute(
        "SELECT log_id FROM server_exercise_checkins WHERE id = 'legacy-checkin-1'"
    ).fetchone()
    conn.close()

    assert log_row is not None
    assert log_row[1] == "平板支撑"
    assert checkin_row[0] == log_row[0]


def test_sync_hub_accepts_versioned_exercise_checkins_with_same_item_key(tmp_path):
    db_path = tmp_path / "versioned_exercise_checkins.db"
    db = ServerDBWrapper()
    db.log_path = str(db_path)
    conn = sqlite3.connect(db.log_path)
    ensure_server_schema(conn)
    conn.close()

    hub = SyncHub(db)
    for version in ("v0", "v1"):
        ok, rejected = hub.upsert("exercise_checkins", {
            "id": f"checkin-{version}",
            "date": "2026-06-29",
            "plan_version": version,
            "item_key": "sc-2026-06-29-0",
            "status": 1,
        }, user_id=1)
        assert ok is True
        assert rejected == []

    conn = sqlite3.connect(db.log_path)
    rows = conn.execute(
        "SELECT plan_version FROM server_exercise_daily_logs WHERE exercise_type='sc-2026-06-29-0' ORDER BY plan_version"
    ).fetchall()
    conn.close()
    assert rows == [("v0",), ("v1",)]


def test_sync_hub_defers_exercise_daily_score_reward_until_next_day(tmp_path):
    db_path = tmp_path / "exercise_daily_score_reward.db"
    db = ServerDBWrapper()
    db.log_path = str(db_path)
    conn = sqlite3.connect(db.log_path)
    ensure_server_schema(conn)
    conn.close()

    hub = SyncHub(db)
    ok, rejected = hub.upsert(
        "exercise_daily_logs",
        {
            "id": "daily-v1-2026-06-29",
            "date": "2026-06-29",
            "plan_version": "v1",
            "day_name": "周一",
            "score_snapshot": '{"total": 86, "cats": {"运动": {"s": 57, "m": 57}}}',
            "created_at": "2026-06-29 20:00:00",
            "updated_at": "2026-06-29 20:00:00",
        },
        user_id=1,
    )

    assert ok is True
    assert rejected == []
    conn = sqlite3.connect(db.log_path)
    row = conn.execute(
        "SELECT amount, source_type, source_id, description FROM server_reward_ledger WHERE source_type = 'exercise_score'"
    ).fetchone()
    conn.close()

    assert row is None


def test_legacy_exercise_daily_logs_gets_plan_version_unique_index(tmp_path):
    db_path = tmp_path / "legacy_exercise_daily_logs.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE server_exercise_daily_logs (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            exercise_type TEXT NOT NULL,
            duration_minutes INTEGER DEFAULT 0,
            calories REAL DEFAULT 0.0,
            heart_rate_avg INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            UNIQUE(user_id, date, exercise_type),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()

    ensure_server_schema(conn)
    indexes = conn.execute("PRAGMA index_list(server_exercise_daily_logs)").fetchall()
    unique_index_names = [row[1] for row in indexes if row[2]]
    indexed_columns = {
        tuple(info[2] for info in conn.execute(f"PRAGMA index_info({name})").fetchall())
        for name in unique_index_names
    }
    conn.close()

    assert ("user_id", "date", "plan_version", "exercise_type") in indexed_columns


def test_provider_fingerprint_columns_exist_without_source_hash(tmp_path):
    db_path = tmp_path / "provider_fingerprint_schema.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)

    expected = {
        "server_tasks": {"source", "source_etag", "source_modified_time"},
        "server_habits": {"source", "raw_json", "source_etag", "source_modified_time"},
        "server_habit_checkins": {"raw_json", "source_modified_time"},
        "server_huawei_sleep_data": {"morning_diary_written_at", "evening_diary_written_at"},
    }
    for table, required_cols in expected.items():
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert required_cols <= cols
        assert "source_hash" not in cols

    conn.close()


def test_provider_mirror_primary_and_parent_keys_are_user_scoped(tmp_path):
    conn = sqlite3.connect(tmp_path / "provider-scoped-schema.db")
    ensure_server_schema(conn)
    for table in ("server_tasks", "server_habits", "server_habit_checkins"):
        primary_key = {
            row[1]: row[5] for row in conn.execute(f"PRAGMA table_info({table})") if row[5]
        }
        assert primary_key == {"user_id": 1, "id": 2}
    habit_foreign_key = [
        row for row in conn.execute("PRAGMA foreign_key_list(server_habit_checkins)")
        if row[2] == "server_habits"
    ]
    assert [(row[3], row[4]) for row in habit_foreign_key] == [
        ("user_id", "user_id"), ("habit_id", "id")
    ]
    unique_columns = {
        tuple(column[2] for column in conn.execute(f"PRAGMA index_info({index[1]})"))
        for index in conn.execute("PRAGMA index_list(server_habit_checkins)") if index[2]
    }
    assert ("user_id", "habit_id", "checkin_date") in unique_columns
    conn.close()


def test_server_version_allocation_is_monotonic(tmp_path):
    db_path = tmp_path / "version_counter.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-06-13 00:00:00')"
    )
    conn.commit()
    conn.close()

    db = ServerDBWrapper()
    db.log_path = str(db_path)

    assert db.allocate_server_version(1) == 1
    assert db.allocate_server_version(1) == 2
    assert db.allocate_server_version(1) == 3


def test_write_server_change_records_versioned_change(tmp_path):
    db_path = tmp_path / "change_log_write.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-06-13 00:00:00')"
    )
    conn.commit()
    conn.close()

    db = ServerDBWrapper()
    db.log_path = str(db_path)
    version = db.write_server_change(
        1,
        "task",
        "task-1",
        "upsert",
        {"title": "安排人工智能训练师学习计划"},
        change_id="op-1",
        device_id="pc-1",
        table_name="server_tasks",
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM server_change_log WHERE user_id = 1 AND change_id = 'op-1'"
    ).fetchone()
    conn.close()

    assert version == 1
    assert row["server_version"] == 1
    assert row["entity_type"] == "task"
    assert row["entity_id"] == "task-1"
    assert row["operation"] == "upsert"
    assert "安排人工智能训练师学习计划" in row["changed_fields_json"]
