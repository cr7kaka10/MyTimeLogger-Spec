from datetime import datetime, timedelta, timezone

import pytest

from server.domain.diet_habit_migration_service import DietHabitMigrationService, RULES, WINDOWS
from server.domain.timed_habit_service import TimedHabitService
from server.store import ServerSleepStore


TZ = timezone(timedelta(hours=8))


def test_diet_definitions_exist_on_rest_day_before_daily_activation(tmp_path):
    store = ServerSleepStore(str(tmp_path / "rest.db"))
    store.create_user("rest@example.test", "password")
    migration = DietHabitMigrationService(lambda conn, user, table, key: None)
    monday = datetime(2026, 11, 2, 10, tzinfo=TZ)
    with store._transact() as conn:
        assert migration.switch_date(conn, 1, monday) == "2026-11-03"
        assert migration.ensure_definitions(conn, 1, monday)
        assert not migration.ensure_definitions(conn, 1, monday)
        assert not migration.ensure_day(conn, 1, "2026-11-02", monday)
        assert conn.execute("SELECT COUNT(*) FROM server_habits WHERE user_id=1 AND source='system'").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM server_habit_windows WHERE user_id=1").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM server_habit_checkins WHERE user_id=1").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1").fetchone()[0] == 0


def test_diet_cutover_rest_day_and_single_timeout_penalty(tmp_path):
    store = ServerSleepStore(str(tmp_path / "diet.db"))
    store.create_user("diet@example.test", "password")
    migration = DietHabitMigrationService(lambda conn, user, table, key: None)
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_exercise_plan_items
            (id,user_id,plan_version,day_key,variant,section,sort_order,name,created_at,updated_at)
            VALUES ('monday',1,'v5','周一','gym','warmup',0,'训练','2026-11-01','2026-11-01')""")
        assert migration.switch_date(conn, 1, datetime(2026, 11, 1, 12, tzinfo=TZ)) == "2026-11-02"
        assert not migration.ensure_day(conn, 1, "2026-11-01")
        assert migration.ensure_day(conn, 1, "2026-11-02")
        assert not migration.ensure_day(conn, 1, "2026-11-02")
        rows = conn.execute("SELECT id FROM server_habits WHERE user_id=1 AND source='system'").fetchall()
        assert {r[0] for r in rows} == {f"diet-v5:{rule}" for rule in RULES}
        assert [r[0] for r in conn.execute("SELECT end_minute FROM server_habit_windows WHERE user_id=1 ORDER BY rowid")] == [v[1] for v in WINDOWS]
        conn.execute("UPDATE server_exercise_plan_items SET is_active=0 WHERE user_id=1")
        with pytest.raises(ValueError, match="timed_habit_inactive_day"):
            store.habit_domain_service.timed_checkin_guard(conn, 1, "diet-v5:no_snacks", "2026-11-02", 2)
    run = TimedHabitService(store._transact, store.habit_domain_service,
        now_fn=lambda: datetime(2026, 11, 2, 20, tzinfo=TZ), wallet=store.reward_wallet_service,
        record_change=lambda conn, user, table, key: None)
    assert run.run(1) == set()
    with store._transact() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_habit_checkins WHERE user_id=1").fetchone()[0] == 0
        conn.execute("UPDATE server_exercise_plan_items SET is_active=1 WHERE user_id=1")
        with pytest.raises(ValueError, match="timed_habit_system_manual_failure"):
            store.habit_domain_service.timed_checkin_guard(conn, 1, "diet-v5:breakfast_on_time", "2026-11-02", 1)
    assert run.run(1) == {1}
    assert run.run(1) == set()
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_habit_checkins WHERE user_id=1 AND status=1").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_diet_penalty'").fetchone()[0] == 3
        assert conn.execute("SELECT SUM(amount) FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_diet_penalty'").fetchone()[0] == -60
