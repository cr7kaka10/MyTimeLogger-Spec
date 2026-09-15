# -*- coding: utf-8 -*-
from types import SimpleNamespace

from fastapi.testclient import TestClient

import server.server as server_module
from server.server import app
from server.store import ServerSleepStore
from server.sync_hub import SyncHub
from server.domain.atimelogger_backup_store import ATimeLoggerBackupStore, beijing_text


class _TestSyncDb:
    def __init__(self, log_path):
        self.log_path = log_path


class _AtimeloggerJwtResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {"token": "fixture-fresh-token"}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


def _login_headers(client, username="settings_user"):
    client.post("/auth/register", json={"username": username, "password": "password123"})
    resp = client.post("/auth/login", json={"username": username, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_atimelogger_final_status_and_retry_are_shared_and_redacted(tmp_db_path):
    test_store = ServerSleepStore(db_path=tmp_db_path)
    original_store = server_module.store
    server_module.store = test_store
    try:
        client = TestClient(app)
        headers = _login_headers(client, "final_status_user")
        server_module._write_user_provider_config(
            1, "atimelogger_config",
            {"enabled": True, "username": "atl-user", "token": "super-secret"},
        )
        conn = test_store._connect()
        conn.execute(
            "INSERT INTO server_study_sessions "
            "(id,user_id,start_time,end_time,net_duration_minutes,date,updated_at) "
            "VALUES ('s1',1,'2026-07-25 18:00:00+08:00','2026-07-25 18:30:00+08:00',30,'2026-07-25',?)",
            (beijing_text(),),
        )
        ATimeLoggerBackupStore.enqueue_in_tx(conn, 1, "s1", beijing_text())
        conn.execute(
            "UPDATE server_atimelogger_backups SET sync_state='failed',last_error_code='remote_timeout' "
            "WHERE user_id=1 AND stable_session_id='s1'"
        )
        conn.commit()
        conn.close()

        status = client.get("/admin/provider-bindings/config", headers=headers)
        retry = client.post("/admin/provider-bindings/atimelogger/retry", headers=headers)
        assert status.status_code == retry.status_code == 200
        assert status.json()["atimelogger"]["failed_count"] == 1
        assert retry.json()["released"] == 1
        assert retry.json()["pending_count"] == 1
        serialized = f"{status.json()} {retry.json()}"
        assert "super-secret" not in serialized
        assert "remote_activity_id" not in serialized
    finally:
        server_module.store = original_store


def test_atimelogger_binding_is_personal_and_status_redacts_password(tmp_db_path, monkeypatch):
    test_store = ServerSleepStore(db_path=tmp_db_path)
    orig_store = server_module.store
    orig_sync_hub = server_module.sync_hub
    orig_time_logger_db = server_module.time_logger_db
    server_module.store = test_store
    server_module.sync_hub = SyncHub(_TestSyncDb(tmp_db_path))
    server_module.time_logger_db = SimpleNamespace(log_path=tmp_db_path)
    monkeypatch.setenv("TEXT_BASE_URL", "https://text.example")
    monkeypatch.setenv("TEXT_MODEL", "glm-test")
    monkeypatch.setattr(server_module.requests, "post", lambda *_args, **_kwargs: _AtimeloggerJwtResponse())
    try:
        client = TestClient(app)
        headers = _login_headers(client)
        server_module._write_user_provider_config(1, "ai_model_config", {
            "text_base_url": "https://text.example", "text_api_key": "text-key",
            "text_model": "glm-test", "vision_base_url": "https://vision.example",
            "vision_api_key": "vision-key", "vision_model": "glm-vision",
        })
        response = client.put(
            "/admin/provider-bindings/atimelogger",
            headers=headers,
            json={"enabled": True, "username": "atl-user", "password": "atl-secret"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["scope"] == "personal"
        assert body["username"] == "atl-user"
        assert "atl-secret" not in str(body)

        status = client.get("/admin/integration-config/status", headers=headers)
        assert status.status_code == 200
        payload = status.json()
        assert payload["atimelogger"]["configured"] is True
        assert payload["text_model"]["configured"] is True
        assert "atl-secret" not in str(payload)
    finally:
        server_module.store = orig_store
        server_module.sync_hub = orig_sync_hub
        server_module.time_logger_db = orig_time_logger_db


def test_atimelogger_binding_rejection_does_not_save_submitted_credentials(tmp_db_path, monkeypatch):
    test_store = ServerSleepStore(db_path=tmp_db_path)
    orig_store = server_module.store
    orig_sync_hub = server_module.sync_hub
    orig_time_logger_db = server_module.time_logger_db
    server_module.store = test_store
    server_module.sync_hub = SyncHub(_TestSyncDb(tmp_db_path))
    server_module.time_logger_db = SimpleNamespace(log_path=tmp_db_path)
    monkeypatch.setattr(server_module.requests, "post", lambda *_args, **_kwargs: _AtimeloggerJwtResponse(401))
    try:
        client = TestClient(app)
        headers = _login_headers(client, "rejecting_user")
        response = client.put(
            "/admin/provider-bindings/atimelogger",
            headers=headers,
            json={"enabled": True, "username": "fixture-user", "password": "fixture-password"},
        )
        assert response.status_code == 401
        assert "fixture-password" not in str(response.json())
        assert server_module._load_user_provider_config(1, "atimelogger_config") == {}
    finally:
        server_module.store = orig_store
        server_module.sync_hub = orig_sync_hub
        server_module.time_logger_db = orig_time_logger_db


def test_atimelogger_binding_timeout_does_not_overwrite_existing_token(tmp_db_path, monkeypatch):
    import requests

    test_store = ServerSleepStore(db_path=tmp_db_path)
    orig_store = server_module.store
    orig_sync_hub = server_module.sync_hub
    orig_time_logger_db = server_module.time_logger_db
    server_module.store = test_store
    server_module.sync_hub = SyncHub(_TestSyncDb(tmp_db_path))
    server_module.time_logger_db = SimpleNamespace(log_path=tmp_db_path)
    server_module._write_user_provider_config(1, "atimelogger_config", {
        "username": "old-user", "token": "old-token",
        "password": "legacy-password", "refresh_token": "legacy-refresh",
        "device_id": "legacy-device", "type_map": {"娱乐": "t1"},
    })
    monkeypatch.setattr(server_module.requests, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.ConnectTimeout()))
    try:
        client = TestClient(app)
        headers = _login_headers(client, "timeout_user")
        response = client.put(
            "/admin/provider-bindings/atimelogger",
            headers=headers,
            json={"enabled": True, "username": "fixture-user", "password": "fixture-password"},
        )
        assert response.status_code == 503
        saved = server_module._load_user_provider_config(1, "atimelogger_config")
        assert saved["token"] == "old-token"
        assert saved["username"] == "old-user"
    finally:
        server_module.store = orig_store
        server_module.sync_hub = orig_sync_hub
        server_module.time_logger_db = orig_time_logger_db


def test_atimelogger_binding_success_replaces_old_token(tmp_db_path, monkeypatch):
    test_store = ServerSleepStore(db_path=tmp_db_path)
    orig_store = server_module.store
    orig_sync_hub = server_module.sync_hub
    orig_time_logger_db = server_module.time_logger_db
    server_module.store = test_store
    server_module.sync_hub = SyncHub(_TestSyncDb(tmp_db_path))
    server_module.time_logger_db = SimpleNamespace(log_path=tmp_db_path)
    server_module._write_user_provider_config(1, "atimelogger_config", {
        "username": "old-user", "token": "old-token",
        "password": "legacy-password", "refresh_token": "legacy-refresh",
        "device_id": "legacy-device", "type_map": {"娱乐": "t1"},
    })
    monkeypatch.setattr(server_module.requests, "post", lambda *_args, **_kwargs: _AtimeloggerJwtResponse())
    try:
        client = TestClient(app)
        headers = _login_headers(client, "refreshing_user")
        response = client.put(
            "/admin/provider-bindings/atimelogger",
            headers=headers,
            json={"enabled": True, "username": "fixture-user", "password": "fixture-password"},
        )
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        saved = server_module._load_user_provider_config(1, "atimelogger_config")
        assert saved["token"] == "fixture-fresh-token"
        assert saved["token"] != "old-token"
        assert not {
            "password", "refresh_token", "device_id", "type_map",
        }.intersection(saved)
    finally:
        server_module.store = orig_store
        server_module.sync_hub = orig_sync_hub
        server_module.time_logger_db = orig_time_logger_db


def test_atimelogger_status_requires_recent_server_verification_for_historical_cache(tmp_db_path):
    test_store = ServerSleepStore(db_path=tmp_db_path)
    orig_store = server_module.store
    orig_sync_hub = server_module.sync_hub
    orig_time_logger_db = server_module.time_logger_db
    server_module.store = test_store
    server_module.sync_hub = SyncHub(_TestSyncDb(tmp_db_path))
    server_module.time_logger_db = SimpleNamespace(log_path=tmp_db_path)
    server_module._write_user_provider_config(1, "atimelogger_config", {"enabled": True, "username": "fixture-user", "token": "old-token"})
    try:
        client = TestClient(app)
        headers = _login_headers(client, "historical_cache_user")
        response = client.get("/admin/integration-config/status", headers=headers)
        assert response.status_code == 200
        binding = response.json()["atimelogger"]
        assert binding["configured"] is True
        assert binding["authenticated"] is False
        assert binding["auth_required"] is True
    finally:
        server_module.store = orig_store
        server_module.sync_hub = orig_sync_hub
        server_module.time_logger_db = orig_time_logger_db


def test_atimelogger_authorization_failure_marks_reverification_required(tmp_db_path):
    test_store = ServerSleepStore(db_path=tmp_db_path)
    orig_store = server_module.store
    orig_time_logger_db = server_module.time_logger_db
    server_module.store = test_store
    server_module.time_logger_db = SimpleNamespace(log_path=tmp_db_path)
    server_module._write_user_provider_config(1, "atimelogger_config", {
        "enabled": True,
        "username": "fixture-user",
        "token": "fixture-token",
        "auth_verified_at": "2026-07-19 21:00:00",
        "auth_required": False,
    })
    try:
        server_module._mark_atimelogger_auth_required(1)
        saved = server_module._load_user_provider_config(1, "atimelogger_config")
        assert saved["auth_required"] is True
        assert saved["auth_verified_at"] == ""
    finally:
        server_module.store = orig_store
        server_module.time_logger_db = orig_time_logger_db


def test_ping_exposes_redacted_final_backup_capability():
    response = TestClient(app).get("/ping")
    assert response.status_code == 200
    body = response.json()
    assert body["build_revision"]
    assert body["capabilities"]["atimelogger_final_backup"] == {
        "mode": "final_only", "version": 2,
    }
    assert "token" not in str(body).lower()
    assert "password" not in str(body).lower()


def test_manual_s3_backup_requires_service_manager_and_redacts_state(tmp_db_path, monkeypatch):
    test_store, original_store = ServerSleepStore(db_path=tmp_db_path), server_module.store
    class FakeBackup:
        state = {"status": "idle"}
        async def run_now(self): return {"status": "success", "last_success": "2026-08-15T14:00:00", "error": None}
        def public_state(self): return {"status": "idle", "last_success": None, "error": None}
    original_backup, fake = server_module.s3_backup, FakeBackup()
    server_module.store = test_store; server_module.s3_backup = fake
    try:
        client = TestClient(app)
        manager = _login_headers(client, "s3_manager")
        member = _login_headers(client, "s3_member")
        denied = client.post("/admin/s3-backup/run", headers=member)
        allowed = client.post("/admin/s3-backup/run", headers=manager)
        assert denied.status_code == 403 and allowed.status_code == 200
        assert allowed.json()["status"] == "success"
        assert "secret" not in str(allowed.json()).lower() and "access_key" not in str(allowed.json()).lower()
    finally:
        server_module.store = original_store; server_module.s3_backup = original_backup


def test_repair_endpoint_creates_only_missing_user_jobs(tmp_db_path):
    test_store = ServerSleepStore(db_path=tmp_db_path)
    original_store = server_module.store
    server_module.store = test_store
    try:
        client = TestClient(app)
        headers = _login_headers(client, "repair_user")
        conn = test_store._connect()
        conn.execute(
            "INSERT INTO server_study_sessions "
            "(id,user_id,start_time,end_time,net_duration_minutes,date,updated_at) "
            "VALUES ('repair-s1',1,'2026-07-25 20:00:00+08:00',"
            "'2026-07-25 20:30:00+08:00',30,'2026-07-25',?)",
            (beijing_text(),),
        )
        conn.commit(); conn.close()
        first = client.post(
            "/admin/provider-bindings/atimelogger/repair",
            headers=headers, json={"session_ids": ["repair-s1"]},
        )
        second = client.post(
            "/admin/provider-bindings/atimelogger/repair",
            headers=headers, json={"session_ids": ["repair-s1"]},
        )
        assert first.status_code == second.status_code == 200
        assert (first.json()["operation"], first.json()["repaired"]) == (
            "repair_missing_jobs", 1,
        )
        assert second.json()["repaired"] == 0
    finally:
        server_module.store = original_store
