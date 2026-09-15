from fastapi.testclient import TestClient

import server.server as server_module
from server.domain.habit_checkin_command_service import HabitCheckinCommandService
from server.models.habit_checkin_command_store import HabitCheckinCommandStore
from server.store import ServerSleepStore


def test_habit_command_api_confirms_and_isolated_to_current_user(tmp_path):
    original = (server_module.store, server_module.habit_checkin_command_store, server_module.habit_checkin_command_service)
    store = ServerSleepStore(str(tmp_path / "habit-api.db"))
    store.create_user("owner@example.test", "password")
    store.create_user("other@example.test", "password")
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_habits (id,user_id,name,icon,difficulty,is_active,created_at,updated_at)
               VALUES ('local_habit_1',1,'本地习惯','x','easy',1,'2026-08-01 09:00:00','2026-08-01 09:00:00')"""
        )
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
