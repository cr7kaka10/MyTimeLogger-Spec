import asyncio
from datetime import datetime, timedelta, timezone

from server.db_wrapper import ServerDBWrapper
from server.domain.habit_day_ignore_service import HabitDayIgnoreService
from server.sync_hub import SyncHub
from tests.unit.test_habit_local_reward_management import store


def test_ignore_and_revoke_reach_other_client_by_version(store):
    now = lambda: datetime(2026, 10, 31, 18, tzinfo=timezone(timedelta(hours=8)))
    service = HabitDayIgnoreService(store._transact, store._record_server_change, now)
    db = ServerDBWrapper()
    db.log_path = store.db_path
    hub = SyncHub(db, goal_store=store)

    initial = asyncio.run(hub.handle_pull_by_version(0, 1))
    cursor = initial["to_version"]
    assert not initial["tables"].get("habit_day_ignores")
    assert service.set(1, "local_h", "2026-10-31", "ignore-1", True)["is_ignored"]
    ignored = asyncio.run(hub.handle_pull_by_version(cursor, 1))
    assert ignored["tables"]["habit_day_ignores"][0]["is_ignored"] == 1

    cursor = ignored["to_version"]
    assert not service.set(1, "local_h", "2026-10-31", "ignore-2", False)["is_ignored"]
    revoked = asyncio.run(hub.handle_pull_by_version(cursor, 1))
    assert revoked["tables"]["habit_day_ignores"][0]["is_ignored"] == 0
    assert not asyncio.run(hub.handle_pull_by_version(0, 2))["tables"].get("habit_day_ignores")
    assert not service.set(1, "local_h", "2026-10-31", "ignore-1", True)["is_ignored"]
    assert not asyncio.run(hub.handle_pull_by_version(revoked["to_version"], 1))["tables"].get("habit_day_ignores")
