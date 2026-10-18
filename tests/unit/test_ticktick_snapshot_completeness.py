# -*- coding: utf-8 -*-
import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub
import server.sync_hub as sync_hub_module


def _hub(tmp_path):
    path = tmp_path / "snapshot.db"; conn = sqlite3.connect(path); ensure_server_schema(conn)
    conn.execute("INSERT INTO users (id,username,password_hash,created_at) VALUES (1,'u','p','2026-07-31 00:00:00')")
    conn.commit(); conn.close(); db = ServerDBWrapper(); db.log_path = str(path)
    hub = SyncHub(db); hub._get_ticktick_settings = lambda _uid: SimpleNamespace(inbox_pull_enabled=True)
    db.upsert_task(1, {"id": "keep", "title": "fixture", "priority": 0, "status": 0, "tags": []})
    return path, hub


class _Client:
    def __init__(self, mode): self.mode = mode
    async def get_projects(self): return [{"id": "p1", "name": "提醒"}]
    async def get_project_data(self, project_id):
        if self.mode == "inbox_fail" and project_id == "inbox": raise TimeoutError("inbox")
        if self.mode == "malformed" and project_id == "p1": return []
        return {"tasks": []}
    async def get_completed_tasks(self, _start): return []


@pytest.mark.parametrize("mode", ["inbox_fail", "malformed"])
def test_incomplete_project_payload_never_deletes(tmp_path, mode):
    path, hub = _hub(tmp_path)
    stats = asyncio.run(hub._pull_tasks(_Client(mode), 1))
    with sqlite3.connect(path) as conn:
        deleted_at = conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep'").fetchone()[0]
    assert deleted_at is None
    assert stats["project_failures"] == 1
    assert "project_pull_failed" in stats["deletion_skipped_reason"]


def test_incomplete_snapshot_is_degraded_cooled_down_and_manual_can_retry(tmp_path, monkeypatch):
    path, hub = _hub(tmp_path)
    hub._get_ticktick_settings = lambda _uid: SimpleNamespace(
        enabled=True, access_token="token", host="ticktick.test", verify_tls=True, timeout_seconds=1, inbox_pull_enabled=True,
    )
    async def complete_habits(*_args): return {"complete": True}
    hub._pull_habits = complete_habits

    class Client(_Client):
        instances = 0
        def __init__(self, *_args, **_kwargs): super().__init__("inbox_fail"); type(self).instances += 1
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass

    monkeypatch.setattr(sync_hub_module, "_get_ticktick_client_class", lambda: Client)
    first = asyncio.run(hub.force_pull_ticktick(1, manual=True))
    automatic = asyncio.run(hub.force_pull_ticktick(1))
    manual = asyncio.run(hub.force_pull_ticktick(1, manual=True))

    assert not first["ok"] and not first["complete"] and first["status"] == "degraded" and first["retry_at"]
    assert first["fresh"] is False and first["transport_mode"] == "direct"
    assert first["failure_stage"] == "project_data"
    assert first["tasks"]["candidate_upserts"] == first["tasks"]["published_upserts"] == 0
    assert first["tasks"]["deleted_tasks"] == 0
    assert automatic["skipped"] and automatic["reason"] == "cooldown" and Client.instances == 2
    assert manual["status"] == "degraded"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep'").fetchone()[0] is None
        assert conn.execute("SELECT last_status FROM server_sync_state WHERE user_id=1").fetchone()[0] == "degraded"


def test_task_pull_never_spends_past_the_provider_request_budget(tmp_path, monkeypatch):
    path, hub = _hub(tmp_path)
    monkeypatch.setattr(sync_hub_module, "TICKTICK_PULL_REQUEST_BUDGET", 2)

    class ExpensiveClient(_Client):
        def __init__(self):
            super().__init__("normal")
            self.get_request_attempts = 0
        async def get_projects(self):
            self.get_request_attempts += 2
            return await super().get_projects()
        async def get_project_data(self, project_id):
            self.get_request_attempts += 100
            return await super().get_project_data(project_id)

    stats = asyncio.run(hub._pull_tasks(ExpensiveClient(), 1))

    assert stats["provider_requests"] == stats["request_budget"]
    assert stats["request_budget_exceeded"] and stats["deleted_tasks"] == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep'").fetchone()[0] is None


def test_304_task_partial_snapshot_publishes_safe_active_upserts_only(tmp_path):
    path, hub = _hub(tmp_path)
    def task(prefix, index, status):
        return {"id": f"{prefix}-{index}", "title": prefix, "status": status, "priority": 0, "dueDate": "2099-01-01 00:00:00", "tags": [], "etag": f"{prefix}-{index}", "modifiedTime": "2099-01-01 00:00:00"}
    class Client:
        async def get_projects(self): return [{"id": "timeout", "name": "超时"}, {"id": "active", "name": "进行中"}]
        async def get_project_data(self, project_id):
            if project_id == "timeout": raise TimeoutError("project timeout")
            count = 16 if project_id == "inbox" else 88
            return {"tasks": [task(project_id, index, 0) for index in range(count)]}
        async def get_completed_tasks(self, _start): return [task("done", index, 2) for index in range(200)]

    stats = asyncio.run(hub._pull_tasks(Client(), 1))

    assert stats["active_tasks"] + stats["completed_tasks"] == 304
    assert stats["project_failures"] == 1 and stats["deleted_tasks"] == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep'").fetchone()[0] is None
        assert conn.execute("SELECT COUNT(*) FROM server_tasks WHERE user_id=1").fetchone()[0] == 105
    assert stats["candidate_upserts"] == 304
    assert stats["published_upserts"] == stats["active_task_changes"] == 104
    assert stats["completed_task_changes"] == 0


def test_eight_tomorrow_tasks_across_projects_commit_as_one_complete_snapshot(tmp_path):
    path, hub = _hub(tmp_path)
    class Client:
        async def get_projects(self):
            return [{"id": f"p{i}", "name": f"项目{i}"} for i in range(4)]
        async def get_project_data(self, project_id):
            if project_id == "inbox": return {"tasks": []}
            return {"tasks": [{"id": f"{project_id}-{i}", "title": f"任务{i}", "status": 0,
                    "priority": 0, "dueDate": "2099-01-02 00:00:00", "tags": [],
                    "etag": f"e-{project_id}-{i}", "modifiedTime": "2099-01-01 00:00:00"} for i in range(2)]}
        async def get_completed_tasks(self, _start): return []

    stats = asyncio.run(hub._pull_tasks(Client(), 1))
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM server_tasks WHERE user_id=1 AND deleted_at IS NULL").fetchone()[0]
    assert stats["complete"] and stats["active_tasks"] == 8 and rows == 8


def test_project_list_timeout_is_identified_and_preserves_snapshot(tmp_path):
    path, hub = _hub(tmp_path)
    class Client(_Client):
        async def get_projects(self): raise TimeoutError("project list")

    with pytest.raises(TimeoutError) as raised:
        asyncio.run(hub._pull_tasks(Client("normal"), 1))
    assert raised.value.diagnostics["failure_stage"] == "project_list"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep'").fetchone()[0] is None


def test_dynamic_budget_reads_more_projects_than_legacy_cap(tmp_path):
    _, hub = _hub(tmp_path)
    class Client:
        async def get_projects(self): return [{"id": f"p{i}", "name": str(i)} for i in range(25)]
        async def get_project_data(self, _project_id): return {"tasks": []}
        async def get_completed_tasks(self, _start): return []

    stats = asyncio.run(hub._pull_tasks(Client(), 1))
    assert stats["complete"] and stats["provider_requests"] > 20
    assert stats["request_budget"] > sync_hub_module.TICKTICK_PULL_REQUEST_BUDGET


def test_validate_only_snapshot_never_publishes_or_deletes(tmp_path):
    path, hub = _hub(tmp_path)
    stats = asyncio.run(hub._pull_tasks(_Client("normal"), 1, publish=False))
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT title,deleted_at FROM server_tasks WHERE id='keep'").fetchone()
    assert stats["complete"] and stats["published"] is False
    assert row == ("fixture", None)


def test_partial_snapshot_publishes_four_new_and_one_rescheduled_task(tmp_path):
    path, hub = _hub(tmp_path)
    hub.db.upsert_task(1, {"id": "moved", "title": "已改期", "status": 0, "priority": 0,
                           "due_date": "2026-09-25 00:00:00", "tags": [], "etag": "old"})
    tasks = [
        {"id": task_id, "title": task_id, "status": 0, "priority": 0,
         "dueDate": "2026-09-25T00:00:00+0800", "tags": [], "etag": f"new-{task_id}",
         "modifiedTime": "2026-09-25T08:00:00+0800"}
        for task_id in ("new-1", "new-2", "new-3", "new-4")
    ] + [{"id": "moved", "title": "已改期", "status": 0, "priority": 0,
          "dueDate": "2026-10-30T00:00:00+0800", "tags": [], "etag": "new-moved",
          "modifiedTime": "2026-09-25T08:00:00+0800"}]
    class Client:
        async def get_projects(self): return [{"id": "ok"}, {"id": "failed"}]
        async def get_project_data(self, project_id):
            if project_id == "failed": raise TimeoutError("fixture")
            return {"tasks": tasks if project_id == "ok" else []}
        async def get_completed_tasks(self, _start): return []

    preview = asyncio.run(hub._pull_tasks(Client(), 1, publish=False))
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_tasks WHERE id LIKE 'new-%'").fetchone()[0] == 0
        assert conn.execute("SELECT due_date FROM server_tasks WHERE id='moved'").fetchone()[0] == "2026-09-25 00:00:00"
    assert preview["candidate_upserts"] == 5 and preview["published_upserts"] == 0

    stats = asyncio.run(hub._pull_tasks(Client(), 1))
    with sqlite3.connect(path) as conn:
        due = conn.execute("SELECT due_date FROM server_tasks WHERE user_id=1 AND id='moved'").fetchone()[0]
        created = conn.execute("SELECT COUNT(*) FROM server_tasks WHERE id LIKE 'new-%'").fetchone()[0]
    assert (created, due) == (4, "2026-10-30 00:00:00")
    assert not stats["complete"] and stats["candidate_upserts"] == stats["published_upserts"] == 5
    assert stats["deleted_tasks"] == stats["completed_task_changes"] == 0


def test_complete_snapshot_deletes_only_ticktick_owned_tasks(tmp_path):
    path, hub = _hub(tmp_path)
    hub.db.upsert_task(1, {"id": "local", "title": "本地", "status": 0, "priority": 0, "tags": []})
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE server_tasks SET source='local' WHERE user_id=1 AND id='local'")
        conn.commit()
    stats = asyncio.run(hub._pull_tasks(_Client("normal"), 1))
    with sqlite3.connect(path) as conn:
        rows = dict(conn.execute("SELECT id,deleted_at FROM server_tasks WHERE user_id=1").fetchall())
    assert stats["complete"] and stats["deleted_tasks"] == 1
    assert rows["keep"] is not None and rows["local"] is None
