# -*- coding: utf-8 -*-
import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.provider_delta_filter import classify_provider_records
from server.sync_hub import SyncHub


def _db(tmp_path):
    path = tmp_path / "task-revival.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.executemany(
        "INSERT INTO users (id,username,password_hash,created_at) VALUES (?,?,?,?)",
        [(1, "u1", "p", "2026-07-31 00:00:00"), (2, "u2", "p", "2026-07-31 00:00:00")],
    )
    conn.commit(); conn.close()
    db = ServerDBWrapper(); db.log_path = str(path)
    return path, db


def _task(task_id="task-1"):
    return {"id": task_id, "title": "fixture", "priority": 0, "status": 0, "tags": [], "etag": "same"}


def test_same_etag_tombstone_is_changed(tmp_path):
    path, db = _db(tmp_path); db.upsert_task(1, _task())
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE server_tasks SET deleted_at='2026-07-31 16:20:54' WHERE user_id=1")
    local = db.get_provider_fingerprints(1, "server_tasks")
    result = classify_provider_records([_task()], local, "task")
    assert [row["id"] for row in result.changed] == ["task-1"]


def test_upsert_clears_tombstone_and_versions_null(tmp_path):
    path, db = _db(tmp_path); db.upsert_task(1, _task())
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE server_tasks SET deleted_at='2026-07-31 16:20:54' WHERE user_id=1")
    assert db.upsert_task(1, _task()) is True
    with sqlite3.connect(path) as conn:
        deleted_at = conn.execute("SELECT deleted_at FROM server_tasks WHERE user_id=1").fetchone()[0]
        payload = conn.execute("SELECT changed_fields_json FROM server_change_log WHERE user_id=1 ORDER BY server_version DESC LIMIT 1").fetchone()[0]
    pull = asyncio.run(SyncHub(db).handle_pull_by_version(1, 1, limit=20))
    assert deleted_at is None and json.loads(payload)["deleted_at"] is None
    assert pull["tables"]["tasks"][0]["deleted_at"] is None and pull["to_version"] == 2


def test_normal_unchanged_and_other_user_stay_unchanged(tmp_path):
    path, db = _db(tmp_path); db.upsert_task(1, _task()); db.upsert_task(2, _task("task-2"))
    before = db.allocate_server_version(2)
    assert db.upsert_task(1, _task()) is False
    with sqlite3.connect(path) as conn:
        other = conn.execute("SELECT deleted_at,title FROM server_tasks WHERE user_id=2").fetchone()
        other_version = conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=2").fetchone()[0]
    assert other == (None, "fixture") and other_version == before


class _TaskClient:
    def __init__(self, status):
        self.status = status
        self.task = {**_task(), "status": status, "projectId": "p1", "dueDate": "2026-07-31T00:00:00+0800"}

    async def get_projects(self): return [{"id": "p1", "name": "提醒"}]
    async def get_project_data(self, _project_id): return {"tasks": [self.task] if self.status == 0 else []}
    async def get_completed_tasks(self, _start): return [self.task] if self.status == 2 else []


@pytest.mark.parametrize("status,changes_key,unchanged_key", [
    (0, "active_task_changes", "active_task_unchanged"),
    (2, "completed_task_changes", "completed_task_unchanged"),
])
def test_sync_hub_revives_active_and_completed_paths(monkeypatch, tmp_path, status, changes_key, unchanged_key):
    path, db = _db(tmp_path); hub = SyncHub(db); client = _TaskClient(status)
    db.upsert_task(1, {**client.task, "due_date": "2026-07-31 00:00:00"})
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE server_tasks SET deleted_at='2026-07-31 16:20:54' WHERE user_id=1")
    monkeypatch.setattr(hub, "_get_ticktick_settings", lambda _uid: SimpleNamespace(inbox_pull_enabled=False))
    first = asyncio.run(hub._pull_tasks(client, 1)); second = asyncio.run(hub._pull_tasks(client, 1))
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT status,deleted_at FROM server_tasks WHERE user_id=1").fetchone()
    assert row == (status, None) and first[changes_key] == 1
    assert second[changes_key] == 0 and second[unchanged_key] == 1
