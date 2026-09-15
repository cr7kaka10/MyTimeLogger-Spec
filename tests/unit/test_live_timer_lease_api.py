import asyncio

import pytest
from fastapi.testclient import TestClient

from server.server import app
import server.server as server_module
from server.store import ServerSleepStore


CAPABILITY = {"X-MTL-Timer-State": "timer-current-state-v1"}


class _SyncHub:
    def __init__(self):
        self.events = []
        self.completed_session_events = []
        self.notification_order = []

    def notify_timer_state(self, user_id, revision):
        self.events.append((user_id, revision))
        self.notification_order.append(("timer_state", user_id, revision))

    def notify_completed_session(self, user_id):
        self.completed_session_events.append(user_id)
        self.notification_order.append(("completed_session", user_id))

    async def start_ticktick_poll(self):
        await asyncio.Event().wait()


@pytest.fixture
def timer_client(tmp_path, monkeypatch):
    store = ServerSleepStore(db_path=str(tmp_path / "api.db"))
    hub = _SyncHub()
    def seed_categories(user_id):
        conn = store._connect()
        try:
            conn.executemany(
                "INSERT OR IGNORE INTO server_categories(user_id,name,group_name,updated_at) VALUES (?,?,'test','now')",
                [(user_id, name) for name in ("输入", "吃饭", "输出", "家庭")],
            )
            conn.commit()
        finally:
            conn.close()
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "sync_hub", hub)
    monkeypatch.setattr(server_module, "_ensure_sample_data_for_user", seed_categories)
    with TestClient(app) as client:
        yield client, hub


def _auth(client, username):
    client.post("/auth/register", json={"username": username, "password": "password123"})
    login = client.post("/auth/login", json={"username": username, "password": "password123"})
    return {"Authorization": f"Bearer {login.json()['token']}", **CAPABILITY}


def _command(client, headers, operation, revision, key, device="pc", category="输入", intent=None, note=""):
    return client.post(f"/api/timer/current/{operation}", headers=headers, json={
        "session_id": "session", "device_id": device, "observed_revision": revision,
        "idempotency_key": key, "user_intent_id": intent or key,
        "category_id": None, "category_name": category, "timer_mode": "countup", "duration_ms": 0,
        "current_note": note,
    })


def test_api_cross_device_current_state_and_user_isolation(timer_client):
    client, hub = timer_client
    first = _auth(client, "first")
    second = _auth(client, "second")
    started = _command(client, first, "start", 0, "start", note="学习任务")
    assert started.status_code == 200
    assert hub.events[-1] == (1, 1)
    assert client.get("/api/timer/current", headers=first).json()["state"]["category_name"] == "输入"
    assert client.get("/api/timer/current", headers=first).json()["state"]["current_note"] == "学习任务"
    assert client.get("/api/timer/current", headers=second).json()["state"] is None
    switched = _command(client, first, "switch", 1, "switch", device="android", category="吃饭")
    assert switched.status_code == 200
    assert switched.json()["state"]["updated_by_device_id"] == "android"
    noted = _command(client, first, "note", 2, "note", device="pc", note="午饭")
    assert noted.status_code == 200
    assert noted.json()["state"]["current_note"] == "午饭"


def test_api_notifies_completed_session_only_after_accepted_switch_or_stop(timer_client):
    client, hub = timer_client
    headers = _auth(client, "completed-session-user")

    started = _command(client, headers, "start", 0, "start")
    assert started.status_code == 200
    assert hub.completed_session_events == []

    switched = _command(client, headers, "switch", 1, "switch", category="输出")
    assert switched.status_code == 200
    assert switched.json()["completed_session_id"]
    assert hub.completed_session_events == [1]
    assert hub.notification_order[-2:] == [("timer_state", 1, 2), ("completed_session", 1)]

    noted = _command(client, headers, "note", 2, "note", note="已切换")
    assert noted.status_code == 200
    assert hub.completed_session_events == [1]

    stopped = _command(client, headers, "stop", 3, "stop")
    assert stopped.status_code == 200
    assert stopped.json()["completed_session_id"]
    assert hub.completed_session_events == [1, 1]
    assert hub.notification_order[-2:] == [("timer_state", 1, 4), ("completed_session", 1)]


def test_api_stale_response_contains_current_snapshot_and_retry_wins(timer_client):
    client, _ = timer_client
    headers = _auth(client, "revision-user")
    assert _command(client, headers, "start", 0, "start").status_code == 200
    assert _command(client, headers, "switch", 1, "pc-switch", category="输出").status_code == 200
    stale = _command(client, headers, "switch", 1, "android-1", device="android", category="家庭", intent="intent")
    assert stale.status_code == 409
    assert stale.json()["error_code"] == "stale_timer_revision"
    assert stale.json()["state"]["revision"] == 2
    retry = _command(client, headers, "switch", 2, "android-2", device="android", category="家庭", intent="intent")
    assert retry.json()["state"]["revision"] == 3
    assert retry.json()["state"]["category_name"] == "家庭"


def test_api_capability_rejects_old_owner_lease_protocol(timer_client):
    client, _ = timer_client
    auth = _auth(client, "upgrade-user")
    no_capability = {"Authorization": auth["Authorization"]}
    assert client.get("/api/timer/current", headers=no_capability).status_code == 426
    capability = client.get("/api/timer/current/capability", headers=no_capability)
    assert capability.json()["capability"] == "timer-current-state-v1"
    old = client.post("/api/timer/lease/acquire", headers={
        **no_capability, "X-MTL-Timer-Lease": "timer-lease-v1",
    }, json={})
    assert old.status_code == 426
