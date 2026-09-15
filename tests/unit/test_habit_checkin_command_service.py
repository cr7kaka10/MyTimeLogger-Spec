import asyncio

import httpx

from server.domain.habit_checkin_command_service import HabitCheckinCommandService
from server.domain.reward_config_service import RewardConfigService
from server.db_wrapper import ServerDBWrapper
from server.models.habit_checkin_command_store import HabitCheckinCommandStore
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


class HabitClient:
    def __init__(self, timeout=False):
        self.calls = 0
        self.requests = []
        self.timeout = timeout

    async def checkin_habit(self, habit_id, stamp, status, value):
        self.calls += 1
        self.requests.append((habit_id, stamp, status, value))
        if self.timeout:
            raise httpx.TimeoutException("timeout")
        return {"habit_id": habit_id, "stamp": stamp, "status": status, "value": value}


def _service(tmp_path):
    store = ServerSleepStore(str(tmp_path / "habit-command.db"))
    store.create_user("owner@example.test", "password")
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_habits (id,user_id,name,icon,difficulty,is_active,created_at,updated_at)
               VALUES ('ticktick:1:habit-1',1,'测试习惯','x','medium',1,'2026-08-01 09:00:00','2026-08-01 09:00:00')"""
        )
        RewardConfigService().ensure_item(conn, 1, "habit", "ticktick:1:habit-1", difficulty="medium")
    commands = HabitCheckinCommandStore(store._connect)
    return store, HabitCheckinCommandService(store._transact, store.habit_domain_service, commands)


def _count(store, table):
    conn = store._connect()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_confirmed_checkin_and_cancel_share_one_server_truth(tmp_path):
    store, service = _service(tmp_path)
    client = HabitClient()
    checked = asyncio.run(service.execute(1, "check-1", "ticktick:1:habit-1", "2026-08-01", 2, client))
    repeated = asyncio.run(service.execute(1, "check-1", "ticktick:1:habit-1", "2026-08-01", 2, client))
    assert checked["status"] == repeated["status"] == "confirmed"
    assert client.calls == 1 and _count(store, "server_habit_checkins") == 1
    assert _count(store, "server_reward_ledger") == 1
    with store._connect() as conn:
        changed_tables = {row[0] for row in conn.execute("SELECT table_name FROM server_change_log WHERE user_id=1").fetchall()}
    assert {"server_habit_checkins", "server_reward_ledger", "server_user_wallets"}.issubset(changed_tables)
    wrapper = ServerDBWrapper()
    wrapper.log_path = store.db_path
    pull = asyncio.run(SyncHub(wrapper).handle_pull_by_version(0, user_id=1, limit=100))
    assert pull["tables"]["habit_checkins"] and pull["tables"]["reward_ledger"] and pull["tables"]["user_wallets"]
    cancelled = asyncio.run(service.execute(1, "cancel-1", "ticktick:1:habit-1", "2026-08-01", 0, client))
    assert cancelled["status"] == "confirmed" and client.calls == 2
    assert _count(store, "server_habit_checkins") == _count(store, "server_reward_ledger") == 0


def test_direct_checkin_uses_configured_reward_and_clean_title(tmp_path):
    store, _ = _service(tmp_path)
    habit_id = "ticktick:1:habit-1"
    with store._transact() as conn:
        conn.execute(
            "UPDATE server_habits SET name='慎独', icon='habit_yoga', difficulty='easy' WHERE id=?",
            (habit_id,),
        )
        conn.execute(
            "UPDATE server_reward_config SET coins=1 WHERE user_id=1 AND item_type='habit' AND item_id=?",
            (habit_id,),
        )
    assert store.checkin_habit(1, habit_id, "2026-09-06") is True
    with store._connect() as conn:
        row = conn.execute(
            "SELECT amount,description FROM server_reward_ledger WHERE user_id=1 AND source_type='habit_checkin'"
        ).fetchone()
    assert tuple(row) == (1.0, "√ 习惯 慎独")


def test_provider_timeout_leaves_server_fact_unchanged_and_retryable(tmp_path):
    store, service = _service(tmp_path)
    result = asyncio.run(service.execute(1, "timeout-1", "ticktick:1:habit-1", "2026-08-01", 2, HabitClient(timeout=True)))
    assert result["status"] == "retryable_failed" and result["error_code"] == "provider_timeout"
    assert _count(store, "server_habit_checkins") == _count(store, "server_reward_ledger") == 0


def test_provider_confirmed_command_recovers_without_second_provider_call(tmp_path):
    store, service = _service(tmp_path)
    service._commands.create_or_get(1, "recover-1", "ticktick:1:habit-1", "2026-08-01", 2)
    service._commands.mark(1, "recover-1", "provider_confirmed")
    client = HabitClient()
    recovered = asyncio.run(service.execute(1, "recover-1", "ticktick:1:habit-1", "2026-08-01", 2, client))
    assert recovered["status"] == "confirmed" and client.calls == 0
    assert _count(store, "server_habit_checkins") == _count(store, "server_reward_ledger") == 1


def test_makeup_habit_checkin_does_not_grant_an_item(tmp_path):
    store, service = _service(tmp_path)
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_rewards (id,user_id,title,price,unlock_source_type,unlock_source_id,created_at,updated_at)
               VALUES ('habit-reward',1,'习惯商品',0,'habit','ticktick:1:habit-1','2026-08-01 09:00:00','2026-08-01 09:00:00')"""
        )
    client = HabitClient()
    assert asyncio.run(service.execute(1, "check-used", "ticktick:1:habit-1", "2026-08-01", 2, client))["status"] == "confirmed"
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone() is None


def test_makeup_habit_checkins_cannot_complete_item_threshold(tmp_path):
    store, service = _service(tmp_path)
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_rewards
               (id,user_id,title,price,unlock_source_type,unlock_source_id,unlock_required_count,unlock_threshold_started_at,created_at,updated_at)
               VALUES ('threshold-reward',1,'累计商品',0,'habit','ticktick:1:habit-1',2,'2026-08-01 00:00:00','2026-08-01 09:00:00','2026-08-01 09:00:00')"""
        )
    client = HabitClient()
    assert asyncio.run(service.execute(1, "threshold-first", "ticktick:1:habit-1", "2026-08-01", 2, client))["status"] == "confirmed"
    assert asyncio.run(service.execute(1, "threshold-second", "ticktick:1:habit-1", "2026-08-02", 2, client))["status"] == "confirmed"
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone() is None


def test_confirmed_success_and_failure_can_each_return_to_unchecked(tmp_path):
    store, service = _service(tmp_path)
    client = HabitClient()
    habit_id = "ticktick:1:habit-1"
    assert asyncio.run(service.execute(1, "success", habit_id, "2026-08-01", 2, client))["status"] == "confirmed"
    assert asyncio.run(service.execute(1, "success-reset", habit_id, "2026-08-01", 0, client))["status"] == "confirmed"
    assert _count(store, "server_habit_checkins") == 0
    assert asyncio.run(service.execute(1, "failure", habit_id, "2026-08-02", 1, client))["status"] == "confirmed"
    assert asyncio.run(service.execute(1, "failure-reset", habit_id, "2026-08-02", 0, client))["status"] == "confirmed"
    assert client.calls == 4
    assert client.requests == [
        ("habit-1", "20260801", 2, 1.0),
        ("habit-1", "20260801", 0, 0.0),
        ("habit-1", "20260802", 1, 0.0),
        ("habit-1", "20260802", 0, 0.0),
    ]
    assert _count(store, "server_habit_checkins") == _count(store, "server_reward_ledger") == 0


def test_provider_shaped_success_with_null_legacy_date_can_be_cancelled(tmp_path):
    store, service = _service(tmp_path)
    habit_id = "ticktick:1:habit-1"
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_habit_checkins
               (id,user_id,habit_id,date,checkin_date,checkin_time,status,updated_at)
               VALUES ('provider-success',1,?,NULL,'2026-08-14','10:04:00',2,'2026-08-14 10:04:00')""",
            (habit_id,),
        )
    client = HabitClient()
    result = asyncio.run(service.execute(1, "provider-cancel", habit_id, "2026-08-14", 0, client))
    assert result["status"] == "confirmed"
    assert client.calls == 1
    assert _count(store, "server_habit_checkins") == 0


def test_legacy_date_only_checkin_remains_cancellable(tmp_path):
    store, service = _service(tmp_path)
    habit_id = "ticktick:1:habit-1"
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_habit_checkins
               (id,user_id,habit_id,date,checkin_date,status,updated_at)
               VALUES ('legacy-success',1,?,'2026-08-13',NULL,2,'2026-08-13 10:00:00')""",
            (habit_id,),
        )
    result = asyncio.run(service.execute(1, "legacy-cancel", habit_id, "2026-08-13", 0, HabitClient()))
    assert result["status"] == "confirmed"
    assert _count(store, "server_habit_checkins") == 0


def test_checkin_date_wins_when_legacy_date_conflicts(tmp_path):
    store, service = _service(tmp_path)
    habit_id = "ticktick:1:habit-1"
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_habit_checkins
               (id,user_id,habit_id,date,checkin_date,status,updated_at)
               VALUES ('conflict-success',1,?,'2026-08-13','2026-08-14',2,'2026-08-14 10:00:00')""",
            (habit_id,),
        )
    client = HabitClient()
    wrong_date = asyncio.run(service.execute(1, "conflict-wrong", habit_id, "2026-08-13", 0, client))
    assert wrong_date["error_code"] == "cancel_not_allowed" and client.calls == 0
    confirmed = asyncio.run(service.execute(1, "conflict-right", habit_id, "2026-08-14", 0, client))
    assert confirmed["status"] == "confirmed" and client.calls == 1
    assert _count(store, "server_habit_checkins") == 0
