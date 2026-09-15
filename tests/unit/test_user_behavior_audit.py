import sqlite3

import pytest
from fastapi.testclient import TestClient
import server.server as server_module
from server.server import app
from server.store import ServerSleepStore

from server.domain.user_behavior_audit_service import UserBehaviorAuditService
from server.models.server_schema import ensure_server_schema


def _db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users (username,password_hash,created_at) VALUES ('audit-user','hash','2026-08-26 00:00:00')")
    conn.commit()
    return conn


def _event(event_id="e1", occurred_at="2026-08-26 10:00:00", **extra):
    return {
        "event_id": event_id, "occurred_at": occurred_at, "device_id": "device-a",
        "runtime": "web", "page": "/timer", "event_type": "interaction",
        "action": "control.activated", "result": "accepted", "metadata": {"tab": "timer"}, **extra,
    }


def test_append_is_idempotent_and_account_scoped(tmp_path):
    conn = _db(tmp_path / "audit.db")
    service = UserBehaviorAuditService(lambda: sqlite3.connect(tmp_path / "audit.db"))
    event = _event()
    assert service.append(1, [event]) == ["e1"]
    assert service.append(1, [event]) == ["e1"]
    with conn:
        rows = conn.execute("SELECT COUNT(*) FROM server_user_behavior_events").fetchone()[0]
    assert rows == 1


@pytest.mark.parametrize("metadata", [{"token": "x"}, {"label": "x" * 5000}])
def test_sensitive_or_oversized_metadata_is_rejected_without_partial_write(tmp_path, metadata):
    conn = _db(tmp_path / "audit-invalid.db")
    service = UserBehaviorAuditService(lambda: sqlite3.connect(tmp_path / "audit-invalid.db"))
    with pytest.raises(ValueError):
        service.append(1, [_event(metadata=metadata)])
    assert conn.execute("SELECT COUNT(*) FROM server_user_behavior_events").fetchone()[0] == 0


def test_readable_projection_uses_safe_metadata_and_falls_back():
    click = UserBehaviorAuditService.present({**_event(), "metadata_json": '{"surface":"management_plan","control":"当前导图"}'})
    assert click["summary"] == "在管理方案中点击了“当前导图”"
    request = UserBehaviorAuditService.present({**_event(action="api.request_result", result="succeeded"), "metadata_json": '{"method":"GET","path":"/api/management-plans/mindmap","status":200}'})
    assert request["summary"] == "管理方案的服务请求成功"
    assert "GET /api/management-plans/mindmap" in request["detail"]
    unknown = UserBehaviorAuditService.present({**_event(action="future.action"), "metadata_json": "{}"})
    assert unknown["summary"] == "在计时中执行了系统操作"


def test_api_is_authenticated_and_returns_only_current_users_events(tmp_path, monkeypatch):
    store = ServerSleepStore(str(tmp_path / "api.db"))
    original = server_module.store
    server_module.store = store
    try:
        monkeypatch.setattr(server_module, "_ensure_sample_data_for_user", lambda _user_id: None)
        client = TestClient(app)
        assert client.get("/api/v1/behavior-events?date=2026-08-26").status_code in {401, 403}
        client.post("/auth/register", json={"username": "audit-api", "password": "password123"})
        token = client.post("/auth/login", json={"username": "audit-api", "password": "password123"}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"events": [_event(occurred_at="2026-08-26 23:59:59"), _event("e2", occurred_at="2026-08-27 00:00:00")]}
        assert client.post("/api/v1/behavior-events/batch", json=payload, headers=headers).status_code == 200
        response = client.get("/api/v1/behavior-events?date=2026-08-26", headers=headers)
        assert response.status_code == 200
        assert [row["event_id"] for row in response.json()["events"]] == ["e1"]
        row = response.json()["events"][0]
        assert row["summary"] == '在计时中执行了系统操作' or '点击了' in row["summary"]
        assert row["page_label"] == "计时"
        assert "metadata_json" not in row
        assert client.get("/api/v1/behavior-events?date=2026-02-30", headers=headers).status_code == 400
    finally:
        server_module.store = original
