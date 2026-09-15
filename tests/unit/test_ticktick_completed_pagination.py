import asyncio
import json
import sqlite3

from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub
from server.ticktick_client import TickTickClient


def _hub(tmp_path):
    path = tmp_path / "completed-pagination.db"
    with sqlite3.connect(path) as conn:
        ensure_server_schema(conn)
        conn.execute("INSERT INTO users (id,username,password_hash,created_at) VALUES (1,'u','p','2026-09-01')")
    db = ServerDBWrapper()
    db.log_path = str(path)
    return path, SyncHub(db)


def _completed(task_id, due_date):
    return {
        "id": task_id, "title": task_id, "status": 2, "priority": 0, "tags": [],
        "projectId": "p1", "dueDate": f"{due_date}T09:00:00+0800",
        "completedTime": f"{due_date}T10:00:00+0800", "etag": f"{task_id}-etag",
    }


def test_completed_client_normalizes_legacy_and_explicit_pages():
    assert TickTickClient.normalize_completed_tasks_page([{"id": "legacy"}]) == {
        "records": [{"id": "legacy"}], "next_page": None,
    }
    assert TickTickClient.normalize_completed_tasks_page({
        "tasks": [{"id": "first"}], "hasMore": True, "nextCursor": "cursor-2",
    }) == {"records": [{"id": "first"}], "next_page": {"cursor": "cursor-2"}}
    assert TickTickClient.normalize_completed_tasks_page({"tasks": [], "hasMore": False}) == {
        "records": [], "next_page": None,
    }


def test_completed_history_reads_all_explicit_pages(tmp_path):
    path, hub = _hub(tmp_path)

    class Client:
        async def get_projects(self): return [{"id": "p1", "name": "清单"}]
        async def get_project_data(self, _project_id): return {"tasks": []}
        async def get_completed_tasks(self, _start, continuation=None):
            if continuation is None:
                return {"records": [_completed("task-0905", "2026-09-05")], "next_page": {"cursor": "page-2"}}
            assert continuation == {"cursor": "page-2"}
            return {"records": [_completed("task-0906", "2026-09-06")], "next_page": None}

    stats = asyncio.run(hub._pull_tasks(Client(), 1))
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT id, status FROM server_tasks WHERE user_id=1 ORDER BY id").fetchall()
    assert rows == [("task-0905", 2), ("task-0906", 2)]
    assert stats["completed_pull_succeeded"] is True
    assert stats["completed_pull_error"] is None
    assert stats["complete"] is True


def test_completed_pagination_failure_is_diagnostic_and_preserves_existing_task(tmp_path):
    path, hub = _hub(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO server_tasks (id,user_id,title,status,raw_json,updated_at) VALUES (?,?,?,?,?,?)",
            ("keep", 1, "保留", 0, json.dumps({"project_id": "p1"}), "2026-09-07 12:00:00"),
        )

    class Client:
        async def get_projects(self): return [{"id": "p1", "name": "清单"}]
        async def get_project_data(self, _project_id): return {"tasks": []}
        async def get_completed_tasks(self, _start, continuation=None):
            if continuation is None:
                return {"records": [_completed("partial", "2026-09-05")], "next_page": {"cursor": "page-2"}}
            raise TimeoutError("provider timeout")

    stats = asyncio.run(hub._pull_tasks(Client(), 1))
    with sqlite3.connect(path) as conn:
        kept = conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep'").fetchone()
        partial = conn.execute("SELECT id FROM server_tasks WHERE id='partial'").fetchone()
    assert kept == (None,)
    assert partial is None
    assert stats["completed_pull_succeeded"] is False
    assert stats["completed_pull_error"] == "TimeoutError:provider timeout"
    assert "completed_pull_failed" in stats["deletion_skipped_reason"]


def test_completed_pagination_rejects_repeated_page(tmp_path):
    _, hub = _hub(tmp_path)
    record = _completed("same", "2026-09-05")

    class Client:
        async def get_projects(self): return [{"id": "p1", "name": "清单"}]
        async def get_project_data(self, _project_id): return {"tasks": []}
        async def get_completed_tasks(self, _start, continuation=None):
            return {"records": [record], "next_page": {"cursor": "again"}}

    stats = asyncio.run(hub._pull_tasks(Client(), 1))
    assert stats["complete"] is False
    assert "completed_page_duplicate_records" in stats["completed_pull_error"]


def test_completed_provider_success_with_persistence_failure_is_not_success(tmp_path, monkeypatch):
    _, hub = _hub(tmp_path)

    class Client:
        async def get_projects(self): return [{"id": "p1", "name": "清单"}]
        async def get_project_data(self, _project_id): return {"tasks": []}
        async def get_completed_tasks(self, _start, continuation=None):
            return {"records": [_completed("cannot-save", "2026-09-06")], "next_page": None}

    monkeypatch.setattr(hub.db, "upsert_task", lambda *_args: (_ for _ in ()).throw(sqlite3.IntegrityError("forced")))
    stats = asyncio.run(hub._pull_tasks(Client(), 1))
    assert stats["completed_pull_succeeded"] is True
    assert stats["completed_item_errors"][0]["error_type"] == "IntegrityError"
    assert stats["complete"] is False
    assert "task_persistence_failed" in stats["deletion_skipped_reason"]
