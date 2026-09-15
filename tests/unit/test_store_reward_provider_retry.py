import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

from server.db_wrapper import ServerDBWrapper
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


def test_successful_provider_habit_pull_retries_store_initialization(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    assert store.create_user("provider@example.com", "password")
    user_id = store.verify_user("provider@example.com", "password")
    client = SimpleNamespace(
        get_habits=AsyncMock(return_value=[
            {"id": "brush", "name": "刷牙", "status": 0, "etag": "brush-v1", "modifiedTime": "2026-08-04T00:00:00+0800"},
            {"id": "face", "name": "洗脸", "status": 0, "etag": "face-v1", "modifiedTime": "2026-08-04T00:00:00+0800"},
        ]),
        get_habit_sections=AsyncMock(return_value=[]),
        get_habit_checkins=AsyncMock(return_value=[]),
    )
    hub = SyncHub(ServerDBWrapper(tmp_db_path))
    asyncio.run(hub._pull_habits(client, user_id))
    with sqlite3.connect(tmp_db_path) as conn:
        rewards = conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=?", (user_id,)).fetchone()[0]
        marker = conn.execute("SELECT COUNT(*) FROM server_sample_data_initializations WHERE user_id=? AND module='store_rewards'", (user_id,)).fetchone()[0]
    assert rewards == 3 and marker == 1
