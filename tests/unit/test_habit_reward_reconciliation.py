# -*- coding: utf-8 -*-

import asyncio

from server.db_wrapper import ServerDBWrapper
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


class _HabitClient:
    def __init__(self, op_time="2026-08-23T11:14:00+0000"):
        self.op_time = op_time

    async def get_habits(self):
        return [{"id": "h1", "name": "洗脸", "status": 0, "sortOrder": 1,
                 "etag": "h1-v1", "modifiedTime": "2026-08-23T11:14:00+0000"}]

    async def get_habit_sections(self):
        return []

    async def get_habit_checkins(self, habit_ids, from_stamp, to_stamp):
        checkin = {"stamp": "20260823", "status": 2}
        if self.op_time is not None:
            checkin["opTime"] = self.op_time
        return [{"habitId": "h1", "checkins": [checkin]}]


class _FourHabitClient:
    rows = [("h1", "慎独"), ("h2", "洗脸"), ("h3", "刷牙"), ("h4", "发广告帖")]

    def __init__(self):
        self.checked = False

    async def get_habits(self):
        return [{"id": hid, "name": name, "status": 0, "sortOrder": index,
                 "iconRes": f"habit_internal_{index}", "etag": f"v{index}",
                 "modifiedTime": "2026-09-06T00:00:00+0000"}
                for index, (hid, name) in enumerate(self.rows, 1)]

    async def get_habit_sections(self):
        return []

    async def get_habit_checkins(self, habit_ids, from_stamp, to_stamp):
        if not self.checked:
            return []
        return [{"habitId": hid, "checkins": [{"stamp": "20260906", "status": 2,
                 "opTime": f"2026-09-06T0{index}:00:00+0000"}]}
                for index, (hid, _) in enumerate(self.rows, 1)]


def _store(tmp_path):
    db_path = tmp_path / "habit_reconcile.db"
    store = ServerSleepStore(str(db_path))
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'reconcile','x','2026-08-15')")
    return store


def test_ticktick_unchanged_pull_reconciles_makeup(tmp_path):
    store = _store(tmp_path)
    db = ServerDBWrapper(); db.log_path = str(tmp_path / "habit_reconcile.db")
    hub = SyncHub(db)
    asyncio.run(hub._pull_habits(_HabitClient(), 1))
    with store._transact() as conn:
        conn.execute("UPDATE server_reward_ledger SET amount=.5,description='√ 习惯 [补]洗脸' WHERE source_type='habit_checkin'")
    asyncio.run(hub._pull_habits(_HabitClient(), 1))
    with store._connect() as conn:
        row = conn.execute("SELECT amount,description,occurred_at FROM server_reward_ledger WHERE source_type='habit_checkin'").fetchone()
    assert tuple(row) == (1.0, "√ 习惯 洗脸", "2026-08-23 19:14:00")


def test_ticktick_unknown_actual_time_saves_checkin_without_ledger(tmp_path):
    store = _store(tmp_path)
    db = ServerDBWrapper(); db.log_path = str(tmp_path / "habit_reconcile.db")
    asyncio.run(SyncHub(db)._pull_habits(_HabitClient(None), 1))
    with store._connect() as conn:
        checkin = conn.execute("SELECT status,checkin_time FROM server_habit_checkins").fetchone()
        count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='habit_checkin'").fetchone()[0]
    assert tuple(checkin) == (2, None)
    assert count == 0


def test_four_chinese_habits_use_configured_amounts_on_ticktick_replay_and_pull(tmp_path):
    store = _store(tmp_path)
    db = ServerDBWrapper(); db.log_path = str(tmp_path / "habit_reconcile.db")
    hub, client = SyncHub(db), _FourHabitClient()
    asyncio.run(hub._pull_habits(client, 1))
    with store._transact() as conn:
        habits = conn.execute("SELECT id,name FROM server_habits WHERE user_id=1").fetchall()
        for amount, habit in enumerate(sorted(habits, key=lambda row: row['name']), 1):
            conn.execute("UPDATE server_reward_config SET coins=?,penalty=? WHERE user_id=1 AND item_type='habit' AND item_id=?", (amount, amount, habit['id']))
    client.checked = True
    asyncio.run(hub._pull_habits(client, 1))
    asyncio.run(hub._pull_habits(client, 1))
    with store._connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT amount,description FROM server_reward_ledger WHERE user_id=1 AND source_type='habit_checkin' ORDER BY description")]
    expected = {f"√ 习惯 {habit['name']}": float(index) for index, habit in enumerate(sorted(habits, key=lambda row: row['name']), 1)}
    assert len(rows) == 4 and {row['description']: row['amount'] for row in rows} == expected
    assert all('habit_internal_' not in row['description'] for row in rows) and not any(row['amount'] == 5 and expected[row['description']] != 5 for row in rows)
    pull = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=500, include_ledger_snapshot=True))
    assert {row['description'] for row in pull['ledger_snapshot']['rows'] if row['source_type'] == 'habit_checkin'} == set(expected)
