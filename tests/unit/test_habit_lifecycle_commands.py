import asyncio
import pytest
from tests.unit.test_habit_checkin_command_service import _service, _count, HabitClient


@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("confirmed", [False, True])
def test_stale_command_is_terminal_and_cannot_create_history(tmp_path, deleted, confirmed):
    store, service = _service(tmp_path)
    hid = "habit-1"
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


def test_active_provider_habit_is_rejected_without_remote_request(tmp_path):
    store, service = _service(tmp_path)
    with store._transact() as conn:
        conn.execute("UPDATE server_habits SET id='ticktick:1:habit-1',source='ticktick' WHERE id='habit-1'")
    client = HabitClient()
    result = asyncio.run(service.execute(1, "race", "ticktick:1:habit-1", "2026-09-22", 2, client))
    assert result["status"] == "failed" and result["error_code"] == "provider_habit_sync_disabled"
    assert client.calls == 0 and _count(store, "server_habit_checkins") == 0
