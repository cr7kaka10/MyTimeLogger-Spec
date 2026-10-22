import asyncio
from datetime import date

from server.domain.habit_auto_failure_service import HabitAutoFailureService, KEY
from server.db_wrapper import ServerDBWrapper
from server.sync_hub import SyncHub
from tests.unit.test_habit_checkin_command_service import _service


def test_rollover_starts_today_then_fails_yesterday_once(tmp_path):
    store, commands = _service(tmp_path)
    auto = HabitAutoFailureService(store._transact, store.habit_domain_service)
    assert auto.run(date(2026, 10, 20)) == 0
    auto = HabitAutoFailureService(store._transact, store.habit_domain_service)  # 重启后从持久水位继续
    assert auto.run(date(2026, 10, 21)) == 1
    assert auto.run(date(2026, 10, 21)) == 0
    with store._connect() as conn:
        row = conn.execute("SELECT status FROM server_habit_checkins WHERE user_id=1 AND habit_id='habit-1'").fetchone()
        assert row["status"] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='habit_fail'").fetchone()[0] == 1
        assert '"done": "2026-10-20"' in conn.execute(
            "SELECT value FROM server_system_config WHERE user_id=1 AND key=?", (KEY,)).fetchone()[0]
        assert {row[0] for row in conn.execute("SELECT table_name FROM server_change_log WHERE user_id=1")} >= {
            "server_habit_checkins", "server_reward_ledger", "server_user_wallets"}
    wrapper = ServerDBWrapper()
    wrapper.log_path = store.db_path
    pull = asyncio.run(SyncHub(wrapper).handle_pull_by_version(0, user_id=1, limit=100))
    assert pull["tables"]["habit_checkins"] and pull["tables"]["reward_ledger"]
    assert asyncio.run(commands.execute(1, "late-1", "habit-1", "2026-10-20", 2))["status"] == "confirmed"
    with store._connect() as conn:
        assert conn.execute("SELECT status FROM server_habit_checkins WHERE user_id=1").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='habit_fail'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='habit_checkin'").fetchone()[0] == 1


def test_rollover_skips_unscheduled_completed_and_archived(tmp_path):
    store, commands = _service(tmp_path)
    auto = HabitAutoFailureService(store._transact, store.habit_domain_service)
    auto.run(date(2026, 10, 20))
    with store._transact() as conn:
        conn.execute("UPDATE server_habits SET repeat_rule='FREQ=WEEKLY;BYDAY=MO' WHERE id='habit-1'")
    assert auto.run(date(2026, 10, 21)) == 0  # 10月20日是周二
    assert asyncio.run(commands.execute(1, "done-1", "habit-1", "2026-10-26", 2))["status"] == "confirmed"
    assert auto.run(date(2026, 10, 27)) == 0  # 已完成的周一不能记失败
    with store._transact() as conn:
        conn.execute("UPDATE server_habits SET is_active=1")
    assert auto.run(date(2026, 11, 3)) == 0


def test_completion_before_rollover_never_creates_failure(tmp_path):
    store, commands = _service(tmp_path)
    auto = HabitAutoFailureService(store._transact, store.habit_domain_service)
    auto.run(date(2026, 10, 20))
    assert asyncio.run(commands.execute(1, "early-1", "habit-1", "2026-10-20", 2))["status"] == "confirmed"
    assert auto.run(date(2026, 10, 21)) == 0
    assert auto.run(date(2026, 10, 21)) == 0
    assert asyncio.run(commands.execute(1, "early-1", "habit-1", "2026-10-20", 2))["status"] == "confirmed"
    with store._connect() as conn:
        assert conn.execute("SELECT status FROM server_habit_checkins WHERE user_id=1").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='habit_fail'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='habit_checkin'").fetchone()[0] == 1


def test_existing_failure_and_user_scope_do_not_duplicate(tmp_path):
    store, commands = _service(tmp_path)
    store.create_user("other@example.test", "password")
    auto = HabitAutoFailureService(store._transact, store.habit_domain_service)
    auto.run(date(2026, 10, 20), user_id=1)
    assert asyncio.run(commands.execute(1, "failed-1", "habit-1", "2026-10-20", 1))["status"] == "confirmed"
    with store._connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='habit_fail'").fetchone()[0]
    assert auto.run(date(2026, 10, 21), user_id=1) == 0
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='habit_fail'").fetchone()[0] == before
        assert conn.execute("SELECT 1 FROM server_system_config WHERE user_id=2 AND key=?", (KEY,)).fetchone() is None
