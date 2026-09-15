# -*- coding: utf-8 -*-
import asyncio
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
import pytest

from server.db_wrapper import ServerDBWrapper
from server.domain.sample_data_initialization_service import SampleDataInitializationService
from server.models.server_schema import ensure_server_schema
from server.store import ServerSleepStore
from server.sync_hub import SyncHub
import server.server as server_module


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(path: str) -> str:
    with open(os.path.join(ROOT_DIR, path), "r", encoding="utf-8") as f:
        return f.read()


def _build_hub(db_path):
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-06-13 00:00:00')"
    )
    conn.commit()
    conn.close()

    db = ServerDBWrapper()
    db.log_path = str(db_path)
    return db, SyncHub(db)


def _atm_activities(count, prefix="activity"):
    return [{"type": f"{prefix}-{index}", "start": f"0{index}:00", "finish": f"0{index}:30", "duration": 1800}
            for index in range(count)]


def test_versioned_pull_returns_only_versions_after_cursor(tmp_path):
    db, hub = _build_hub(tmp_path / "versioned_pull.db")
    db.write_server_change(1, "task", "task-1", "upsert", {"title": "A"})
    db.write_server_change(1, "task", "task-2", "upsert", {"title": "B"})
    db.write_server_change(1, "task", "task-3", "upsert", {"title": "C"})

    result = asyncio.run(hub.handle_pull_by_version(1, user_id=1, limit=10))

    assert result["from_version"] == 1
    assert result["to_version"] == 3
    assert result["has_more"] is False
    assert [row["server_version"] for row in result["changes"]] == [2, 3]
    assert result["diagnostics"]["protocol"] == "server_version"


def test_versioned_pull_supports_paging(tmp_path):
    db, hub = _build_hub(tmp_path / "versioned_pull_paging.db")
    for i in range(3):
        db.write_server_change(1, "task", f"task-{i}", "upsert", {"title": str(i)})

    result = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=2))

    assert result["to_version"] == 2
    assert result["has_more"] is True
    assert len(result["changes"]) == 2


def test_versioned_pull_empty_keeps_cursor(tmp_path):
    db_path = tmp_path / "versioned_pull_empty.db"
    _, hub = _build_hub(db_path)
    with sqlite3.connect(db_path) as conn:
        before = tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("server_change_log", "server_sync_state"))

    result = asyncio.run(hub.handle_pull_by_version(42, user_id=1, limit=10, request_id="unit-sync-run"))

    with sqlite3.connect(db_path) as conn:
        after = tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("server_change_log", "server_sync_state"))

    assert result["from_version"] == 42
    assert result["to_version"] == 42
    assert result["has_more"] is False
    assert result["changes"] == []
    assert result["diagnostics"]["request_id"] == "unit-sync-run"
    assert isinstance(result["diagnostics"]["elapsed_ms"], float)
    assert after == before


def test_changed_sse_event_carries_the_user_server_version(tmp_path):
    db, hub = _build_hub(tmp_path / "versioned_sse.db")
    version = db.write_server_change(1, "goal", "goal-1", "upsert", {"title": "同步"})
    queue = asyncio.Queue()
    hub.subscribe(queue, user_id=1)

    hub._notify_clients(["goals"], user_id=1)

    message = queue.get_nowait()
    assert message["event"] == "changed"
    assert json.loads(message["data"]) == {"tables": ["goals"], "server_version": version}


def test_duplicate_version_diagnostics_are_read_only_and_attribute_source(tmp_path):
    db_path = tmp_path / "duplicate_versions.db"
    db, hub = _build_hub(db_path)
    db.write_server_change(1, "goal", "goal-1", "upsert", {"title": "同一事实"}, device_id="pc")
    db.write_server_change(1, "goal", "goal-1", "upsert", {"title": "同一事实"}, device_id="pc")
    with sqlite3.connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM server_change_log").fetchone()[0]

    diagnostics = hub.get_duplicate_version_diagnostics(1)

    with sqlite3.connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) FROM server_change_log").fetchone()[0]
    assert diagnostics == {
        "user_id": 1,
        "no_op_count": 1,
        "entities": [{"table_name": "server_goals", "record_id": "goal-1", "source": "pc", "write_count": 2, "no_op_count": 1}],
    }
    assert after == before


def test_versioned_cursor_and_backfill_lookup_use_matching_indexes(tmp_path):
    db_path = tmp_path / "versioned_pull_indexes.db"
    _, _ = _build_hub(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor_plan = " ".join(row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM server_change_log WHERE user_id=1 AND server_version>0 ORDER BY server_version LIMIT 1"
        ))
        record_plan = " ".join(row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT 1 FROM server_change_log WHERE user_id=1 AND table_name='atm_summary' AND record_id='1' AND server_version>0"
        ))
    assert "idx_change_log_user_version" in cursor_plan
    assert "idx_change_log_user_record_version" in record_plan


def test_versioned_pull_batches_authoritative_rows_by_table(tmp_path, monkeypatch):
    db, hub = _build_hub(tmp_path / "versioned_pull_batch.db")
    for index in range(3):
        db.write_server_change(1, "task", f"task-{index}", "upsert", {"title": str(index)})
    calls = []
    original = hub.get_records
    monkeypatch.setattr(hub, "get_records", lambda table, ids, user_id: (calls.append((table, ids)), original(table, ids, user_id))[1])

    result = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=10))

    assert result["changes"] and calls == [("tasks", {"task-0", "task-1", "task-2"})]


def test_complete_v2_and_v4_plans_are_available_to_full_and_incremental_pull(tmp_path):
    db_path = tmp_path / "complete_v2_pull.db"
    db, hub = _build_hub(db_path)
    cursor = db.allocate_server_version(1)
    SampleDataInitializationService(str(db_path)).ensure_user_sample_data(1)
    full = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=500))
    delta = asyncio.run(hub.handle_pull_by_version(cursor, user_id=1, limit=500))
    expected = {
        "exercise_plan_schedule_items": 11,
        "exercise_plan_items": 90,
        "exercise_plan_progress_items": 4,
        "exercise_plan_diet_rules": 3,
        "exercise_plan_score_rules": 18,
        "exercise_plan_category_rules": 6,
    }
    for table, count in expected.items():
        assert len({row["id"] for row in full["tables"][table] if row.get("plan_version") == "v2"}) == count
        assert len({row["id"] for row in delta["tables"][table] if row.get("plan_version") == "v2"}) == count
    expected_v4 = {
        "exercise_plan_schedule_items": 8,
        "exercise_plan_items": 23,
        "exercise_plan_progress_items": 4,
        "exercise_plan_diet_rules": 3,
        "exercise_plan_score_rules": 0,
        "exercise_plan_category_rules": 3,
    }
    for table, count in expected_v4.items():
        assert len({row["id"] for row in full["tables"].get(table, []) if row.get("plan_version") == "v4"}) == count
        assert len({row["id"] for row in delta["tables"].get(table, []) if row.get("plan_version") == "v4"}) == count
    assert any(row["key"] == "active_exercise_plan_version" and row["value"] == "v4" for row in delta["tables"]["system_config"])
    repeat = asyncio.run(hub.handle_pull_by_version(delta["to_version"], user_id=1, limit=500))
    assert repeat["changes"] == [] and repeat["tables"] == {}


def test_versioned_pull_ledger_snapshot_is_complete_scoped_and_summarized(tmp_path):
    db_path = tmp_path / "versioned_ledger_snapshot.db"
    _, hub = _build_hub(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (2, 'u2', 'p', '2026-06-13 00:00:00')")
    conn.executemany(
        """INSERT INTO server_reward_ledger
           (id, user_id, amount, source_type, source_id, description, target_date, created_at, updated_at)
           VALUES (?, ?, ?, 'goal_reward', ?, '目标', '2026-08-04', '2026-08-05 00:00:00', '2026-08-05 00:00:00')""",
        [("ledger-income", 1, 2.5, "income"), ("ledger-expense", 1, -1.0, "expense"), ("other-user", 2, 99, "other")],
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_pull_by_version(777, user_id=1, include_ledger_snapshot=True))

    snapshot = result["ledger_snapshot"]
    assert result["to_version"] == 777
    assert {row["id"] for row in snapshot["rows"]} == {"ledger-income", "ledger-expense"}
    assert snapshot["summary"] == {"balance": 1.5, "income": 2.5, "expense": 1.0}
    assert snapshot["integrity"]["count"] == 2
    assert len(snapshot["integrity"]["sha256"]) == 64


def test_study_session_outbox_updates_converge_between_pc_and_android(tmp_path):
    _, hub = _build_hub(tmp_path / "study_session_bidirectional.db")
    session_id = "shared-session-1"

    def payload(summary, updated_at):
        return {
            "id": session_id, "start_time": "2026-07-27 10:00:00", "end_time": "2026-07-27 10:10:00",
            "net_duration_minutes": 10, "net_duration_seconds": 600, "date": "2026-07-27",
            "day_of_week": "星期日", "pause_count": 0, "pause_reasons": "[]",
            "session_summary": summary, "category_id": None, "updated_at": updated_at,
        }

    pc_create = asyncio.run(hub.handle_push([{
        "change_id": "pc-session-create", "device_id": "pc", "table": "study_sessions",
        "operation": "upsert", "payload": payload("PC 新增", "2026-07-27 10:10:00"),
    }], user_id=1))
    assert pc_create["accepted"] == 1
    android_pull = asyncio.run(hub.handle_pull_by_version(0, user_id=1))
    assert android_pull["tables"]["study_sessions"][0]["session_summary"] == "PC 新增"

    android_update = asyncio.run(hub.handle_push([{
        "change_id": "android-session-update", "device_id": "android", "table": "study_sessions",
        "operation": "upsert", "payload": payload("安卓修改", "2026-07-27 10:11:00"),
    }], user_id=1))
    assert android_update["accepted"] == 1
    pc_pull = asyncio.run(hub.handle_pull_by_version(android_pull["to_version"], user_id=1))
    assert pc_pull["tables"]["study_sessions"][0]["session_summary"] == "安卓修改"


def test_new_study_session_recalculates_goals_without_prior_server_record(tmp_path):
    db, _ = _build_hub(tmp_path / "new_study_session_goal_periods.db")
    affected = []

    class GoalStoreSpy:
        def recalculate_goal_periods(self, user_id, dates):
            affected.append((user_id, dates))
            return True

    hub = SyncHub(db, goal_store=GoalStoreSpy())
    result = asyncio.run(hub.handle_push([{
        "change_id": "new-study-session", "device_id": "pc", "table": "study_sessions", "operation": "upsert",
        "payload": {"id": "new-session", "start_time": "2026-07-27 10:00:00", "end_time": "2026-07-27 10:10:00",
                    "net_duration_minutes": 10, "net_duration_seconds": 600, "date": "2026-07-27", "day_of_week": "星期日",
                    "pause_count": 0, "pause_reasons": "[]", "session_summary": "首次创建", "category_id": None,
                    "updated_at": "2026-07-27 10:10:00"},
    }], user_id=1))

    assert result["accepted"] == 1
    assert affected == [(1, {"2026-07-27"})]


def test_study_session_sync_normalizes_business_date_from_longer_covered_day(tmp_path):
    _, hub = _build_hub(tmp_path / "study_session_business_date.db")
    payload = {
        "id": "manual-backfill", "start_time": "2026-08-30 22:30:00", "end_time": "2026-08-31 08:30:00",
        "net_duration_minutes": 600, "net_duration_seconds": 36000, "date": "2026-08-30",
        "day_of_week": "星期一", "pause_count": 0, "pause_reasons": "手动添加", "session_summary": "补录",
        "category_id": None, "updated_at": "2026-08-05 09:00:00",
    }
    result = asyncio.run(hub.handle_push([{
        "change_id": "android-manual-backfill", "device_id": "android", "table": "study_sessions",
        "operation": "upsert", "payload": payload,
    }], user_id=1))
    assert result["accepted"] == 1
    pull = asyncio.run(hub.handle_pull_by_version(0, user_id=1))
    assert pull["tables"]["study_sessions"][0]["date"] == "2026-08-31"
    assert pull["tables"]["study_sessions"][0]["day_of_week"] == "星期一"


def test_study_session_invalid_category_cannot_overwrite_server_reference(tmp_path):
    db, hub = _build_hub(tmp_path / "study_session_category_guard.db")
    conn = sqlite3.connect(db.log_path)
    conn.execute("INSERT INTO server_categories(id,user_id,name,group_name,updated_at) VALUES (47,1,'工作','默认','now')")
    conn.commit(); conn.close()
    base = {"id": "guarded", "start_time": "2026-08-31 10:00:00", "end_time": "2026-08-31 10:01:00", "net_duration_minutes": 1, "net_duration_seconds": 60, "date": "2026-08-31", "day_of_week": "星期一", "pause_count": 0, "pause_reasons": "[]", "session_summary": "work", "updated_at": "2026-08-31 10:01:00"}
    assert asyncio.run(hub.handle_push([{"change_id": "valid", "device_id": "pc", "table": "study_sessions", "operation": "upsert", "payload": {**base, "category_id": 47}}], user_id=1))["accepted"] == 1
    assert asyncio.run(hub.handle_push([{"change_id": "invalid-overwrite", "device_id": "android", "table": "study_sessions", "operation": "upsert", "payload": {**base, "category_id": 18}}], user_id=1))["accepted"] == 1
    pull = asyncio.run(hub.handle_pull_by_version(0, user_id=1))
    assert [row for row in pull["tables"]["study_sessions"] if row["id"] == "guarded"][-1]["category_id"] == 47
    rejected = asyncio.run(hub.handle_push([{"change_id": "invalid-new", "device_id": "android", "table": "study_sessions", "operation": "upsert", "payload": {**base, "id": "invalid-new", "category_id": 18}}], user_id=1))
    assert rejected["accepted"] == 0 and rejected["rejected"][0]["reason"] == "invalid_category_reference"


def test_versioned_first_pull_returns_snapshot_without_change_log(tmp_path):
    db_path = tmp_path / "versioned_pull_snapshot.db"
    db, hub = _build_hub(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_tasks
           (id, user_id, title, priority, status, updated_at)
           VALUES ('server-only-task', 1, '服务端已有任务', 0, 0, '2026-06-13 10:00:00')"""
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=10))

    assert result["diagnostics"]["snapshot"] is True
    assert result["to_version"] > 0
    assert result["tables"]["tasks"][0]["id"] == "server-only-task"
    assert result["tables"]["tasks"][0]["title"] == "服务端已有任务"

    repeat = asyncio.run(hub.handle_pull_by_version(result["to_version"], user_id=1, limit=10))
    assert repeat["changes"] == []
    assert repeat["tables"] == {}


def test_huawei_sleep_save_records_version_change(tmp_path):
    db_path = tmp_path / "versioned_huawei_sleep.db"
    db, hub = _build_hub(db_path)
    cursor = db.allocate_server_version(1)

    store = ServerSleepStore(db_path=str(db_path))
    ok = store.save_huawei_sleep_data(
        1,
        "2026-07-01",
        {
            "sleep_score": 77,
            "total_sleep_min": 343,
            "analysis_html": "<p>睡眠报告</p>",
            "report_status": 1,
        },
    )

    assert ok is True
    result = asyncio.run(hub.handle_pull_by_version(cursor, user_id=1, limit=10))

    assert result["from_version"] == cursor
    assert result["to_version"] > cursor
    assert result["changes"][0]["table_name"] == "huawei_sleep_data"
    assert result["tables"]["huawei_sleep_data"][0]["date"] == "2026-07-01"
    assert result["tables"]["huawei_sleep_data"][0]["sleep_score"] == 77


def test_full_sleep_settlement_and_coin_flow_share_one_core_pull(tmp_path):
    db_path = tmp_path / "sleep_coin_core_pull.db"
    db, hub = _build_hub(db_path)
    cursor = db.allocate_server_version(1)
    store = ServerSleepStore(db_path=str(db_path))
    store.save_huawei_sleep_data(1, "2026-09-08", {
        "report_status": 2, "full_report_state": "generated", "analysis_report": "# 完整报告",
        "sleep_start": "23:00", "sleep_end": "07:00", "sleep_score": 90,
        "deep_sleep_min": 95, "sleep_cycles": 5.5, "awake_min": 10,
        "awake_count": 1, "fall_asleep_min": 20, "wake_up_min": 10,
    }, settle_score=True, report_completed_at="2026-09-08 08:30:00")

    result = asyncio.run(hub.handle_pull_by_version(cursor, user_id=1, limit=100, include_ledger_snapshot=True))

    assert result["to_version"] > cursor
    assert {"huawei_sleep_data", "sleep_score_settlements", "reward_ledger", "user_wallets"} <= result["tables"].keys()
    assert result["tables"]["huawei_sleep_data"][0]["analysis_report"] == "# 完整报告"
    assert result["tables"]["sleep_score_settlements"]
    assert result["ledger_snapshot"]["summary"]["balance"] == result["wallet"]["balance"]


def test_startup_backfills_unversioned_huawei_sleep_rows(tmp_path):
    db_path = tmp_path / "versioned_huawei_sleep_backfill.db"
    db, hub = _build_hub(db_path)
    cursor = db.allocate_server_version(1)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_huawei_sleep_data
           (user_id, date, sleep_score, total_sleep_min, updated_at)
           VALUES (1, '2026-07-01', 77, 343, '2026-07-01 20:26:15')"""
    )
    conn.commit()
    conn.close()

    assert hub.run_startup_sync_migrations() == 1
    result = asyncio.run(hub.handle_pull_by_version(cursor, user_id=1, limit=10))

    assert result["to_version"] > cursor
    assert result["changes"][0]["table_name"] == "huawei_sleep_data"
    assert result["tables"]["huawei_sleep_data"][0]["date"] == "2026-07-01"


def test_atm_summary_keeps_stable_id_and_publishes_upsert(tmp_path):
    db_path = tmp_path / "atm_stable_summary.db"
    db, _ = _build_hub(db_path)
    assert db.save_atm_data(1, "2026-07-20", {"activities": _atm_activities(1)})
    with sqlite3.connect(db_path) as conn:
        first_id = conn.execute("SELECT id FROM server_atm_summary").fetchone()[0]
        conn.execute("UPDATE server_atm_summary SET updated_at='2000-01-01 00:00:00'")
    assert db.save_atm_data(1, "2026-07-20", {"activities": _atm_activities(1, "next")})
    with sqlite3.connect(db_path) as conn:
        summary = conn.execute("SELECT id,updated_at FROM server_atm_summary").fetchone()
        changes = conn.execute("SELECT record_id,operation FROM server_change_log WHERE table_name='server_atm_summary'").fetchall()
    assert summary[0] == first_id and summary[1] != "2000-01-01 00:00:00"
    assert changes[-1] == (str(first_id), "upsert")


def test_atm_activity_replace_set_publishes_delete_and_upsert(tmp_path):
    db_path = tmp_path / "atm_replace_set.db"
    db, _ = _build_hub(db_path)
    db.save_atm_data(1, "2026-07-20", {"activities": _atm_activities(2, "old")})
    with sqlite3.connect(db_path) as conn:
        old_ids = {row[0] for row in conn.execute("SELECT id FROM server_atm_activities")}
    db.save_atm_data(1, "2026-07-20", {"activities": _atm_activities(1, "new")})
    with sqlite3.connect(db_path) as conn:
        new_ids = {row[0] for row in conn.execute("SELECT id FROM server_atm_activities")}
        changes = conn.execute("SELECT record_id,operation FROM server_change_log WHERE table_name='server_atm_activities'").fetchall()
    assert len(new_ids) == 1 and not (old_ids & new_ids)
    assert old_ids <= {int(record_id) for record_id, operation in changes if operation == "delete"}
    assert new_ids <= {int(record_id) for record_id, operation in changes if operation == "upsert"}


def test_atm_save_rolls_back_data_version_and_changes(tmp_path, monkeypatch):
    db_path = tmp_path / "atm_atomic_rollback.db"
    db, _ = _build_hub(db_path)
    db.save_atm_data(1, "2026-07-20", {"activities": _atm_activities(2, "old")})
    with sqlite3.connect(db_path) as conn:
        before = [conn.execute(sql).fetchall() for sql in (
            "SELECT * FROM server_atm_summary", "SELECT * FROM server_atm_activities ORDER BY id",
            "SELECT * FROM server_version_counters", "SELECT * FROM server_change_log ORDER BY server_version")]
    original = db.write_server_change
    calls = 0
    def fail_second_change(*args, **kwargs):
        nonlocal calls
        calls += 1
        version = original(*args, **kwargs)
        if calls == 2:
            raise RuntimeError("injected ATM change failure")
        return version
    monkeypatch.setattr(db, "write_server_change", fail_second_change)
    with pytest.raises(RuntimeError, match="injected ATM change failure"):
        db.save_atm_data(1, "2026-07-20", {"activities": _atm_activities(1, "new")})
    with sqlite3.connect(db_path) as conn:
        after = [conn.execute(sql).fetchall() for sql in (
            "SELECT * FROM server_atm_summary", "SELECT * FROM server_atm_activities ORDER BY id",
            "SELECT * FROM server_version_counters", "SELECT * FROM server_change_log ORDER BY server_version")]
    assert after == before


def test_both_atm_save_entrypoints_publish_same_sequence(tmp_path):
    sequences = []
    for name in ("store", "wrapper"):
        db_path = tmp_path / f"atm_{name}.db"
        db, _ = _build_hub(db_path)
        if name == "store":
            ServerSleepStore(str(db_path)).save_atm_data(1, "2026-07-20", {"activities": _atm_activities(2)})
        else:
            db.save_atm_data(1, "2026-07-20", {"activities": _atm_activities(2)})
        with sqlite3.connect(db_path) as conn:
            sequences.append(conn.execute("SELECT table_name,operation FROM server_change_log ORDER BY server_version").fetchall())
    assert sequences[0] == sequences[1] == [("server_atm_summary", "upsert"), ("server_atm_activities", "upsert"), ("server_atm_activities", "upsert")]


def test_startup_backfills_unversioned_atm_rows_once(tmp_path):
    db_path = tmp_path / "atm_backfill_once.db"
    _, hub = _build_hub(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO server_version_counters VALUES (1,648,'2026-07-21 18:00:00')")
        conn.execute("INSERT INTO server_atm_summary (id,user_id,date,updated_at) VALUES (10,1,'2026-07-20','2026-07-20')")
        for activity in _atm_activities(7):
            conn.execute("""INSERT INTO server_atm_activities
                (user_id,date,activity_type,start_time,end_time,duration_minutes,comment)
                VALUES (1,'2026-07-20',?,?,?,?,?)""", (
                activity["type"], activity["start"], activity["finish"], 30, "",
            ))
    assert hub.run_startup_sync_migrations() == 1
    first = asyncio.run(hub.handle_pull_by_version(648, user_id=1, limit=20))
    with sqlite3.connect(db_path) as conn:
        first_counter = conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=1").fetchone()[0]
    second = asyncio.run(hub.handle_pull_by_version(first["to_version"], user_id=1, limit=20))
    with sqlite3.connect(db_path) as conn:
        second_counter = conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=1").fetchone()[0]
    assert len(first["changes"]) == 8
    assert [len(first["tables"][name]) for name in ("atm_summary", "atm_activities")] == [1, 7]
    assert first_counter == second_counter == 656 and second["changes"] == []


def test_existing_cursor_receives_atm_backfill_then_replace_tombstones(tmp_path):
    db_path = tmp_path / "atm_cursor_convergence.db"
    db, hub = _build_hub(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO server_version_counters VALUES (1,648,'2026-07-21 18:00:00')")
        conn.execute("INSERT INTO server_atm_summary (user_id,date,updated_at) VALUES (1,'2026-07-20','2026-07-20')")
        for activity in _atm_activities(7, "old"):
            conn.execute("""INSERT INTO server_atm_activities
                (user_id,date,activity_type,start_time,end_time,duration_minutes,comment)
                VALUES (1,'2026-07-20',?,?,?,?,?)""", (activity["type"], activity["start"], activity["finish"], 30, ""))
    assert hub.run_startup_sync_migrations() == 1
    backfill = asyncio.run(hub.handle_pull_by_version(648, user_id=1, limit=20))
    local_ids = {int(row["id"]) for row in backfill["tables"]["atm_activities"]}
    db.save_atm_data(1, "2026-07-20", {"activities": _atm_activities(1, "new")})
    delta = asyncio.run(hub.handle_pull_by_version(backfill["to_version"], user_id=1, limit=20))
    for row in delta["tables"]["atm_activities"]:
        if row.get("_sync_operation") == "delete":
            local_ids.discard(int(row["id"]))
        else:
            local_ids.add(int(row["id"]))
    with sqlite3.connect(db_path) as conn:
        authoritative = {row[0] for row in conn.execute("SELECT id FROM server_atm_activities")}
    assert len(backfill["tables"]["atm_summary"]) == 1 and len(local_ids) == 1
    assert local_ids == authoritative


def test_push_huawei_sleep_update_logs_server_canonical_id(tmp_path):
    db_path = tmp_path / "huawei_sleep_canonical_id.db"
    _, hub = _build_hub(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_huawei_sleep_data
           (id, user_id, date, sleep_score, total_sleep_min, updated_at)
           VALUES (9, 1, '2026-07-01', 77, 343, '2026-07-01 07:00:00')"""
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_push([
        {
            "change_id": "pc-morning-diary-1",
            "device_id": "pc",
            "table": "huawei_sleep_data",
            "operation": "upsert",
            "payload": {
                "id": 1,
                "date": "2026-07-01",
                "morning_diary": "晨间日记内容",
                "updated_at": "2026-07-01 08:00:00",
            },
        }
    ], user_id=1))

    assert result["accepted"] == 1
    assert result["operation_results"][0]["record_id"] == "9"

    pulled = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=10))
    assert pulled["tables"]["huawei_sleep_data"][0]["id"] == 9
    assert pulled["tables"]["huawei_sleep_data"][0]["morning_diary"] == "晨间日记内容"


def test_cross_device_independent_diary_pull_uses_server_time_and_stable_rewards(tmp_path, monkeypatch):
    db_path = tmp_path / "independent_diary_pull.db"
    _, hub = _build_hub(db_path)
    clock = {"now": "2026-09-06 12:34:56"}
    monkeypatch.setattr("server.sync_hub._now", lambda: clock["now"])
    operations = [
        {"change_id": "android-morning", "device_id": "android", "table": "huawei_sleep_data", "operation": "upsert",
         "payload": {"id": 1, "date": "2026-09-06", "morning_diary": "晨记", "updated_at": "2026-09-06 08:00:00"}},
        {"change_id": "pc-evening", "device_id": "pc", "table": "huawei_sleep_data", "operation": "upsert",
         "payload": {"id": 2, "date": "2026-09-06", "evening_diary": "晚记", "updated_at": "2026-09-06 12:00:00"}},
    ]
    assert asyncio.run(hub.handle_push(operations, user_id=1))["accepted"] == 2
    asyncio.run(hub.handle_push(operations, user_id=1))

    clock["now"] = "2026-09-06 13:00:00"
    assert asyncio.run(hub.handle_push([{
        "change_id": "pc-morning-edit", "device_id": "pc", "table": "huawei_sleep_data", "operation": "upsert",
        "payload": {"id": 1, "date": "2026-09-06", "morning_diary": "晨记修改", "updated_at": clock["now"]},
    }], user_id=1))["accepted"] == 1

    pulled = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=100))
    sleep = pulled["tables"]["huawei_sleep_data"][0]
    settlement = pulled["tables"]["sleep_score_settlements"][0]
    diary_ledgers = [row for row in pulled["tables"]["reward_ledger"] if row["source_type"] in {"sleep_morning_diary_reward", "sleep_evening_diary_reward"}]
    assert sleep["morning_diary_written_at"] == "2026-09-06 13:00:00"
    assert sleep["evening_diary_written_at"] == "2026-09-06 12:34:56"
    assert settlement["morning_diary_reward_status"] == settlement["evening_diary_reward_status"] == "completed"
    assert settlement["morning_diary_reward_amount"] == settlement["evening_diary_reward_amount"] == 10
    assert sorted((row["id"], row["amount"]) for row in diary_ledgers) == [
        ("sleep-evening-diary-reward:1:2026-09-06:v1", 10.0),
        ("sleep-morning-diary-reward:1:2026-09-06:v1", 10.0),
    ]


def test_versioned_pull_returns_reward_ledger_delete_and_wallet_snapshot(tmp_path):
    db_path = tmp_path / "versioned_reward_delete.db"
    db, hub = _build_hub(db_path)
    db.write_server_change(
        1,
        "reward_ledger",
        "ledger-old",
        "delete",
        {"id": "ledger-old"},
        table_name="server_reward_ledger",
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_user_wallets (user_id, balance, updated_at)
           VALUES (1, 0.0, '2026-06-18 10:00:00')"""
    )
    conn.commit()
    conn.close()
    db.write_server_change(
        1,
        "user_wallets",
        "1",
        "upsert",
        {"user_id": 1, "balance": 0.0, "updated_at": "2026-06-18 10:00:00"},
        table_name="server_user_wallets",
    )

    result = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=10))

    assert result["tables"]["reward_ledger"][0]["_sync_operation"] == "delete"
    assert result["tables"]["reward_ledger"][0]["id"] == "ledger-old"
    assert result["tables"]["user_wallets"][0]["balance"] == 0.0
    assert result["wallet"]["balance"] == 0.0


def test_versioned_snapshot_keeps_user_wallet_primary_key(tmp_path):
    db_path = tmp_path / "versioned_wallet_snapshot.db"
    _, hub = _build_hub(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_user_wallets (user_id, balance, updated_at)
           VALUES (1, 3.5, '2026-06-18 10:00:00')"""
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=10))

    assert result["tables"]["user_wallets"][0]["user_id"] == 1
    assert result["tables"]["user_wallets"][0]["balance"] == 3.5


def test_push_accepts_outbox_op_id_payload_shape(tmp_path):
    db, hub = _build_hub(tmp_path / "outbox_payload_shape.db")

    result = asyncio.run(hub.handle_push([
        {
            "op_id": "client-op-1",
            "table": "tasks",
            "operation": "upsert",
            "payload": {
                "id": "task-from-outbox",
                "title": "客户端 outbox payload",
                "status": 0,
                "priority": 0,
            },
        }
    ], user_id=1, sync_scope="checklist"))

    assert result["accepted"] == 1
    assert result["operation_results"][0]["change_id"] == "client-op-1"
    assert result["operation_results"][0]["status"] == "accepted"

    duplicate = asyncio.run(hub.handle_push([
        {
            "op_id": "client-op-1",
            "table": "tasks",
            "operation": "upsert",
            "payload": {"id": "task-from-outbox", "title": "重复提交"},
        }
    ], user_id=1, sync_scope="checklist"))
    assert duplicate["operation_results"][0]["status"] == "duplicate"


def test_task_completion_rolls_back_when_reward_change_log_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "task_reward_change_log_rollback.db"
    db, hub = _build_hub(db_path)
    original_write = db.write_server_change
    provider_calls = []

    def fail_wallet_change(*args, **kwargs):
        if kwargs.get("table_name") == "server_user_wallets":
            raise RuntimeError("injected reward change log failure")
        return original_write(*args, **kwargs)

    async def unexpected_provider_push(*args, **kwargs):
        provider_calls.append((args, kwargs))
        return {"ok": True, "results": []}

    monkeypatch.setattr(db, "write_server_change", fail_wallet_change)
    monkeypatch.setattr(hub, "_push_and_sync_ticktick", unexpected_provider_push)

    result = asyncio.run(hub.handle_push([{
        "change_id": "task-complete-with-failing-reward-log",
        "table": "tasks",
        "operation": "upsert",
        "payload": {"id": "task-atomic", "title": "原子任务", "status": 2, "priority": 0},
    }], user_id=1))

    conn = sqlite3.connect(db_path)
    counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
        "server_tasks", "server_reward_ledger", "server_user_wallets", "server_change_log",
    )]
    conn.close()

    assert result["accepted"] == 0
    assert result["operation_results"][0]["status"] == "rejected"
    assert counts == [0, 0, 0, 0]
    assert provider_calls == []


def test_local_checklist_records_never_forward_to_ticktick(tmp_path, monkeypatch):
    _, hub = _build_hub(tmp_path / "local_checklist_no_ticktick.db")
    provider_calls = []

    async def unexpected_provider_push(*args, **kwargs):
        provider_calls.append((args, kwargs))
        return {"ok": True, "results": []}

    monkeypatch.setattr(hub, "_push_and_sync_ticktick", unexpected_provider_push)
    created = asyncio.run(hub.handle_push([
        {"change_id": "local-task", "table": "tasks", "operation": "upsert", "payload": {"id": "local_task", "title": "本地任务", "status": 0, "source": "local"}},
        {"change_id": "local-habit", "table": "habits", "operation": "upsert", "payload": {"id": "local_habit", "name": "本地习惯", "source": "local"}},
    ], user_id=1))
    completed = asyncio.run(hub.handle_push([
        {"change_id": "local-task-done", "table": "tasks", "operation": "upsert", "payload": {"id": "local_task", "title": "本地任务", "status": 2, "source": "local"}},
    ], user_id=1))
    assert created["accepted"] == 2
    assert completed["accepted"] == 1
    assert provider_calls == []


def test_habit_checkin_rolls_back_when_reward_change_log_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "habit_reward_change_log_rollback.db"
    db, hub = _build_hub(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_habits
           (id, user_id, name, icon, is_active, difficulty, created_at, updated_at)
           VALUES ('habit-atomic', 1, '原子习惯', '', 1, 'easy', '2026-07-14 10:00:00', '2026-07-14 10:00:00')"""
    )
    conn.commit()
    conn.close()
    original_write = db.write_server_change
    provider_calls = []

    def fail_wallet_change(*args, **kwargs):
        if kwargs.get("table_name") == "server_user_wallets":
            raise RuntimeError("injected habit reward change log failure")
        return original_write(*args, **kwargs)

    async def unexpected_provider_push(*args, **kwargs):
        provider_calls.append((args, kwargs))
        return {"ok": True, "results": []}

    monkeypatch.setattr(db, "write_server_change", fail_wallet_change)
    monkeypatch.setattr(hub, "_push_and_sync_ticktick", unexpected_provider_push)

    result = asyncio.run(hub.handle_push([{
        "change_id": "habit-checkin-with-failing-reward-log",
        "table": "habit_checkins",
        "operation": "upsert",
        "payload": {
            "id": "checkin-atomic", "habit_id": "habit-atomic", "checkin_date": "2026-07-14", "status": 2,
        },
    }], user_id=1))

    conn = sqlite3.connect(db_path)
    counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
        "server_habit_checkins", "server_reward_ledger", "server_user_wallets", "server_change_log",
    )]
    conn.close()

    assert result["accepted"] == 0
    assert result["operation_results"][0]["status"] == "rejected"
    assert counts == [0, 0, 0, 0]
    assert provider_calls == []


def test_exercise_checkin_does_not_require_a_reward_change_log(tmp_path, monkeypatch):
    db_path = tmp_path / "exercise_reward_change_log_rollback.db"
    db, hub = _build_hub(db_path)
    original_write = db.write_server_change

    def fail_wallet_change(*args, **kwargs):
        if kwargs.get("table_name") == "server_user_wallets":
            raise RuntimeError("injected exercise reward change log failure")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(db, "write_server_change", fail_wallet_change)

    result = asyncio.run(hub.handle_push([{
        "change_id": "exercise-checkin-with-failing-reward-log",
        "table": "exercise_checkins",
        "operation": "upsert",
        "payload": {
            "id": "exercise-checkin-atomic", "date": "2026-07-14", "plan_version": "v1",
            "item_key": "squat", "status": 1,
        },
    }], user_id=1))

    conn = sqlite3.connect(db_path)
    counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
        "server_exercise_daily_logs", "server_exercise_checkins", "server_reward_ledger",
        "server_user_wallets", "server_change_log",
    )]
    conn.close()

    assert result["accepted"] == 1
    assert result["operation_results"][0]["status"] == "accepted"
    assert counts[0:2] == [1, 1]
    assert counts[2:4] == [0, 0]


def test_exercise_checkin_push_persists_server_item_score(tmp_path):
    db_path = tmp_path / "exercise_item_score_push.db"
    db, hub = _build_hub(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO server_exercise_plan_versions(version,user_id,title,source_name,is_active,exercise_points,created_at,updated_at) "
            "VALUES('v1',1,'运动','test',1,40,'2026-07-14','2026-07-14')"
        )
        conn.execute(
            "INSERT INTO server_exercise_plan_items(id,user_id,plan_version,day_key,variant,section,sort_order,name,created_at,updated_at) "
            "VALUES('item-0',1,'v1','周二','gym','无氧',0,'高拉训练器（正握）','2026-07-14','2026-07-14')"
        )
        conn.commit()
    result = asyncio.run(hub.handle_push([{
        "change_id": "exercise-score-push",
        "table": "exercise_checkins",
        "operation": "upsert",
        "payload": {
            "id": "exercise-score-checkin", "date": "2026-07-14", "plan_version": "v1",
            "item_key": "ex-2026-07-14-g-0", "status": 1, "completed_time": "08:00",
        },
    }], user_id=1))
    assert result["accepted"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT earned_points,max_points,score_reason FROM server_exercise_item_scores "
            "WHERE user_id=1 AND date='2026-07-14' AND plan_version='v1' AND item_key='ex-2026-07-14-g-0'"
        ).fetchone()
    assert row == (40.0, 40.0, "completed")


def test_exercise_schedule_checkin_push_persists_combined_item_score(tmp_path):
    db_path = tmp_path / "exercise_schedule_score_push.db"
    _, hub = _build_hub(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO server_exercise_plan_versions(version,user_id,title,source_name,is_active,exercise_points,created_at,updated_at) "
            "VALUES('v1',1,'运动','test',1,40,'2026-07-14','2026-07-14')"
        )
        conn.execute(
            "INSERT INTO server_exercise_plan_schedule_items(id,user_id,plan_version,schedule_type,sort_order,time,item,created_at,updated_at) "
            "VALUES('schedule-1',1,'v1','weekday',1,'09:00-10:30','工作第1节','2026-07-14','2026-07-14')"
        )
        conn.executemany(
            "INSERT INTO server_exercise_plan_score_rules(id,user_id,plan_version,day_type,sort_order,schedule_index,points,category,target_time,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [
                ('work', 1, 'v1', 'weekday', 0, 1, 10, '工作', None, '2026-07-14', '2026-07-14'),
                ('timing', 1, 'v1', 'weekday', 1, 1, 1.25, '守时', '10:30', '2026-07-14', '2026-07-14'),
            ],
        )
        conn.commit()
    result = asyncio.run(hub.handle_push([{
        "change_id": "exercise-schedule-score-push",
        "table": "exercise_checkins",
        "operation": "upsert",
        "payload": {
            "id": "exercise-schedule-checkin", "date": "2026-07-14", "plan_version": "v1",
            "item_key": "sc-2026-07-14-1", "status": 1, "completed_time": "10:30",
        },
    }], user_id=1))
    assert result["accepted"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT earned_points,max_points,score_rule_version FROM server_exercise_item_scores "
            "WHERE user_id=1 AND item_key='sc-2026-07-14-1'"
        ).fetchone()
    assert row == (11.25, 11.25, "v1")


def test_exercise_checkin_push_reuses_natural_key_canonical_id(tmp_path):
    db_path = tmp_path / "exercise_checkin_canonical_id.db"
    _, hub = _build_hub(db_path)
    first = asyncio.run(hub.handle_push([{"change_id": "exercise-natural-first", "table": "exercise_checkins", "operation": "upsert", "payload": {
        "id": "pc-checkin", "date": "2026-08-27", "plan_version": "v2", "item_key": "sc-2026-08-27-0", "status": 0,
    }}], user_id=1))
    second = asyncio.run(hub.handle_push([{"change_id": "exercise-natural-second", "table": "exercise_checkins", "operation": "upsert", "payload": {
        "id": "android-checkin", "date": "2026-08-27", "plan_version": "v2", "item_key": "sc-2026-08-27-0", "status": 1, "completed_time": "07:30",
    }}], user_id=1))
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT id,status,completed_time FROM server_exercise_checkins WHERE user_id=1 AND date='2026-08-27' AND plan_version='v2' AND item_key='sc-2026-08-27-0'").fetchall()
    assert first["accepted"] == second["accepted"] == 1
    assert first["operation_results"][0]["record_id"] == second["operation_results"][0]["record_id"] == "pc-checkin"
    assert rows == [("pc-checkin", 1, "07:30")]


def test_exercise_daily_body_fat_survives_old_client_push(tmp_path):
    db_path = tmp_path / "exercise_body_fat_compat.db"
    _, hub = _build_hub(db_path)
    target_date = server_module._beijing_today()
    first = asyncio.run(hub.handle_push([{
        "change_id": "exercise-body-fat-new-client",
        "table": "exercise_daily_logs",
        "operation": "upsert",
        "payload": {"id": "daily-new", "date": target_date, "plan_version": "v1", "weight": 80, "body_fat_rate": 21.5},
    }], user_id=1))
    second = asyncio.run(hub.handle_push([{
        "change_id": "exercise-body-fat-old-client",
        "table": "exercise_daily_logs",
        "operation": "upsert",
        "payload": {"id": "daily-old", "date": target_date, "plan_version": "v1", "weight": 79.5},
    }], user_id=1))
    assert first["accepted"] == second["accepted"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id,weight,body_fat_rate FROM server_exercise_daily_logs WHERE user_id=1 AND date=? AND plan_version='v1' AND exercise_type='daily'",
            (target_date,),
        ).fetchone()
    assert row == ("daily-new", 79.5, 21.5)


def test_v4_diet_pc_and_android_converge_on_one_server_fact(tmp_path, monkeypatch):
    db_path = tmp_path / "exercise_v4_diet_devices.db"
    _, hub = _build_hub(db_path)
    now = datetime(2026, 9, 10, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(server_module, "_beijing_now", lambda: now)
    SampleDataInitializationService(str(db_path)).ensure_user_sample_data(1)
    cursor = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=500))["to_version"]

    pc = asyncio.run(hub.handle_push([{
        "change_id": "pc-diet-toggle",
        "table": "exercise_diet_checkins",
        "operation": "upsert",
        "payload": {"id": "pc-local-id", "date": "2026-09-10", "plan_version": "v4",
                    "rule_key": "no_snacks", "status": "pending", "updated_at": "2026-09-10 18:00:00"},
    }], user_id=1))
    android = asyncio.run(hub.handle_push([{
        "change_id": "android-diet-toggle",
        "table": "exercise_diet_checkins",
        "operation": "upsert",
        "payload": {"id": "android-local-id", "date": "2026-09-10", "plan_version": "v4",
                    "rule_key": "no_snacks", "status": "completed", "occurred_at": "2026-09-10 19:00:00",
                    "updated_at": "2026-09-10 19:00:00"},
    }], user_id=1))

    assert pc["accepted"] == android["accepted"] == 1
    expected_id = "diet:1:2026-09-10:v4:no_snacks"
    assert pc["operation_results"][0]["record_id"] == android["operation_results"][0]["record_id"] == expected_id
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("""SELECT id,status,occurred_at FROM server_exercise_diet_checkins
            WHERE user_id=1 AND date='2026-09-10' AND plan_version='v4' AND rule_key='no_snacks'""").fetchall()
    assert rows == [(expected_id, "completed", "2026-09-10 19:00:00")]
    delta = asyncio.run(hub.handle_pull_by_version(cursor, user_id=1, limit=500))
    pulled = [row for row in delta["tables"]["exercise_diet_checkins"] if row["rule_key"] == "no_snacks"]
    assert len(pulled) == 1 and pulled[0]["status"] == "completed"


def test_v4_diet_user_failure_and_cancel_converge_without_penalty(tmp_path, monkeypatch):
    db_path = tmp_path / "exercise_v4_diet_user_failure.db"
    _, hub = _build_hub(db_path)
    now = datetime(2026, 9, 10, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(server_module, "_beijing_now", lambda: now)
    SampleDataInitializationService(str(db_path)).ensure_user_sample_data(1)
    cursor = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=500))["to_version"]
    failed = asyncio.run(hub.handle_push([{
        "change_id": "diet-user-failed", "table": "exercise_diet_checkins", "operation": "upsert",
        "payload": {"id": "client-failed", "date": "2026-09-10", "plan_version": "v4", "rule_key": "no_snacks",
                    "status": "failed", "occurred_at": "2026-09-10 19:00:00", "updated_at": "2026-09-10 19:00:00"},
    }], user_id=1))
    cancelled = asyncio.run(hub.handle_push([{
        "change_id": "diet-user-cancel", "table": "exercise_diet_checkins", "operation": "upsert",
        "payload": {"id": "client-cancel", "date": "2026-09-10", "plan_version": "v4", "rule_key": "no_snacks",
                    "status": "pending", "updated_at": "2026-09-10 19:01:00"},
    }], user_id=1))
    assert failed["accepted"] == cancelled["accepted"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("""SELECT status,failure_reason,penalty_source_id FROM server_exercise_diet_checkins
            WHERE user_id=1 AND date='2026-09-10' AND rule_key='no_snacks'""").fetchone()
        penalties = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_diet_penalty'").fetchone()[0]
    assert row == ("pending", None, None) and penalties == 0
    delta = asyncio.run(hub.handle_pull_by_version(cursor, user_id=1, limit=500))
    pulled = [row for row in delta["tables"]["exercise_diet_checkins"] if row["rule_key"] == "no_snacks"]
    assert pulled[-1]["status"] == "pending"


def test_v4_diet_sync_rejects_empty_rule_key_and_repairs_plan_projection(tmp_path, monkeypatch):
    db_path = tmp_path / "exercise_v4_diet_empty_key.db"
    _, hub = _build_hub(db_path)
    now = datetime(2026, 9, 10, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(server_module, "_beijing_now", lambda: now)
    initializer = SampleDataInitializationService(str(db_path))
    initializer.ensure_user_sample_data(1)

    with sqlite3.connect(db_path) as conn:
        conn.execute("""UPDATE server_exercise_plan_diet_rules
            SET rule_key = NULL
            WHERE user_id = 1 AND plan_version = 'v4'""")
        conn.commit()

    initializer.ensure_user_sample_data(1)
    snapshot = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=500))
    plan_keys = [
        row["rule_key"]
        for row in snapshot["tables"]["exercise_plan_diet_rules"]
        if row["plan_version"] == "v4"
    ]
    assert plan_keys == ["no_snacks", "no_sugary_drinks", "no_refined_staples"]

    rejected = asyncio.run(hub.handle_push([{
        "change_id": "diet-empty-rule-key",
        "table": "exercise_diet_checkins",
        "operation": "upsert",
        "payload": {
            "id": "diet:1:2026-09-10:v4:",
            "date": "2026-09-10",
            "plan_version": "v4",
            "rule_key": "",
            "status": "completed",
            "occurred_at": "2026-09-10 19:00:00",
            "updated_at": "2026-09-10 19:00:00",
        },
    }], user_id=1))
    assert rejected["accepted"] == 0
    assert rejected["rejected"] == [{
        "table": "exercise_diet_checkins",
        "record_id": "diet:1:2026-09-10:v4:",
        "reason": "unknown_diet_rule",
    }]
    with sqlite3.connect(db_path) as conn:
        empty_facts = conn.execute("""SELECT id FROM server_exercise_diet_checkins
            WHERE user_id = 1 AND date = '2026-09-10' AND plan_version = 'v4' AND rule_key = ''""").fetchall()
    assert empty_facts == []


def test_v4_server_deadline_fact_cannot_be_pushed_by_client(tmp_path):
    _, hub = _build_hub(tmp_path / "exercise_v4_deadline_read_only.db")
    result = asyncio.run(hub.handle_push([{
        "change_id": "client-forged-deadline",
        "table": "exercise_deadline_facts",
        "operation": "upsert",
        "payload": {"id": "forged", "date": "2026-09-10", "plan_version": "v4",
                    "fact_type": "body_metrics", "status": "complete"},
    }], user_id=1))
    assert result["accepted"] == 0 and result["rejected"]


def test_learning_task_rolls_back_when_reward_change_log_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "learning_reward_change_log_rollback.db"
    db, hub = _build_hub(db_path)
    original_write = db.write_server_change

    def fail_wallet_change(*args, **kwargs):
        if kwargs.get("table_name") == "server_user_wallets":
            raise RuntimeError("injected learning reward change log failure")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(db, "write_server_change", fail_wallet_change)

    result = asyncio.run(hub.handle_push([{
        "change_id": "learning-task-with-failing-reward-log",
        "table": "learning_tasks",
        "operation": "upsert",
        "payload": {"id": "learning-atomic", "kr_id": "kr-atomic", "title": "阅读一章", "status": 2},
    }], user_id=1))

    conn = sqlite3.connect(db_path)
    counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
        "server_learning_tasks", "server_reward_ledger", "server_user_wallets", "server_change_log",
    )]
    conn.close()

    assert result["accepted"] == 0
    assert result["operation_results"][0]["status"] == "rejected"
    assert counts == [0, 0, 0, 0]


def test_server_pull_api_declares_version_and_legacy_paths():
    src = _read("server/server.py")

    assert "since_version: int | None = None" in src
    assert "limit: int = 500" in src
    assert "handle_pull_by_version(since_version" in src
    assert '"protocol": "legacy_timestamp"' in src
    assert '"timestamp_since_compatibility"' in src


class _FakeRequest:
    headers = {}


class _FakeSyncHub:
    def __init__(self):
        self.calls = []

    async def force_pull_ticktick(self, user_id, request_id=None):
        self.calls.append(("reconcile", user_id, request_id))
        return {"ok": True, "elapsed_ms": 1.0}

    async def handle_pull_by_version(self, since_version, user_id, limit=500, request_id=None):
        self.calls.append(("version_pull", since_version, user_id, request_id))
        return {
            "changes": [],
            "tables": {},
            "from_version": since_version,
            "to_version": since_version,
            "has_more": False,
            "server_time": "2026-06-17 10:00:00",
            "diagnostics": {"protocol": "server_version"},
            "sync_state": {},
        }


def test_refresh_pull_reconciles_provider_before_version_delta(monkeypatch):
    fake_hub = _FakeSyncHub()
    monkeypatch.setattr(server_module, "sync_hub", fake_hub)

    result = asyncio.run(server_module.sync_pull(
        _FakeRequest(),
        refresh=True,
        since_version=7,
        sync_scope="checklist",
        user={"id": 1},
    ))

    assert fake_hub.calls[0][0] == "reconcile"
    assert fake_hub.calls[1][0] == "version_pull"
    assert fake_hub.calls[1][1] == 7
    assert result["from_version"] == 7
    assert result["to_version"] == 7
    assert result["diagnostics"]["provider_refresh"]["ok"] is True


def test_version_zero_snapshot_contract_keeps_restore_path(tmp_path):
    db_path = tmp_path / "version_zero_snapshot_contract.db"
    db, hub = _build_hub(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_habits
           (id, user_id, name, icon, color, sort_order, is_active, difficulty, created_at, updated_at)
           VALUES ('habit-snapshot', 1, '快照习惯', '', '#A3BE8C', 1, 0, 'easy', '2026-06-01 00:00:00', '2026-06-01 00:00:00')"""
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=10))

    assert result["from_version"] == 0
    assert result["diagnostics"]["snapshot"] is True
    assert result["to_version"] > 0
    assert result["tables"]["habits"][0]["id"] == "habit-snapshot"


def test_versioned_pull_includes_habit_parent_for_checkin_delta(tmp_path):
    db_path = tmp_path / "versioned_habit_parent_backfill.db"
    db, hub = _build_hub(db_path)
    cursor = db.allocate_server_version(1)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_habits
           (id, user_id, name, icon, color, sort_order, is_active, difficulty, created_at, updated_at)
           VALUES ('ticktick:1:habit-a', 1, '洗碗', '', '#A3BE8C', 1, 0, 'easy', '2026-07-08 08:00:00', '2026-07-08 08:00:00')"""
    )
    conn.execute(
        """INSERT INTO server_habit_checkins
           (id, user_id, habit_id, habit_name, checkin_date, checkin_time, status, updated_at)
           VALUES ('checkin-a', 1, 'ticktick:1:habit-a', '洗碗', '2026-07-08', '2026-07-08 22:00:00', 2, '2026-07-08 22:00:00')"""
    )
    conn.commit()
    conn.close()
    db.write_server_change(
        1,
        "habit_checkin",
        "checkin-a",
        "upsert",
        {"id": "checkin-a", "habit_id": "ticktick:1:habit-a"},
        table_name="server_habit_checkins",
    )

    result = asyncio.run(hub.handle_pull_by_version(cursor, user_id=1, limit=10, request_id="habit-parent-unit"))

    assert result["from_version"] == cursor
    assert result["to_version"] > cursor
    assert result["diagnostics"]["dependency_backfilled"] == 1
    assert result["tables"]["habit_checkins"][0]["id"] == "checkin-a"
    assert result["tables"]["habits"][0]["id"] == "ticktick:1:habit-a"
