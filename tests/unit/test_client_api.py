# -*- coding: utf-8 -*-
import pytest
import httpx
from server.utils.api_client import APIClient


def test_api_client_headers():
    config = {
        "server_sleep_sync": {
            "base_url": "http://test-server:8000",
            "auth_token": "mock-token-123",
            "enabled": True
        },
        "server_mode": True
    }
    client = APIClient(config)
    assert client.base_url == "http://test-server:8000"
    assert client.auth_token == "mock-token-123"
    assert client.server_mode is True

    headers = client._headers()
    assert headers["Authorization"] == "Bearer mock-token-123"
    assert headers["X-Auth-Token"] == "mock-token-123"


def test_api_client_request_success(monkeypatch):
    config = {
        "server_sleep_sync": {
            "base_url": "http://test-server:8000",
            "auth_token": "mock-token-123"
        }
    }
    client = APIClient(config)

    class MockResponse:
        status_code = 200
        text = '{"status": "ok"}'
        def raise_for_status(self):
            pass
        def json(self):
            return {"status": "ok"}

    def mock_request(self, method, url, **kwargs):
        # 确保 header 中包含 token
        assert kwargs["headers"]["Authorization"] == "Bearer mock-token-123"
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "request", mock_request)

    ok, res = client.get("/api/test")
    assert ok is True
    assert res["status"] == "ok"


def test_api_client_request_status_error(monkeypatch):
    config = {
        "server_sleep_sync": {
            "base_url": "http://test-server:8000",
            "auth_token": "mock-token-123"
        }
    }
    client = APIClient(config)

    class MockResponse:
        status_code = 401
        text = "Unauthorized session"
        def raise_for_status(self):
            raise httpx.HTTPStatusError("401 Unauthorized", request=None, response=self)
        def json(self):
            return {"detail": "Invalid session token"}

    def mock_request(self, method, url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "request", mock_request)

    ok, res = client.get("/api/test")
    assert ok is False
    assert "401" in res
    assert "Invalid session token" in res


def test_api_client_network_error(monkeypatch):
    config = {
        "server_sleep_sync": {
            "base_url": "http://test-server:8000",
            "auth_token": "mock-token-123"
        }
    }
    client = APIClient(config)

    def mock_request(self, method, url, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.Client, "request", mock_request)

    ok, res = client.get("/api/test")
    assert ok is False
    assert "网络连接失败" in res
