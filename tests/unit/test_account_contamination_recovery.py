import sqlite3

from fastapi.testclient import TestClient

import server.server as server_module
from server.server import app
from server.store import ServerSleepStore


def _headers(client, username):
    client.post("/auth/register", json={"username": username, "password": "password123"})
    return {"Authorization": f"Bearer {client.post('/auth/login', json={'username': username, 'password': 'password123'}).json()['token']}"}


def test_contamination_preview_is_admin_only_and_bad_confirmation_has_no_side_effect(tmp_path):
    store, original = ServerSleepStore(str(tmp_path / "server.db")), server_module.store
    server_module.store = store
    try:
        client = TestClient(app); manager = _headers(client, "manager"); target = _headers(client, "target")
        target_id = store.verify_user("target", "password123")
        conn = store._connect()
        conn.execute("INSERT INTO server_habits (id,user_id,name,icon,is_active,created_at,updated_at) VALUES ('keep',1,'manager-only','x',1,'2026-07-28 01:00:00','2026-07-28 01:00:00')")
        conn.execute("INSERT INTO server_habits (id,user_id,name,icon,is_active,created_at,updated_at) VALUES ('bad',?,'target-only','x',1,'2026-07-28 01:00:00','2026-07-28 01:00:00')", (target_id,))
        conn.execute("INSERT INTO server_reward_ledger (id,user_id,amount,source_type,created_at,updated_at) VALUES ('keep-reward',1,1,'habit_checkin','2026-07-28 01:00:00','2026-07-28 01:00:00')")
        conn.execute("INSERT INTO server_reward_ledger (id,user_id,amount,source_type,created_at,updated_at) VALUES ('bad-reward',?,1,'habit_checkin','2026-07-28 01:00:00','2026-07-28 01:00:00')", (target_id,))
        conn.execute("INSERT INTO server_user_wallets (user_id,balance,updated_at) VALUES (?,1,'2026-07-28 01:00:00')", (target_id,))
        conn.execute("INSERT INTO server_system_config (user_id,key,value,updated_at) VALUES (?, 'ticktick_config', '{}', '2026-07-28 01:00:00')", (target_id,)); conn.commit(); conn.close()
        preview = client.get(f"/admin/account-contamination/{target_id}/preview", headers=manager)
        assert preview.status_code == 200 and "target-only" not in str(preview.json())
        assert client.get(f"/admin/account-contamination/{target_id}/preview", headers=target).status_code == 403
        bad = client.post(f"/admin/account-contamination/{target_id}/recover", headers=manager, json={"summary_hash": "wrong", "confirmation_phrase": f"RESTORE USER {target_id}"})
        assert bad.status_code == 409
        conn = sqlite3.connect(store.db_path)
        try: counts = conn.execute("SELECT user_id,COUNT(*) FROM server_habits GROUP BY user_id ORDER BY user_id").fetchall()
        finally: conn.close()
        assert counts == [(1, 1), (target_id, 1)]
        restored = client.post(f"/admin/account-contamination/{target_id}/recover", headers=manager, json={"summary_hash": preview.json()["summary_hash"], "confirmation_phrase": f"RESTORE USER {target_id}"})
        assert restored.status_code == 200
        conn = sqlite3.connect(store.db_path)
        try:
            counts = conn.execute("SELECT user_id,COUNT(*) FROM server_habits GROUP BY user_id").fetchall()
            rewards = conn.execute("SELECT user_id,COUNT(*) FROM server_reward_ledger GROUP BY user_id").fetchall()
            wallets = conn.execute("SELECT COUNT(*) FROM server_user_wallets WHERE user_id=?", (target_id,)).fetchone()[0]
            configs = conn.execute("SELECT COUNT(*) FROM server_system_config WHERE user_id=? AND key='ticktick_config'", (target_id,)).fetchone()[0]
        finally: conn.close()
        assert counts == [(1, 1)] and rewards == [(1, 1)] and wallets == 0 and configs == 0
    finally:
        server_module.store = original
