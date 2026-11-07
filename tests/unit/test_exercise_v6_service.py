from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import server.server as server_module
from server.domain.diet_habit_migration_service import DietHabitMigrationService
from server.domain.exercise_v4_service import ExerciseV4Service
from server.domain.sample_data_initialization_service import SampleDataInitializationService
from server.store import ServerSleepStore


BJ = timezone(timedelta(hours=8))


def _setup(path):
    store = ServerSleepStore(path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u1','x','2026-10-01')")
    seed = SampleDataInitializationService(path)
    seed.ensure_user_sample_data(1)
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_plan_versions WHERE user_id=1 AND version='v6'").fetchone()[0] == 1
    with store._transact() as conn:
        migration = DietHabitMigrationService(lambda *args: None)
        now = datetime.now(BJ) - timedelta(days=2)
        migration.switch_date(conn, 1, now)
        migration.ensure_definitions(conn, 1, datetime.now(BJ))
    seed.ensure_v6_for_user(1)
    with store._connect() as conn:
        cutoff = datetime.fromisoformat(conn.execute("SELECT value FROM server_system_config WHERE user_id=1 AND key='exercise_v6_effective_date'").fetchone()[0]).date()
        assert cutoff == datetime.now(BJ).date()
    return store, seed, cutoff


def test_v6_publish_is_immediate_without_diet_habits_and_defers_existing_v5_day(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u1','x','2026-10-01')")
        today = datetime.now(BJ).date().isoformat()
        conn.execute("""INSERT INTO server_exercise_daily_logs
            (id,user_id,date,plan_version,exercise_type,created_at,updated_at)
            VALUES ('existing-v5',1,?,'v5','daily',?,?)""", (today, today, today))
    seed = SampleDataInitializationService(tmp_db_path)
    seed.ensure_user_sample_data(1)
    seed.ensure_v6_for_user(1)
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_habits WHERE user_id=1 AND id LIKE 'diet-v5:%'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_plan_versions WHERE user_id=1 AND version='v6'").fetchone()[0] == 1
        cutoff = conn.execute("SELECT value FROM server_system_config WHERE user_id=1 AND key='exercise_v6_effective_date'").fetchone()[0]
        assert cutoff == (datetime.now(BJ).date() + timedelta(days=1)).isoformat()
        assert server_module._exercise_active_plan(conn, 1, today) == "v5"
        assert server_module._exercise_active_plan(conn, 1, cutoff) == "v6"


def test_v6_cutover_rest_and_partial_score_leave_v5_history_intact(tmp_db_path):
    store, seed, cutoff = _setup(tmp_db_path)
    old_date = (cutoff - timedelta(days=1)).isoformat()
    rest_day = cutoff + timedelta(days=(7 - cutoff.weekday()) % 7)
    monday, tuesday = rest_day.isoformat(), (rest_day + timedelta(days=1)).isoformat()
    with store._transact() as conn:
        assert server_module._exercise_active_plan(conn, 1, old_date) == "v5"
        assert server_module._exercise_active_plan(conn, 1, monday) == "v6"
        v5 = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
        old_score = v5.settle(conn, 1, old_date, datetime.combine(cutoff, datetime.min.time(), BJ))
        v6 = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v6")
        rest = v6.settle(conn, 1, monday, datetime.combine(rest_day, datetime.min.time(), BJ))
        partial = v6.settle(conn, 1, tuesday, datetime.combine(rest_day + timedelta(days=1), datetime.min.time(), BJ))
        assert rest["cats"] == {"运动训练": {"s": 0.0, "m": 0.0}}
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_completion_reward' AND target_date=?", (monday,)).fetchone()[0] == 0
        assert partial["cats"]["运动训练"] == {"s": 0.0, "m": 100.0}
        assert v5.settle(conn, 1, old_date, datetime.combine(cutoff, datetime.min.time(), BJ)) == old_score
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_diet_checkins WHERE plan_version='v6'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_deadline_facts WHERE plan_version='v6'").fetchone()[0] == 0


def test_v6_rest_day_has_no_zero_checkin_penalty_but_training_day_keeps_it(tmp_db_path):
    store, _, cutoff = _setup(tmp_db_path)
    rest_day = cutoff + timedelta(days=(7 - cutoff.weekday()) % 7)
    with store._transact() as conn:
        assert server_module._settle_zero_exercise_checkin_penalty_in_txn(conn, 1, rest_day.isoformat()) is False
        tuesday = (rest_day + timedelta(days=1)).isoformat()
        assert server_module._settle_zero_exercise_checkin_penalty_in_txn(conn, 1, tuesday) is True
        assert server_module._settle_zero_exercise_checkin_penalty_in_txn(conn, 1, tuesday) is False
        amount = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_zero_checkin_penalty' AND target_date=?", (tuesday,)).fetchone()[0]
        assert amount == -200


def test_v6_full_completion_reward_and_seed_are_idempotent_and_habits_stay_independent(tmp_db_path):
    store, seed, cutoff = _setup(tmp_db_path)
    with store._connect() as conn:
        original = conn.execute("SELECT COUNT(*) FROM server_exercise_plan_items WHERE user_id=1 AND plan_version='v6'").fetchone()[0]
    seed.ensure_v6_for_user(1)
    tuesday = cutoff + timedelta(days=(1 - cutoff.weekday()) % 7)
    date = tuesday.isoformat()
    with store._transact() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_plan_items WHERE user_id=1 AND plan_version='v6'").fetchone()[0] == original
        assert conn.execute("SELECT COUNT(*) FROM server_habits WHERE user_id=1 AND id LIKE 'diet-v5:%'").fetchone()[0] == 6
        log_id = f"test-v6-log:{date}"
        conn.execute("INSERT INTO server_exercise_daily_logs(id,user_id,date,plan_version,exercise_type,created_at,updated_at) VALUES (?,1,?,'v6','daily',?,?)",
                     (log_id, date, date, date))
        for row in conn.execute("SELECT sort_order FROM server_exercise_plan_items WHERE user_id=1 AND plan_version='v6' AND day_key='周二' AND variant='gym' AND is_active=1"):
            key = f"ex-{date}-g-{row['sort_order']}"
            conn.execute("INSERT INTO server_exercise_checkins(id,user_id,log_id,plan_version,item_key,status,date,created_at,updated_at) VALUES (?,1,?,'v6',?,1,?,?,?)",
                         (f"check:{key}", log_id, key, date, date, date))
        v6 = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v6")
        now = datetime.combine(tuesday, datetime.min.time(), BJ)
        assert v6.settle(conn, 1, date, now)["cats"]["运动训练"] == {"s": 100.0, "m": 100.0}
        v6.settle(conn, 1, date, now)
        rewards = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_completion_reward' AND target_date=?", (date,)).fetchall()
        assert [row[0] for row in rewards] == [200]
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_diet_checkins WHERE plan_version='v6'").fetchone()[0] == 0


def test_legacy_client_cannot_write_across_v6_cutover(tmp_db_path):
    store, _, cutoff = _setup(tmp_db_path)
    with store._connect() as conn:
        with pytest.raises(HTTPException) as old:
            server_module._exercise_require_writable_version(conn, 1, cutoff.isoformat(), "v5")
        assert old.value.status_code == 409
        with pytest.raises(HTTPException) as early:
            server_module._exercise_require_writable_version(conn, 1, (cutoff - timedelta(days=1)).isoformat(), "v6")
        assert early.value.status_code == 409
        server_module._exercise_require_writable_version(conn, 1, cutoff.isoformat(), "v6")
