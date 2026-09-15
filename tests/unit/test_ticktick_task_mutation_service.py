import asyncio
import sqlite3
from datetime import datetime, timezone

import httpx

import server.domain.ticktick_task_dates as task_dates
from server.domain.ticktick_task_mutation_service import TickTickTaskMutationService
from server.models.server_schema import ensure_server_schema
from server.models.ticktick_task_operation_store import TickTickTaskOperationStore


def _service(tmp_path):
    path = tmp_path / "task-service.db"
    with sqlite3.connect(path) as conn:
        ensure_server_schema(conn)
        conn.execute("INSERT OR IGNORE INTO users (id,username,password_hash,created_at) VALUES (1,'one@example.test','x','2026-07-31')")
    def connect():
        conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row; return conn
    return TickTickTaskMutationService(TickTickTaskOperationStore(connect, now=lambda: datetime(2026, 7, 31, 9, tzinfo=timezone.utc)))


class Client:
    def __init__(self, *, timeout=False, delete_raises=False):
        self.calls = 0; self.timeout = timeout; self.delete_raises = delete_raises; self.active = True
    async def create_task(self, title):
        self.calls += 1
        if self.timeout: raise httpx.TimeoutException("timeout")
        return {"id": "task-1", "projectId": "project-1", "title": title}
    async def get_task(self, project_id, task_id):
        return {"id": task_id, "projectId": project_id, "title": "new task"}
    async def get_project_data(self, project_id):
        return {"tasks": [{"id": "task-1", "title": "new task"}]}
    async def update_task(self, project_id, task_id, title): self.calls += 1
    async def delete_task(self, project_id, task_id):
        self.calls += 1
        if self.delete_raises: raise RuntimeError("already deleted")
        self.active = False
    async def is_task_active(self, project_id, task_id): return self.active


class DatedClient(Client):
    def __init__(self, due_date):
        super().__init__(); self.due_date = due_date; self.created_due_date = None
    async def create_task(self, title, due_date=None):
        self.calls += 1; self.created_due_date = due_date
        return {"id": "task-1", "projectId": "project-1", "title": title}
    async def get_task(self, project_id, task_id):
        return {"id": task_id, "projectId": project_id, "title": "new task", "timeZone": "Asia/Shanghai", "dueDate": self.due_date}
    async def get_project_data(self, project_id):
        return {"tasks": [{"id": "task-1", "title": "new task", "timeZone": "Asia/Shanghai", "dueDate": self.due_date}]}


class TaggedClient(Client):
    def __init__(self, read_tags):
        super().__init__(); self.read_tags = read_tags; self.created_tags = None
    async def create_task(self, title, due_date=None, tags=None):
        self.calls += 1; self.created_tags = tags
        return {"id": "task-1", "projectId": "project-1", "title": title}
    async def get_task(self, project_id, task_id):
        return {"id": task_id, "projectId": project_id, "title": "new task", "tags": self.read_tags}
    async def get_project_data(self, project_id):
        return {"tasks": [{"id": "task-1", "title": "new task", "tags": self.read_tags}]}


class TransportFailureClient(Client):
    async def create_task(self, title):
        self.calls += 1
        raise httpx.ConnectError("lost", request=httpx.Request("POST", "https://api.dida365.com/open/v1/task"))


class HttpFailureClient(Client):
    async def create_task(self, title):
        self.calls += 1
        request = httpx.Request("POST", "https://api.dida365.com/open/v1/task")
        raise httpx.HTTPStatusError("rejected", request=request, response=httpx.Response(400, request=request))


class EditableClient(Client):
    def __init__(self, **task):
        super().__init__()
        self.task = {"id": "task-1", "projectId": "project-1", "title": "old", "status": 0, "timeZone": "Asia/Shanghai", **task}
    async def get_task(self, project_id, task_id): return dict(self.task)
    async def update_task(self, project_id, task_id, payload): self.calls += 1; self.task.update(payload)


class TimeoutWriteClient(EditableClient):
    def __init__(self, *, writes_before_timeout):
        super().__init__()
        self.writes_before_timeout = writes_before_timeout
    async def update_task(self, project_id, task_id, payload):
        self.calls += 1
        if self.writes_before_timeout: self.task.update(payload)
        raise httpx.TimeoutException("timeout")


def test_create_confirms_after_readback_and_same_request_never_retries(tmp_path):
    service, client = _service(tmp_path), Client()
    result = asyncio.run(service.create(1, "request-1", "new task", client))
    repeat = asyncio.run(service.create(1, "request-1", "new task", client))
    assert result["status"] == repeat["status"] == "confirmed" and client.calls == 1


def test_create_timeout_is_unknown_without_second_provider_call(tmp_path):
    service, client = _service(tmp_path), Client(timeout=True)
    result = asyncio.run(service.create(1, "request-2", "new task", client))
    repeat = asyncio.run(service.create(1, "request-2", "new task", client))
    assert result["status"] == repeat["status"] == "unknown" and client.calls == 1


def test_create_with_due_date_confirms_only_after_matching_readback(tmp_path):
    due_date = "2026-08-13T00:00:00+0800"
    service, client = _service(tmp_path), DatedClient(due_date)
    result = asyncio.run(service.create(1, "request-dated", "new task", client, "2026-08-13"))
    assert result["status"] == "confirmed" and client.created_due_date == due_date
    mismatch = asyncio.run(_service(tmp_path).create(1, "request-dated-mismatch", "new task", DatedClient("2026-08-14T00:00:00+0800"), "2026-08-13"))
    assert mismatch["status"] == "unknown" and mismatch["error_code"] == "provider_readback_unconfirmed"


def test_create_without_due_date_keeps_existing_client_contract(tmp_path):
    service, client = _service(tmp_path), Client()
    result = asyncio.run(service.create(1, "request-undated", "new task", client))
    assert result["status"] == "confirmed" and client.calls == 1


def test_create_tags_require_matching_readback_and_reconcile(tmp_path):
    service, client = _service(tmp_path), TaggedClient(["输入"])
    result = asyncio.run(service.create(1, "request-tagged", "new task", client, tags=["输入", "输入", " "]))
    assert result["status"] == "confirmed" and client.created_tags == ["输入"]
    mismatch = asyncio.run(_service(tmp_path).create(1, "request-tagged-mismatch", "new task", TaggedClient(["输出"]), tags=["输入"]))
    assert mismatch["status"] == "unknown" and mismatch["error_code"] == "provider_readback_unconfirmed"


def test_create_transport_failure_is_unknown_but_http_rejection_fails(tmp_path):
    unknown = asyncio.run(_service(tmp_path).create(1, "request-transport", "new task", TransportFailureClient()))
    failed = asyncio.run(_service(tmp_path).create(1, "request-http", "new task", HttpFailureClient()))
    assert unknown["status"] == "unknown" and unknown["error_code"] == "provider_request_unknown"
    assert failed["status"] == "failed" and failed["error_code"] == "provider_request_failed"


def test_unknown_create_only_reconciles_a_unique_readback_candidate(tmp_path):
    service = _service(tmp_path)
    client = Client()
    operation, _ = service.ledger.create_or_get(1, "request-reconcile", "create", project_id="project-1", title_fingerprint=service._fingerprint("new task"))
    service.ledger.mark(1, operation["request_id"], "unknown", project_id="project-1")
    confirmed = asyncio.run(service.reconcile_create(1, "request-reconcile", client))
    assert confirmed["status"] == "confirmed" and confirmed["result_task_id"] == "task-1" and client.calls == 0


def test_unknown_dated_create_does_not_reconcile_a_same_title_with_wrong_date(tmp_path):
    service = _service(tmp_path)
    fingerprint = service._create_fingerprint("new task", "2026-08-13T00:00:00+0800")
    operation, _ = service.ledger.create_or_get(1, "request-dated-reconcile", "create", project_id="project-1", title_fingerprint=fingerprint)
    service.ledger.mark(1, operation["request_id"], "unknown", project_id="project-1")
    result = asyncio.run(service.reconcile_create(1, "request-dated-reconcile", DatedClient("2026-08-14T00:00:00+0800")))
    assert result["status"] == "unknown"


def test_unknown_dated_create_reconciles_only_the_matching_date(tmp_path):
    service = _service(tmp_path)
    due_date = "2026-08-13T00:00:00+0800"
    operation, _ = service.ledger.create_or_get(1, "request-dated-reconcile-match", "create", project_id="project-1", title_fingerprint=service._create_fingerprint("new task", due_date))
    service.ledger.mark(1, operation["request_id"], "unknown", project_id="project-1")
    result = asyncio.run(service.reconcile_create(1, "request-dated-reconcile-match", DatedClient(due_date)))
    assert result["status"] == "confirmed" and result["result_task_id"] == "task-1"


def test_title_update_detects_external_change_before_writing(tmp_path):
    service, client = _service(tmp_path), Client()
    result = asyncio.run(service.update_title(1, "request-conflict", "project-1", "task-1", "renamed", client, expected_title="previous title"))
    assert result["status"] == "conflict" and result["error_code"] == "provider_task_conflict" and client.calls == 0


def test_request_id_cannot_be_reused_for_a_different_task_patch(tmp_path):
    ledger = _service(tmp_path).ledger
    first, inserted = ledger.create_or_get(1, "request-patch", "update", task_id="task-1", project_id="project-1", expected_fingerprint="before", patch_fingerprint="after")
    reused, again = ledger.create_or_get(1, "request-patch", "update", task_id="task-1", project_id="project-1", expected_fingerprint="before", patch_fingerprint="different")
    replay, replayed = ledger.create_or_get(1, "request-patch", "update", task_id="task-1", project_id="project-1", expected_fingerprint="before", patch_fingerprint="after")
    assert inserted is True and again is False and replayed is False
    assert first["status"] == replay["status"] == "pending"
    assert reused["error_code"] == "request_id_reused_with_different_patch"


def test_task_patch_rejects_completed_recurring_conflicting_and_invalid_range_without_writing(tmp_path):
    service = _service(tmp_path)
    for suffix, client, patch, expected in (
        ("completed", EditableClient(status=2), {"dueDate": "2026-08-09T00:00:00+0800"}, {}),
        ("repeat", EditableClient(repeatFlag="RRULE:FREQ=DAILY"), {"dueDate": "2026-08-09T00:00:00+0800"}, {}),
        ("conflict", EditableClient(title="newer"), {"title": "saved"}, {"title": "old"}),
        ("range", EditableClient(), {"startDate": "2026-08-10T00:00:00+0800", "dueDate": "2026-08-09T00:00:00+0800"}, {}),
    ):
        result = asyncio.run(service.update(1, f"request-{suffix}", "project-1", "task-1", patch, expected, client))
        assert result["status"] in {"failed", "conflict"} and client.calls == 0


def test_task_patch_rejects_unavailable_non_shanghai_timezone_before_provider_write(tmp_path, monkeypatch):
    monkeypatch.setattr(task_dates, "ZoneInfo", lambda _: (_ for _ in ()).throw(task_dates.ZoneInfoNotFoundError("missing")))
    client = EditableClient(timeZone="America/New_York", dueDate="2026-08-09T09:00:00-0400")
    result = asyncio.run(_service(tmp_path).update(1, "request-timezone", "project-1", "task-1", {"dueDate": "2026-08-10T09:00:00-0400"}, {"dueDate": "2026-08-09T09:00:00-0400"}, client))
    assert result["status"] == "failed" and result["error_code"] == "task_timezone_unavailable" and client.calls == 0


def test_task_patch_preserves_provider_fields_and_confirms_date_clear(tmp_path):
    service = _service(tmp_path)
    client = EditableClient(content="keep", tags=["tag"], startDate="2026-08-01T09:00:00+0800", dueDate="2026-08-02T09:00:00+0800")
    result = asyncio.run(service.update(1, "request-date", "project-1", "task-1", {"startDate": None, "dueDate": "2026-08-09T09:00:00+0800"}, {"startDate": "2026-08-01T09:00:00+0800", "dueDate": "2026-08-02T09:00:00+0800"}, client))
    assert result["status"] == "confirmed" and client.calls == 1
    assert client.task["startDate"] is None and client.task["content"] == "keep" and client.task["tags"] == ["tag"]


def test_timeout_readback_confirms_once_or_stays_unknown_without_retry(tmp_path):
    service = _service(tmp_path)
    for request_id, wrote, expected_status in (("request-timeout-confirmed", True, "confirmed"), ("request-timeout-unknown", False, "unknown")):
        client = TimeoutWriteClient(writes_before_timeout=wrote)
        first = asyncio.run(service.update(1, request_id, "project-1", "task-1", {"dueDate": "2026-08-09T00:00:00+0800"}, {}, client))
        replay = asyncio.run(service.update(1, request_id, "project-1", "task-1", {"dueDate": "2026-08-09T00:00:00+0800"}, {}, client))
        assert first["status"] == replay["status"] == expected_status and client.calls == 1


def test_delete_confirms_when_active_snapshot_no_longer_contains_task(tmp_path):
    result = asyncio.run(_service(tmp_path).delete(1, "request-3", "project-1", "task-1", Client(delete_raises=True)))
    assert result["status"] == "failed"
    client = Client(delete_raises=True); client.active = False
    confirmed = asyncio.run(_service(tmp_path).delete(1, "request-4", "project-1", "task-1", client))
    assert confirmed["status"] == "confirmed" and confirmed["http_status"] == 404
