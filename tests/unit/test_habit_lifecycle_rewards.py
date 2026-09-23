import asyncio
import pytest
from server.db_wrapper import ServerDBWrapper
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


class Client:
    blocks = [{"habitId": "h", "checkins": [{"stamp": "20260922", "status": 2,
                "opTime": "2026-09-22T10:00:00+0000"}]}]
    sections_fail = False
    etag = "v1"
    async def get_habits(self):
        return [{"id": "h", "name": "阅读", "status": 0, "etag": self.etag}]
    async def get_habit_sections(self):
        if self.sections_fail:
            raise RuntimeError("unavailable")
        return []
    async def get_habit_checkins(self, *args):
        return self.blocks


@pytest.mark.parametrize("blocks", [[], [{"habitId": "h", "checkins": []}]])
def test_incomplete_checkins_preserve_history_and_rewards(tmp_path, blocks):
    store = ServerSleepStore(str(tmp_path / "lifecycle.db"))
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES(1,'owner','x','2026-09-22')")
    db = ServerDBWrapper(); db.log_path = store.db_path
    hub, client = SyncHub(db), Client()
    asyncio.run(hub._pull_habits(client, 1))
    with store._transact() as conn:
        before = list(map(tuple, conn.execute("SELECT * FROM server_reward_ledger")))
        assert before
        conn.execute("INSERT INTO server_categories(id,user_id,name,group_name) VALUES(999,1,'读书','学习')")
        conn.execute("UPDATE server_habits SET category_id=999")
    client.blocks, client.sections_fail, client.etag = blocks, True, "v2"
    stats = asyncio.run(hub._pull_habits(client, 1))
    with store._connect() as conn:
        assert conn.execute("SELECT status FROM server_habit_checkins").fetchone()[0] == 2
        assert list(map(tuple, conn.execute("SELECT * FROM server_reward_ledger"))) == before
        assert conn.execute("SELECT category_id FROM server_habits").fetchone()[0] == 999
    assert stats["complete"] is False
    assert stats["section_error"]["code"] == "habit_sections_failed"
    assert stats["missing_checkin_blocks"] == (0 if blocks else 1)
