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

    assert first["ok"] and first["status"] == "degraded" and first["retry_at"]
    assert first["tasks"]["deleted_tasks"] == 0
    assert automatic["skipped"] and automatic["reason"] == "cooldown" and Client.instances == 2
    assert manual["status"] == "degraded"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep'").fetchone()[0] is None
        assert conn.execute("SELECT last_status FROM server_sync_state WHERE user_id=1").fetchone()[0] == "degraded"


def test_task_pull_never_spends_past_the_provider_request_budget(tmp_path, monkeypatch):
    path, hub = _hub(tmp_path)
    monkeypatch.setattr(sync_hub_module, "TICKTICK_PULL_REQUEST_BUDGET", 2)

    stats = asyncio.run(hub._pull_tasks(_Client("normal"), 1))

    assert stats["provider_requests"] == 2
    assert stats["request_budget_exceeded"] and stats["deleted_tasks"] == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep'").fetchone()[0] is None


def test_304_task_partial_snapshot_merges_safe_records_without_deletion(tmp_path):
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
