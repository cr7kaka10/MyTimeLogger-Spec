import pytest
from fastapi.testclient import TestClient
from server.server import app

client = TestClient(app)

# We will mock the get_current_user dependency and the management_plan_service
from server.server import get_current_user, management_plan_service

def override_get_current_user():
    return {"id": 1, "username": "testuser"}

app.dependency_overrides[get_current_user] = override_get_current_user

def test_export_bundle_api(monkeypatch):
    def mock_export_bundle(user_id):
        assert user_id == 1
        return {"schema": "mytimelogger.management-bundle", "version": 1, "nodes": []}
    
    monkeypatch.setattr(management_plan_service, "export_bundle", mock_export_bundle)
    
    response = client.get("/api/v1/management-plan/export")
    assert response.status_code == 200
    assert response.json()["schema"] == "mytimelogger.management-bundle"


def test_preview_bundle_api(monkeypatch):
    def mock_preview_bundle(user_id, mode, bundle):
        assert user_id == 1
        assert mode == "merge"
        return {"nodes": [{"action": "add"}], "relations": []}
        
    monkeypatch.setattr(management_plan_service, "preview_bundle", mock_preview_bundle)
    
    response = client.post("/api/v1/management-plan/import/preview", json={
        "bundle": {"nodes": []},
        "mode": "merge"
    })
    
    assert response.status_code == 200
    assert response.json()["nodes"][0]["action"] == "add"


def test_apply_bundle_api_success(monkeypatch):
    def mock_apply_bundle(user_id, idempotency_key, bundle, mode):
        assert user_id == 1
        assert idempotency_key == "test-key"
        return "rev-123"
        
    monkeypatch.setattr(management_plan_service, "apply_bundle", mock_apply_bundle)
    
    response = client.post("/api/v1/management-plan/import/apply", json={
        "bundle": {"nodes": []},
        "idempotency_key": "test-key",
        "mode": "merge"
    })
    
    assert response.status_code == 200
    assert response.json()["revision_id"] == "rev-123"


def test_apply_bundle_api_missing_key():
    response = client.post("/api/v1/management-plan/import/apply", json={
        "bundle": {"nodes": []},
        "mode": "merge"
    })
    
    assert response.status_code == 422
    assert "Missing idempotency_key" in response.json()["detail"]


def test_apply_bundle_api_validation_error(monkeypatch):
    def mock_apply_bundle(*args, **kwargs):
        raise ValueError("Invalid schema")
        
    monkeypatch.setattr(management_plan_service, "apply_bundle", mock_apply_bundle)
    
    response = client.post("/api/v1/management-plan/import/apply", json={
        "bundle": {"nodes": []},
        "idempotency_key": "test-key"
    })
    
    assert response.status_code == 422
    assert "Invalid schema" in response.json()["detail"]


def test_apply_bundle_api_conflict(monkeypatch):
    def mock_apply_bundle(*args, **kwargs):
        raise Exception("Database locked")
        
    monkeypatch.setattr(management_plan_service, "apply_bundle", mock_apply_bundle)
    
    response = client.post("/api/v1/management-plan/import/apply", json={
        "bundle": {"nodes": []},
        "idempotency_key": "test-key"
    })
    
    assert response.status_code == 409
    assert "Database locked" in response.json()["detail"]
