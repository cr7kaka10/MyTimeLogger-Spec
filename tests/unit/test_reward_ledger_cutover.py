# -*- coding: utf-8 -*-

import json
import sqlite3

import pytest

import server.server as server_app
import server.store as store_module
from server.models.server_schema import ensure_server_schema
from server.store import ServerSleepStore


def _store(tmp_path):
    db_path = tmp_path / "reward_cutover.db"
    store = ServerSleepStore(str(db_path))
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'cutover','x','2026-08-15 00:00:00')")
    return store


def test_goal_cutover_excludes_august_16_and_keeps_august_17_idempotent(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.setattr(store_module, "now_str", lambda: "2026-08-19 00:01:00")
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_goals
            (id,user_id,title,metric,target_value,period,operator,reward_coins,penalty_coins,is_active,created_at,updated_at)
            VALUES('goal-cutover',1,'专注','duration',30,'daily','>=',10,5,1,'2026-08-16','2026-08-16')""")
        for day in ("2026-08-16", "2026-08-17"):
            conn.execute("""INSERT INTO server_study_sessions
                (id,user_id,start_time,end_time,net_duration_minutes,date,updated_at)
                VALUES(?,?,?,?,?,?,?)""", (f"session-{day}", 1, f"{day} 09:00:00", f"{day} 09:30:00", 30, day, day))

    store.auto_settle_goals(1)
    store.auto_settle_goals(1)
    with store._connect() as conn:
        rows = conn.execute("""SELECT target_date, occurred_at, amount FROM server_reward_ledger
            WHERE source_type IN ('goal_reward','goal_penalty') ORDER BY target_date""").fetchall()

    assert [(row[0], row[1], row[2]) for row in rows] == [
        ("2026-08-17", "2026-08-17 00:00:00", 10.0),
        ("2026-08-18", "2026-08-18 00:00:00", -5.0),
    ]


def test_exercise_cutover_backfills_once_with_business_date(tmp_path, monkeypatch):
    store = _store(tmp_path)
    previous_store = server_app.store
    monkeypatch.setattr(server_app, "store", store)
    monkeypatch.setattr(server_app, "_beijing_today", lambda: "2026-08-19")
    try:
        with store._transact() as conn:
            for day in ("2026-08-16", "2026-08-17"):
                conn.execute("""INSERT INTO server_exercise_daily_logs
                    (id,user_id,date,plan_version,day_name,exercise_type,score_snapshot,completed_items,total_items,created_at,updated_at)
                    VALUES(?,?,?,?,?,'daily',?,?,?,?,?)""", (
                        f"exercise-{day}", 1, day, "v1", "周一", json.dumps({"total": 85}), 4, 4, day, day,
                    ))
            store.reward_settlement_service.settle_in_txn(
                conn, 1, -50, "exercise", "v1 周日 10分", "exercise_score",
                "exercise-score:v1:2026-08-16", "2026-08-16", False,
            )
            store.reward_settlement_service.settle_in_txn(
                conn, 1, -5, "goal", "旧目标", "goal_penalty", "old-goal", "2026-08-16", False,
            )
        server_app._settle_completed_exercise_days()
        server_app._settle_completed_exercise_days()
        with store._connect() as conn:
            rows = conn.execute("""SELECT target_date, occurred_at, amount FROM server_reward_ledger
                WHERE source_type IN ('exercise_score','goal_penalty') ORDER BY target_date""").fetchall()
            balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    finally:
        server_app.store = previous_store

    assert [(row[0], row[1], row[2]) for row in rows] == [("2026-08-17", "2026-08-17 00:00:00", 50.0)]
    assert balance == 50.0


@pytest.mark.parametrize("existing_snapshot", [None, {"total": 0}])
def test_exercise_checkins_rebuild_missing_or_stale_daily_snapshot(tmp_path, monkeypatch, existing_snapshot):
    store = _store(tmp_path)
    monkeypatch.setattr(server_app, "store", store)
    monkeypatch.setattr(server_app, "_beijing_today", lambda: "2026-08-19")
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_exercise_plan_versions
            (version,user_id,title,is_active,created_at) VALUES('v1',1,'计划',1,'2026-08-17')""")
        if existing_snapshot is not None:
            conn.execute("""INSERT INTO server_exercise_daily_logs
                (id,user_id,date,plan_version,exercise_type,day_name,completed_items,total_items,score_snapshot,created_at,updated_at)
                VALUES('daily',1,'2026-08-17','v1','daily','一',0,2,?,'2026-08-17','2026-08-17')""",
                (json.dumps(existing_snapshot),))
            store.reward_settlement_service.settle_in_txn(
                conn, 1, -50, "exercise", "v1 一 0分", "exercise_score",
                "exercise-score:v1:2026-08-17", "2026-08-17", False,
            )
        for index in (0, 1):
            conn.execute("""INSERT INTO server_exercise_plan_score_rules
                (id,user_id,plan_version,day_type,sort_order,schedule_index,points,category,created_at)
                VALUES(?,1,'v1','weekday',?,?,50,'运动','2026-08-17')""", (f"rule-{index}", index, index))
            log_id = f"auto-{index}"
            item_key = f"sc-2026-08-17-{index}"
            conn.execute("""INSERT INTO server_exercise_daily_logs
                (id,user_id,date,plan_version,exercise_type,created_at,updated_at)
                VALUES(?,1,'2026-08-17','v1',?,'2026-08-17','2026-08-17')""", (log_id, item_key))
            conn.execute("""INSERT INTO server_exercise_checkins
                (id,user_id,log_id,plan_version,item_key,status,date,created_at,updated_at)
                VALUES(?,1,?,'v1',?,1,'2026-08-17','2026-08-17','2026-08-17')""",
                (f"checkin-{index}", log_id, item_key))

    first_changed = server_app._settle_completed_exercise_days()
    second_changed = server_app._settle_completed_exercise_days()
    with store._connect() as conn:
        daily = conn.execute("""SELECT completed_items,total_items,score_snapshot FROM server_exercise_daily_logs
            WHERE user_id=1 AND date='2026-08-17' AND plan_version='v1' AND exercise_type='daily'""").fetchone()
        rows = conn.execute("SELECT amount,source_id,description FROM server_reward_ledger WHERE source_type='exercise_score'").fetchall()

    assert (daily[0], daily[1], json.loads(daily[2])["total"]) == (2, 2, 100)
    assert (first_changed, second_changed) == (1, 0)
    assert [(row[0], row[1], row[2]) for row in rows] == [
        (80.0, "exercise-score:v1:2026-08-17", "√ 运动 v1 周一 100分"),
    ]


def test_daily_sync_uses_canonical_type_and_existing_id(tmp_path):
    store = _store(tmp_path)
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_exercise_daily_logs
            (id,user_id,date,plan_version,exercise_type,created_at,updated_at)
            VALUES('canonical',1,'2026-08-17','v1','daily','2026-08-17','2026-08-17')""")
        record = server_app.sync_hub._prepare_exercise_record(conn, "exercise_daily_logs", {
            "id": "client-row", "date": "2026-08-17", "plan_version": "v1", "day_name": "一",
        }, 1)
        canonical_id = server_app.sync_hub._canonical_record_id_for_change(
            "exercise_daily_logs", record, 1, "client-row", conn=conn,
        )

    assert record["exercise_type"] == "daily"
    assert record["id"] == "canonical"
    assert canonical_id == "canonical"


def test_habit_actual_time_is_stored_without_sync_time_fallback(tmp_path):
    store = _store(tmp_path)
    with store._transact() as conn:
        store.reward_settlement_service.settle_habit_success_in_txn(
            conn, 1, "habit-1", "晨练", 1, "2026-08-22", occurred_at="2026-08-22 07:15:00",
        )
        store.reward_settlement_service.settle_habit_success_in_txn(
            conn, 1, "habit-2", "读书", 1, "2026-08-22",
        )
        store.reward_settlement_service.settle_habit_success_in_txn(
            conn, 1, "habit-3", "冥想", 1, "2026-08-22",
        )
        store.reward_settlement_service.settle_habit_success_in_txn(
            conn, 1, "habit-3", "冥想", 1, "2026-08-22", occurred_at="2026-08-22 21:30:00",
        )
    with store._connect() as conn:
        rows = conn.execute("SELECT source_id, occurred_at FROM server_reward_ledger WHERE source_type='habit_checkin' ORDER BY source_id").fetchall()

    assert [(row[0], row[1]) for row in rows] == [
        ("habit-1", "2026-08-22 07:15:00"),
        ("habit-2", None),
        ("habit-3", "2026-08-22 21:30:00"),
    ]
