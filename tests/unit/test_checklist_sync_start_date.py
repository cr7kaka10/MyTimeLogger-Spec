import asyncio
import json
import sqlite3

import pytest

from server.checklist_sync_start_date import (
    DEFAULT_CHECKLIST_SYNC_START_DATE,
    resolve_checklist_sync_start_date,
)
from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


def _hub(tmp_path):
    db_path = tmp_path / "checklist_start_date.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-07-01')")
    conn.commit()
    conn.close()
    db = ServerDBWrapper()
    db.log_path = str(db_path)
    return db_path, SyncHub(db)


@pytest.mark.parametrize("value", [None, "", "invalid", "2026-02-30"])
def test_invalid_start_date_falls_back_to_default(value):
    assert resolve_checklist_sync_start_date(value).date == DEFAULT_CHECKLIST_SYNC_START_DATE


def test_start_date_derives_beijing_and_ticktick_formats():
    resolved = resolve_checklist_sync_start_date("2026-07-01")

    assert resolved.date == "2026-07-01"
    assert resolved.compact_date == "20260701"
    assert resolved.beijing_start_datetime.isoformat() == "2026-07-01T00:00:00+08:00"
    assert resolved.utc_start_for_ticktick_completed == "2026-06-30T16:00:00+0000"


def test_sync_hub_reads_per_user_start_date_and_falls_back(tmp_path):
    db_path, hub = _hub(tmp_path)
    assert hub._get_checklist_sync_start_date(1).date == "2026-07-01"

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO server_system_config (user_id,key,value,updated_at) VALUES (1,?,?,?)",
        ("checklist_sync_start_date", "invalid", "2026-07-01"),
    )
    conn.commit()
    conn.close()

    assert hub._get_checklist_sync_start_date(1).date == "2026-07-01"


def test_ticktick_task_pull_uses_configured_start_date(tmp_path):
    db_path, hub = _hub(tmp_path)

    class Client:
        completed_start = None

        async def get_projects(self):
            return [{"id": "p1", "name": "收件箱"}]

        async def get_project_data(self, project_id):
            return {"tasks": [
                {"id": "old", "title": "旧任务", "status": 0, "dueDate": "2026-06-30T23:59:59+0800", "etag": "old-etag"},
                {"id": "start", "title": "起点任务", "status": 0, "dueDate": "2026-07-01T00:00:00+0800", "etag": "start-etag"},
            ]}

        async def get_completed_tasks(self, start_time):
            self.completed_start = start_time
            return []

    client = Client()
    asyncio.run(hub._pull_tasks(client, 1))

    conn = sqlite3.connect(db_path)
    ids = {row[0] for row in conn.execute("SELECT id FROM server_tasks WHERE user_id = 1")}
    conn.close()
    assert client.completed_start == "2026-06-30T16:00:00+0000"
    assert "old" not in ids
    assert "start" in ids


def test_ticktick_task_pull_explicitly_reads_inbox_and_preserves_provider_project_id(tmp_path):
    db_path, hub = _hub(tmp_path)

    class Client:
        project_data_calls = []

        async def get_projects(self):
            return [{"id": "p1", "name": "普通项目"}]

        async def get_project_data(self, project_id):
            self.project_data_calls.append(project_id)
            if project_id == "inbox":
                return {"tasks": [{
                    "id": "inbox-task",
                    "title": "收集箱任务",
                    "status": 0,
                    "projectId": "canonical-inbox-project",
                    "dueDate": "2026-07-31T09:00:00+0800",
                    "etag": "inbox-etag",
                }]}
            return {"tasks": []}

        async def get_completed_tasks(self, start_time):
            return []

    client = Client()
    stats = asyncio.run(hub._pull_tasks(client, 1))

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT raw_json FROM server_tasks WHERE user_id=1 AND id='inbox-task'"
    ).fetchone()
    conn.close()
    assert "inbox" in client.project_data_calls
    assert json.loads(row[0])["project_id"] == "canonical-inbox-project"
    assert stats["inbox_requested"] is True
    assert stats["inbox_succeeded"] is True


def test_ticktick_task_pull_deduplicates_listed_inbox(tmp_path):
    _, hub = _hub(tmp_path)

    class Client:
        calls = []

        async def get_projects(self):
            return [{"id": "inbox", "name": "收集箱"}, {"id": "p1", "name": "普通项目"}]

        async def get_project_data(self, project_id):
            self.calls.append(project_id)
            return {"tasks": []}

        async def get_completed_tasks(self, start_time):
            return []

    client = Client()
    asyncio.run(hub._pull_tasks(client, 1))
    assert client.calls.count("inbox") == 1


def test_ticktick_task_pull_can_disable_inbox_read(tmp_path):
    db_path, hub = _hub(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO server_system_config (user_id,key,value,updated_at) VALUES (1,'ticktick_config',?,?)",
        (json.dumps({"access_token": "test", "inbox_pull_enabled": False}), "2026-07-31 12:00:00"),
    )
    conn.commit()
    conn.close()

    class Client:
        calls = []

        async def get_projects(self):
            return [{"id": "p1", "name": "普通项目"}]

        async def get_project_data(self, project_id):
            self.calls.append(project_id)
            return {"tasks": []}

        async def get_completed_tasks(self, start_time):
            return []

    client = Client()
    asyncio.run(hub._pull_tasks(client, 1))
    assert "inbox" not in client.calls


def test_ticktick_task_pull_inbox_failure_keeps_existing_task(tmp_path):
    db_path, hub = _hub(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO server_tasks (id,user_id,title,status,raw_json,source_etag,updated_at) VALUES (?,?,?,?,?,?,?)",
        ("old-inbox", 1, "旧收集箱任务", 0, json.dumps({"project_id": "canonical-inbox-project"}), "old-etag", "2026-07-31 12:00:00"),
    )
    conn.commit()
    conn.close()

    class Client:
        async def get_projects(self):
            return []

        async def get_project_data(self, project_id):
            if project_id == "inbox":
                raise TimeoutError("provider timeout")
            return {"tasks": []}

        async def get_completed_tasks(self, start_time):
            return []

    stats = asyncio.run(hub._pull_tasks(Client(), 1))
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id, deleted_at FROM server_tasks WHERE id='old-inbox'").fetchone()
    conn.close()
    assert row == ("old-inbox", None)
    assert stats["inbox_error"] == "TimeoutError"
    assert stats["deletion_skipped_reason"]


def test_ticktick_task_pull_reserves_budget_for_inbox(tmp_path):
    _, hub = _hub(tmp_path)

    class Client:
        calls = []

        async def get_projects(self):
            return [{"id": f"p{i}", "name": f"项目{i}"} for i in range(25)]

        async def get_project_data(self, project_id):
            self.calls.append(project_id)
            return {"tasks": []}

        async def get_completed_tasks(self, start_time):
            return []

    client = Client()
    stats = asyncio.run(hub._pull_tasks(client, 1))
    assert "inbox" in client.calls
    assert stats["project_budget_truncated"]


def test_ticktick_habit_pull_uses_configured_start_date(tmp_path):
    db_path, hub = _hub(tmp_path)

    class Client:
        checkin_start = None

        async def get_habits(self):
            return [{"id": "h1", "name": "习惯", "status": 0, "sortOrder": 1, "etag": "habit-etag"}]

        async def get_habit_sections(self):
            return []

        async def get_habit_checkins(self, habit_ids, start, end):
            self.checkin_start = start
            return [{"habitId": "h1", "checkins": [
                {"stamp": "20260630", "status": 2, "opTime": "2026-06-30T08:00:00+0800"},
                {"stamp": "20260701", "status": 2, "opTime": "2026-07-01T08:00:00+0800"},
            ]}]

    client = Client()
    asyncio.run(hub._pull_habits(client, 1))

    conn = sqlite3.connect(db_path)
    dates = {row[0] for row in conn.execute("SELECT checkin_date FROM server_habit_checkins WHERE user_id = 1")}
    conn.close()
    assert client.checkin_start == "20260701"
    assert dates == {"2026-07-01"}


def test_task_reward_uses_configured_beijing_start_date(tmp_path):
    db_path, hub = _hub(tmp_path)
    hub._reward_task_if_new("old", "旧任务", {"completedTime": "2026-06-30T08:00:00+0800"}, 1)
    hub._reward_task_if_new("start", "起点任务", {"completedTime": "2026-07-01T00:00:00+0800"}, 1)

    conn = sqlite3.connect(db_path)
    source_ids = {row[0] for row in conn.execute("SELECT source_id FROM server_reward_ledger WHERE user_id = 1")}
    conn.close()
    assert "old" not in source_ids
    assert "start" in source_ids


def test_schema_cleanup_uses_per_user_start_date(tmp_path):
    db_path, _ = _hub(tmp_path)
    conn = sqlite3.connect(db_path)
    now = "2026-07-01 12:00:00"
    conn.execute("INSERT INTO server_system_config (user_id,key,value,updated_at) VALUES (1,'checklist_sync_start_date','2026-07-01',?)", (now,))
    conn.executemany(
        "INSERT INTO server_tasks (id,user_id,title,due_date,updated_at) VALUES (?,?,?,?,?)",
        [("task-old", 1, "旧", "2026-06-30 23:59:59", now), ("task-start", 1, "新", "2026-07-01 00:00:00", now)],
    )
    conn.execute("INSERT INTO server_habits (id,user_id,name,created_at,updated_at) VALUES ('habit',1,'习惯',?,?)", (now, now))
    conn.executemany(
        "INSERT INTO server_habit_checkins (id,user_id,habit_id,checkin_date,updated_at) VALUES (?,?,?,?,?)",
        [("checkin-old", 1, "habit", "2026-06-30", now), ("checkin-start", 1, "habit", "2026-07-01", now)],
    )
    conn.executemany(
        "INSERT INTO server_reward_ledger (id,user_id,amount,source_type,source_id,target_date,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        [("ledger-old", 1, 1, "task_complete", "task-old", "2026-06-30", now, now), ("ledger-start", 1, 2, "task_complete", "task-start", "2026-07-01", now, now)],
    )
    ensure_server_schema(conn)

    assert {row[0] for row in conn.execute("SELECT id FROM server_tasks WHERE user_id=1")} == {"task-start"}
    assert {row[0] for row in conn.execute("SELECT id FROM server_habit_checkins WHERE user_id=1")} == {"checkin-start"}
    assert {row[0] for row in conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=1")} == {"ledger-start"}
    assert conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0] == 2
    conn.close()
