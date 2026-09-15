import sqlite3
from datetime import datetime, timezone

from server.models.server_schema import ensure_server_schema
from server.models.ticktick_task_operation_store import TickTickTaskOperationStore
from server.ticktick_client import task_operation_log_fields


def _store(tmp_path):
    path = tmp_path / "operation-ledger.db"
    with sqlite3.connect(path) as conn:
        ensure_server_schema(conn)
        conn.executemany("INSERT INTO users (id,username,password_hash,created_at) VALUES (?,?,?,?)", [(1, "one@example.test", "x", "2026-07-31 00:00:00"), (2, "two@example.test", "x", "2026-07-31 00:00:00")])
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    return TickTickTaskOperationStore(connect, now=lambda: datetime(2026, 7, 31, 9, tzinfo=timezone.utc))


def test_ticktick_operation_is_idempotent_and_user_scoped(tmp_path):
    store = _store(tmp_path)
    created, inserted = store.create_or_get(1, "request-1", "create")
    repeated, inserted_again = store.create_or_get(1, "request-1", "delete", task_id="other")
    other_user, other_inserted = store.create_or_get(2, "request-1", "create")
    assert inserted is True and inserted_again is False and other_inserted is True
    assert created["operation"] == repeated["operation"] == "create"
    assert store.get(2, "request-1")["id"] == other_user["id"] != store.get(1, "request-1")["id"]


def test_ticktick_operation_persists_attempts_and_safe_result_fields(tmp_path):
    store = _store(tmp_path)
    store.create_or_get(1, "request-2", "update", task_id="task-1", project_id="project-1")
    attempt = store.begin_attempt(1, "request-2")
    confirmed = store.mark(1, "request-2", "confirmed", result_task_id="task-1", http_status=200)
    assert attempt["attempts"] == 1
    assert confirmed["status"] == "confirmed" and confirmed["confirmed_at"].endswith("+08:00")
    assert confirmed["error_code"] is None


def test_task_operation_log_fields_never_include_sensitive_payload():
    fields = task_operation_log_fields(request_id="request-3", operation="create", status="failed", task_id="task-3", http_status=401, error_code="provider_auth_failed")
    assert fields == {"request_id": "request-3", "operation": "create", "status": "failed", "task_id": "task-3", "project_id": None, "http_status": 401, "error_code": "provider_auth_failed"}
    assert not ({"token", "authorization", "title", "body", "response"} & set(fields))
