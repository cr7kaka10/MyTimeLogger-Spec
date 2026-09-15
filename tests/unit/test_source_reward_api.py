from fastapi.testclient import TestClient

import server.server as server_module
from server.domain.source_reward_service import SourceRewardService
from server.store import ServerSleepStore


def test_source_reward_api_returns_authoritative_summary_and_rejects_invalid_type(tmp_path):
    original_store, original_service = server_module.store, server_module.source_reward_service
    store = ServerSleepStore(str(tmp_path / "source-reward-api.db"))
    store.create_user("owner@example.test", "password")
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at)
               VALUES(1,'task','task-1',12,7,'2026-08-15 00:00:00')"""
        )
        conn.execute(
            """INSERT INTO server_rewards(id,user_id,title,price,unlock_source_type,unlock_source_id,created_at,updated_at)
               VALUES('reward-1',1,'电影票',0,'checklist_task','task-1','2026-08-15 00:00:00','2026-08-15 00:00:00')"""
        )
    server_module.store = store
    server_module.source_reward_service = SourceRewardService(store._connect)
    server_module.app.dependency_overrides[server_module.get_current_user_optional] = lambda: {"id": 1}
    try:
        client = TestClient(server_module.app)
        payload = client.get("/api/rewards/source/checklist_task/task-1").json()
        assert (payload["coins"], payload["penalty"], payload["itemReward"]["id"]) == (12, 7, "reward-1")
        empty = client.get("/api/rewards/source/habit/missing").json()
        assert (empty["coins"], empty["itemReward"]) == (0, None)
        assert client.get("/api/rewards/source/unknown/task-1").status_code == 400
    finally:
        server_module.app.dependency_overrides.pop(server_module.get_current_user_optional, None)
        server_module.store, server_module.source_reward_service = original_store, original_service


def test_store_and_source_entry_read_the_same_unique_reward_record(tmp_path):
    original_store, original_service = server_module.store, server_module.source_reward_service
    store = ServerSleepStore(str(tmp_path / "source-reward-roundtrip.db"))
    store.create_user("owner@example.test", "password")
    with store._transact() as conn:
        conn.execute(
            "INSERT INTO server_habits(id,user_id,name,is_active,created_at,updated_at) VALUES('habit-1',1,'刷牙',0,'2026-08-15','2026-08-15')"
        )
    server_module.store = store
    server_module.source_reward_service = SourceRewardService(store._connect)
    server_module.app.dependency_overrides[server_module.get_current_user_optional] = lambda: {"id": 1}
    try:
        client = TestClient(server_module.app)
        assert client.post("/api/rewards/config", json={"item_type": "habit", "item_id": "habit-1", "coins": 6, "penalty": 2}).status_code == 200
        created = client.post("/api/rewards", json={
            "title": "电影票", "price": 0, "unlock_source_type": "habit", "unlock_source_id": "habit-1",
            "inventory_mode": "weekly", "inventory_limit": 2, "unlock_required_count": 5,
        }).json()
        reward_id = created["reward_id"]
        source = client.get("/api/rewards/source/habit/habit-1").json()
        store_item = next(item for item in client.get("/api/rewards").json()["rewards"] if item["id"] == reward_id)
        assert source["itemReward"]["id"] == store_item["id"] == reward_id
        assert source["coins"] == 6

        assert client.put(f"/api/rewards/{reward_id}", json={"title": "新电影票", "inventory_limit": 3, "unlock_required_count": 4}).status_code == 200
        source = client.get("/api/rewards/source/habit/habit-1").json()["itemReward"]
        store_item = next(item for item in client.get("/api/rewards").json()["rewards"] if item["id"] == reward_id)
        assert source["title"] == store_item["title"] == "新电影票"
        assert source["inventory_limit"] == store_item["inventory_limit"] == 3
        assert source["unlock_required_count"] == store_item["unlock_required_count"] == 4
    finally:
        server_module.app.dependency_overrides.pop(server_module.get_current_user_optional, None)
        server_module.store, server_module.source_reward_service = original_store, original_service
