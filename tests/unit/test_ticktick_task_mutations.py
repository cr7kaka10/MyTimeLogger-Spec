import asyncio

import pytest

from server.ticktick_client import TickTickClient


class RecordingClient(TickTickClient):
    def __init__(self):
        super().__init__("test-token")
        self.calls = []

    async def _post(self, path, body=None):
        self.calls.append((path, body))
        return {"id": body.get("id", "created-id"), "projectId": body.get("projectId", "inbox")}

    async def _get(self, path, params=None):
        self.calls.append((path, params))
        return {"tasks": [{"id": "active-task"}]}


def test_create_task_sends_title_to_default_inbox():
    client = RecordingClient()
    result = asyncio.run(client.create_task(" test "))
    assert client.calls == [("/task", {"title": "test"})]
    assert result == {"id": "created-id", "projectId": "inbox"}


def test_create_task_includes_optional_tags_without_changing_due_date_fields():
    client = RecordingClient()
    asyncio.run(client.create_task("学习", "2026-08-14T00:00:00+0800", ["输入"]))
    assert client.calls == [("/task", {"title": "学习", "dueDate": "2026-08-14T00:00:00+0800", "timeZone": "Asia/Shanghai", "isAllDay": True, "tags": ["输入"]})]


def test_create_task_requires_title_and_canonical_response_identifiers():
    with pytest.raises(ValueError, match="validation_error:title_required"):
        asyncio.run(RecordingClient().create_task("  "))


def test_update_task_uses_verified_title_contract():
    client = RecordingClient()
    asyncio.run(client.update_task("project", "task", "updated"))
    assert client.calls == [("/task/task", {"id": "task", "projectId": "project", "title": "updated"})]


def test_update_task_sends_only_writable_fields_and_required_identifiers():
    client = RecordingClient()
    asyncio.run(client.update_task("project", "task", {
        "id": "spoofed", "projectId": "spoofed", "title": "updated",
        "startDate": "2026-08-09T09:00:00+0800", "dueDate": None,
        "status": 2, "etag": "readonly", "modifiedTime": "readonly",
    }))
    path, payload = client.calls[0]
    assert path == "/task/task"
    assert payload == {"id": "task", "projectId": "project", "title": "updated", "startDate": "2026-08-09T09:00:00+0800", "dueDate": None}


def test_activity_snapshot_confirms_delete_visibility():
    client = RecordingClient()
    assert asyncio.run(client.is_task_active("project", "active-task")) is True
    assert asyncio.run(client.is_task_active("project", "deleted-task")) is False


def test_get_project_data_uses_official_inbox_path():
    client = RecordingClient()
    asyncio.run(client.get_project_data("inbox"))
    assert client.calls == [("/project/inbox/data", None)]
