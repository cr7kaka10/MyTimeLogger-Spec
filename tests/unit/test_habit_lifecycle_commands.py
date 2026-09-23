import asyncio
import pytest
from tests.unit.test_habit_checkin_command_service import _service, _count, HabitClient


@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("confirmed", [False, True])
def test_stale_command_is_terminal_and_cannot_create_history(tmp_path, deleted, confirmed):
    store, service = _service(tmp_path)
    hid = "ticktick:1:habit-1"
    service._commands.create_or_get(1, "stale", hid, "2026-09-22", 2)
    if confirmed:
        service._commands.mark(1, "stale", "provider_confirmed")
    with store._transact() as conn:
        conn.execute("DELETE FROM server_habits" if deleted else "UPDATE server_habits SET is_active=1")
    client = HabitClient()
    for _ in range(2):
        result = asyncio.run(service.execute(1, "stale", hid, "2026-09-22", 2, client))
        assert result["status"] == "failed"
        assert result["error_code"] == ("habit_not_found" if deleted else "habit_archived")
    assert client.calls == 0
    assert _count(store, "server_habit_checkins") == _count(store, "server_reward_ledger") == 0


def test_archive_during_provider_request_blocks_finalize(tmp_path):
    store, service = _service(tmp_path)
    class ArchivingClient(HabitClient):
        async def checkin_habit(self, *args):
            await super().checkin_habit(*args)
            with store._transact() as conn:
                conn.execute("UPDATE server_habits SET is_active=1")
    client = ArchivingClient()
    result = asyncio.run(service.execute(1, "race", "ticktick:1:habit-1", "2026-09-22", 2, client))
    assert result["status"] == "failed" and result["error_code"] == "habit_archived"
    assert client.calls == 1 and _count(store, "server_habit_checkins") == 0
