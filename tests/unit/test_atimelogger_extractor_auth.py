import importlib.util
from pathlib import Path

import requests


MODULE_PATH = Path(__file__).resolve().parents[2] / "server" / "skills" / "time-management" / "modules" / "atimelogger_extractor.py"
spec = importlib.util.spec_from_file_location("atimelogger_extractor_auth_test_module", MODULE_PATH)
extractor_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(extractor_module)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload if payload is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, get_response, post_response=None):
        self.headers = {}
        self.get_response = get_response
        self.post_response = post_response
        self.calls = []

    def get(self, url, **_kwargs):
        self.calls.append(("GET", url))
        return self.get_response

    def post(self, url, **_kwargs):
        self.calls.append(("POST", url))
        return self.post_response


def test_valid_saved_token_loads_types_without_password_login(monkeypatch):
    session = FakeSession(FakeResponse(200, [{"id": "type-1", "name": "睡觉"}]))
    monkeypatch.setattr(extractor_module.requests, "Session", lambda: session)

    extractor = extractor_module.AtimeloggerExtractor({"token": "fixture-token"})

    assert extractor._login() is True
    assert extractor.types_map == {"type-1": {"id": "type-1", "name": "睡觉"}}
    assert [method for method, _url in session.calls] == ["GET"]


def test_rejected_token_and_password_exposes_safe_reauthorization_reason(monkeypatch):
    session = FakeSession(FakeResponse(401), FakeResponse(401))
    monkeypatch.setattr(extractor_module.requests, "Session", lambda: session)

    extractor = extractor_module.AtimeloggerExtractor({"token": "fixture-token", "username": "fixture-user", "password": "fixture-password"})

    assert extractor._login() is False
    assert extractor.failure_reason == "aTimeLogger 授权已失效，请在设置中重新保存账号密码后重试。"
    assert [method for method, _url in session.calls] == ["GET", "POST"]


def test_saved_token_connection_failure_does_not_attempt_password_login(monkeypatch):
    class TimeoutSession:
        def __init__(self):
            self.headers = {}
            self.calls = []

        def get(self, url, **_kwargs):
            self.calls.append(("GET", url))
            raise requests.ConnectTimeout()

        def post(self, url, **_kwargs):
            self.calls.append(("POST", url))
            raise AssertionError("网络故障时不得伪装为重新登录")

    session = TimeoutSession()
    monkeypatch.setattr(extractor_module.requests, "Session", lambda: session)
    extractor = extractor_module.AtimeloggerExtractor({"token": "fixture-token", "username": "fixture-user", "password": "fixture-password"})

    assert extractor._login() is False
    assert extractor.failure_reason == "aTimeLogger 连接失败，请检查网络后重试。"
    assert [method for method, _url in session.calls] == ["GET"]


def test_rejected_intervals_after_token_login_exposes_safe_reauthorization_reason(monkeypatch):
    session = FakeSession(FakeResponse(200, [{"id": "type-1", "name": "睡觉"}]), FakeResponse(401))
    monkeypatch.setattr(extractor_module.requests, "Session", lambda: session)

    extractor = extractor_module.AtimeloggerExtractor({"token": "fixture-token"})

    assert extractor.extract_daily_data("2026-07-18") is None
    assert extractor.failure_reason == "aTimeLogger 授权已失效，请在设置中重新保存账号密码后重试。"
