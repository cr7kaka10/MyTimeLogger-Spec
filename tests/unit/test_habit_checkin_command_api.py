import asyncio

from fastapi.testclient import TestClient

import server.server as server_module
from server.domain.habit_checkin_command_service import HabitCheckinCommandService
from server.models.habit_checkin_command_store import HabitCheckinCommandStore
from server.store import ServerSleepStore
from server.db_wrapper import ServerDBWrapper
from server.sync_hub import SyncHub


def test_habit_command_api_confirms_and_isolated_to_current_user(tmp_path):
    original = (server_module.store, server_module.habit_checkin_command_store, server_module.habit_checkin_command_service)
    store = ServerSleepStore(str(tmp_path / "habit-api.db"))
    store.create_user("owner@example.test", "password")
    store.create_user("other@example.test", "password")
    with store._transact() as conn:
        conn.execute(
                """INSERT INTO server_habits (id,user_id,name,icon,difficulty,source,is_active,created_at,updated_at)
                   VALUES ('local_habit_1',1,'本地习惯','x','easy','local',0,'2026-08-01 09:00:00','2026-08-01 09:00:00')"""
        )
        conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty) VALUES(1,'habit','local_habit_1',1,1)")
    commands = HabitCheckinCommandStore(store._connect)
    server_module.store = store
    server_module.habit_checkin_command_store = commands
    server_module.habit_checkin_command_service = HabitCheckinCommandService(store._transact, store.habit_domain_service, commands)
    server_module.app.dependency_overrides[server_module.get_current_user] = lambda: {"id": 1, "username": "owner@example.test"}
    try:
        client = TestClient(server_module.app)
        payload = {"habit_id": "local_habit_1", "date": "2026-08-01", "desired_status": 2, "idempotency_key": "habit-command-1"}
        assert client.post("/api/habits/checkin-commands", json=payload).json()["status"] == "confirmed"
        assert client.post("/api/habits/checkin-commands", json=payload).json()["status"] == "confirmed"
        server_module.app.dependency_overrides[server_module.get_current_user] = lambda: {"id": 2, "username": "other@example.test"}
        assert client.get("/api/habits/checkin-commands/habit-command-1").status_code == 404
    finally:
        server_module.app.dependency_overrides.pop(server_module.get_current_user, None)
        server_module.store, server_module.habit_checkin_command_store, server_module.habit_checkin_command_service = original


def test_habit_journal_updates_only_confirmed_local_checkin(tmp_path, monkeypatch):
    store = ServerSleepStore(str(tmp_path / "habit-journal.db"))
    store.create_user("journal-owner@example.test", "password")
    store.create_user("journal-other@example.test", "password")
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_habits(id,user_id,name,source,is_active,created_at,updated_at)
            VALUES('local_journal',1,'写日志','local',0,'2026-10-27','2026-10-27')""")
        conn.execute("""INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty)
            VALUES(1,'habit','local_journal',1,1)""")
    assert store.habit_domain_service.checkin_habit(1, "local_journal", "2026-10-27")
    monkeypatch.setattr(server_module, "store", store)
    owner = {"id": 1, "username": "journal-owner@example.test"}
    other = {"id": 2, "username": "journal-other@example.test"}
    server_module.app.dependency_overrides[server_module.get_current_user] = lambda: owner
    try:
        client = TestClient(server_module.app)
        url = "/api/habits/local_journal/checkins/2026-10-27/journal"
        with store._connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1").fetchone()[0]
        saved = client.put(url, json={"note": "😊 今天完成了"})
        assert saved.status_code == 200 and saved.json()["note"] == "😊 今天完成了"
        db = ServerDBWrapper()
        db.log_path = str(tmp_path / "habit-journal.db")
        snapshot = asyncio.run(SyncHub(db).handle_pull_by_version(0, user_id=1))
        assert any(row["note"] == "😊 今天完成了" for row in snapshot["tables"]["habit_checkins"])
        assert client.put(url, json={"note": "😊 今天完成了"}).status_code == 200
        assert client.put(url, json={"note": "x" * 2001}).status_code == 400
        assert client.put(url.replace("2026-10-27", "2026-10-28"), json={"note": "误写"}).status_code == 404
        server_module.app.dependency_overrides[server_module.get_current_user] = lambda: other
        assert client.put(url, json={"note": "越权"}).status_code == 404
        with store._transact() as conn:
            assert conn.execute("SELECT note FROM server_habit_checkins WHERE user_id=1").fetchone()[0] == "😊 今天完成了"
            assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1").fetchone()[0] == before
        assert store.habit_domain_service.cancel_checkin_habit(1, "local_journal", "2026-10-27")
        server_module.app.dependency_overrides[server_module.get_current_user] = lambda: owner
        assert client.put(url, json={"note": "撤销后"}).status_code == 404
    finally:
        server_module.app.dependency_overrides.pop(server_module.get_current_user, None)
