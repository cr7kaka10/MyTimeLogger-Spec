from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import server.server as server_module
from server.store import ServerSleepStore


BJ = timezone(timedelta(hours=8))


@pytest.fixture
def account(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    assert store.create_user("zero-exercise-isolated", "test-password")
    with store._connect() as conn:
        return store, conn.execute("SELECT id FROM users WHERE username='zero-exercise-isolated'").fetchone()[0]


@pytest.mark.parametrize("day,penalty", [
    ("2026-11-02", False), ("2026-11-03", True), ("2026-11-04", True),
    ("2026-11-05", True), ("2026-11-06", True), ("2026-11-07", True), ("2026-11-08", True),
])
def test_weekday_gate_and_idempotent_ledger(account, day, penalty, monkeypatch):
    store, user_id = account
    monkeypatch.setattr(server_module, "store", store)
    with store._transact() as conn:
        first = server_module._settle_zero_exercise_checkin_penalty_in_txn(conn, user_id, day)
        second = server_module._settle_zero_exercise_checkin_penalty_in_txn(conn, user_id, day)
        assert (first, second) == (penalty, False)
        rows = conn.execute("SELECT amount,description,target_date FROM server_reward_ledger WHERE source_type='exercise_zero_checkin_penalty'").fetchall()
        assert len(rows) == int(penalty)
        if penalty:
            assert rows[0]["amount"] == -200 and day in rows[0]["description"]
            assert "当天无任何运动训练打卡" in rows[0]["description"]
            assert rows[0]["target_date"] == day


@pytest.mark.parametrize("item_key,status,penalty", [
    ("ex-2026-11-03-g-1", 1, False), ("ex-2026-11-03-r-2", 1, False),
    ("ex-2026-11-03-g-1", 0, True), ("ex-2026-11-03-g-1", -1, True),
    ("sc-2026-11-03-1", 1, True), ("body:weight", 1, True),
])
def test_only_completed_training_checkins_count(account, item_key, status, penalty, monkeypatch):
    store, user_id = account
    monkeypatch.setattr(server_module, "store", store)
    with store._transact() as conn:
        conn.execute("INSERT INTO server_exercise_daily_logs(id,user_id,date,plan_version,exercise_type,created_at) VALUES('log',?,?,'v5','daily',?)", (user_id, "2026-11-03", "2026-11-03"))
        conn.execute("INSERT INTO server_exercise_checkins(id,user_id,log_id,plan_version,item_key,status,date,created_at) VALUES('check',?,'log','v5',?,?,?,?)", (user_id, item_key, status, "2026-11-03", "2026-11-03"))
        assert server_module._settle_zero_exercise_checkin_penalty_in_txn(conn, user_id, "2026-11-03") is penalty


def test_policy_starts_next_beijing_day_and_survives_restart(account, monkeypatch):
    store, user_id = account
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "sync_hub", SimpleNamespace(_notify_clients=lambda *_: None))
    monkeypatch.setattr(server_module, "_backfill_exercise_score_snapshots_in_txn", lambda *_: set())
    monkeypatch.setattr(server_module, "get_user_statistics_start_date", lambda *_: SimpleNamespace(date="2026-11-01"))
    monkeypatch.setattr(server_module, "_beijing_now", lambda: datetime(2026, 11, 3, 12, tzinfo=BJ))
    server_module._settle_completed_exercise_days()
    monkeypatch.setattr(server_module, "_beijing_now", lambda: datetime(2026, 11, 6, 1, tzinfo=BJ))
    server_module._settle_completed_exercise_days()
    server_module._settle_completed_exercise_days()
    with store._connect() as conn:
        policy = conn.execute("SELECT effective_date FROM server_exercise_policy_metadata WHERE policy_key='zero_checkin_penalty_v1'").fetchone()[0]
        days = [row[0] for row in conn.execute("SELECT target_date FROM server_reward_ledger WHERE user_id=? AND source_type='exercise_zero_checkin_penalty' ORDER BY target_date", (user_id,))]
        assert policy == "2026-11-04" and days == ["2026-11-04", "2026-11-05"]
