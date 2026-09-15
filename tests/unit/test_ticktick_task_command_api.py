import json
import pytest
from fastapi.testclient import TestClient

import server.server as server_module
from server.domain.ticktick_task_mutation_service import TickTickTaskMutationService
from server.models.ticktick_task_operation_store import TickTickTaskOperationStore
from server.store import ServerSleepStore
from server.db_wrapper import ServerDBWrapper
from server.domain.flash_card_service import FlashCardService


@pytest.fixture
def task_api(tmp_path):
    original = (server_module.store, server_module.ticktick_task_operation_store, server_module.ticktick_task_mutation_service)
    store = ServerSleepStore(str(tmp_path / "task-api.db"))
    store.create_user("owner@example.test", "password")
    store.create_user("other@example.test", "password")
    server_module.store = store
    server_module.ticktick_task_operation_store = TickTickTaskOperationStore(store._connect)
    server_module.ticktick_task_mutation_service = TickTickTaskMutationService(server_module.ticktick_task_operation_store)
    server_module.app.dependency_overrides[server_module.get_current_user] = lambda: {"id": 1, "username": "owner@example.test"}
    try:
        yield TestClient(server_module.app), store
    finally:
        server_module.app.dependency_overrides.pop(server_module.get_current_user, None)
        server_module.store, server_module.ticktick_task_operation_store, server_module.ticktick_task_mutation_service = original


def test_task_command_rejects_invalid_body_and_missing_user_configuration(task_api):
    client, store = task_api
    invalid = client.post("/api/ticktick/tasks/commands", json={"request_id": "r1", "operation": "create", "title": ""})
    unconfigured = client.post("/api/ticktick/tasks/commands", json={"request_id": "r2", "operation": "create", "title": "safe title"})
    assert invalid.json() == {"request_id": "r1", "status": "failed", "error_code": "validation_error"}
    assert unconfigured.json() == {"request_id": "r2", "status": "failed", "error_code": "provider_not_configured"}
    assert store._connect().execute("SELECT COUNT(*) FROM server_ticktick_task_operations").fetchone()[0] == 0


def test_task_command_rejects_empty_date_patch_without_persisting_operation(task_api):
    client, store = task_api
    result = client.post("/api/ticktick/tasks/commands", json={"request_id": "r-date", "operation": "update", "task_id": "task-1", "project_id": "project-1", "patch": {}})
    assert result.json() == {"request_id": "r-date", "status": "failed", "error_code": "validation_error"}
    assert store._connect().execute("SELECT COUNT(*) FROM server_ticktick_task_operations").fetchone()[0] == 0


def test_task_operation_query_is_isolated_per_user(task_api):
    client, store = task_api
    server_module.ticktick_task_operation_store.create_or_get(1, "visible-to-owner", "create")
    assert client.get("/api/ticktick/tasks/operations/visible-to-owner").status_code == 200
    server_module.app.dependency_overrides[server_module.get_current_user] = lambda: {"id": 2, "username": "other@example.test"}
    assert client.get("/api/ticktick/tasks/operations/visible-to-owner").status_code == 404


def test_confirmed_provider_task_is_published_through_versioned_sync(tmp_path):
    store = ServerSleepStore(str(tmp_path / "published.db"))
    store.create_user("owner@example.test", "password"); store.create_user("other@example.test", "password")
    original_db, original_hub = server_module.time_logger_db, server_module.sync_hub
    notified = []
    class Hub:
        def _notify_clients(self, entities, user_id): notified.append((entities, user_id))
    server_module.time_logger_db, server_module.sync_hub = ServerDBWrapper(store.db_path), Hub()
    try:
        server_module._publish_confirmed_ticktick_task(1, "update", {"project_id": "project-1"}, {"id": "task-1", "projectId": "project-1", "title": "edited", "status": 0, "priority": 0, "startDate": "2026-08-08T09:00:00+0800", "dueDate": "2026-08-15T09:00:00+0800", "timeZone": "Asia/Shanghai"})
        conn = store._connect()
        row = conn.execute("SELECT raw_json FROM server_tasks WHERE user_id=1 AND id='task-1'").fetchone()
        version = conn.execute("SELECT server_version FROM server_change_log WHERE user_id=1 AND entity_id='task-1'").fetchone()
        other = conn.execute("SELECT COUNT(*) FROM server_tasks WHERE user_id=2").fetchone()[0]
        conn.close()
    finally:
        server_module.time_logger_db, server_module.sync_hub = original_db, original_hub
    assert json.loads(row[0])["startDate"] == "2026-08-08T09:00:00+0800"
    assert version[0] == 1 and other == 0 and notified == [(["tasks"], 1)]


def test_flash_direct_and_confirm_paths_create_local_tasks_without_ticktick(task_api, monkeypatch):
    client, store = task_api
    changes, provider_calls, notices = [], [], []
    service = FlashCardService(store._connect, lambda *args: changes.append(args))
    original_service, original_hub = server_module.flash_card_service, server_module.sync_hub
    class Hub:
        def _notify_clients(self, entities, user_id): notices.append((entities, user_id))
    def forbidden_provider(*args, **kwargs):
        provider_calls.append((args, kwargs)); raise AssertionError("TickTick must not be constructed")
    try:
        server_module.flash_card_service, server_module.sync_hub = service, Hub()
        monkeypatch.setattr(server_module, "TickTickClient", forbidden_provider)
        direct = service.create(1, {"original_text": "给客户发邮件"})
        service.save_insights(1, direct["id"], "给客户发邮件。", None, [{"title": "给客户发邮件", "reason": "明确"}])
        complex_card = service.create(1, {"original_text": "计划旅行，然后订票并安排住宿"})
        service.save_insights(1, complex_card["id"], "计划旅行，然后订票并安排住宿。", None, [{"title": "规划旅行", "reason": "需拆解"}])
        recommendation = service.list_recommendations(1, [complex_card["id"]])[0]
        response = client.post("/api/ticktick/tasks/commands", json={"request_id": "confirm-local", "operation": "create", "flash_recommendation_id": recommendation["id"]})
        replay = client.post("/api/ticktick/tasks/commands", json={"request_id": "confirm-local", "operation": "create", "flash_recommendation_id": recommendation["id"]})
        with store._connect() as conn:
            local_tasks = conn.execute("SELECT id,title FROM server_tasks WHERE user_id=1 AND source='local'").fetchall()
    finally:
        server_module.flash_card_service, server_module.sync_hub = original_service, original_hub
    assert response.json()["status"] == replay.json()["status"] == "confirmed"
    assert sorted(row["title"] for row in local_tasks) == ["给客户发邮件", "规划旅行"]
    assert provider_calls == [] and notices == [(["flash_task_recommendations", "tasks"], 1)]
