from fastapi.testclient import TestClient
from pathlib import Path

import server.server as server_module
from server.db_wrapper import ServerDBWrapper
from server.server import app
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


def _headers(client, username):
    client.post('/auth/register', json={'username': username, 'password': 'password123'})
    token = client.post('/auth/login', json={'username': username, 'password': 'password123'}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def test_ticktick_reset_preview_is_current_user_scoped_and_content_free(tmp_path):
    store, original_store, original_hub = ServerSleepStore(str(tmp_path / 'server.db')), server_module.store, server_module.sync_hub
    server_module.store, server_module.sync_hub = store, SyncHub(ServerDBWrapper(store.db_path))
    try:
        client = TestClient(app); first = _headers(client, 'first'); second = _headers(client, 'second')
        second_id = store.verify_user('second', 'password123')
        conn = store._connect()
        conn.execute("INSERT INTO server_tasks (id,user_id,title,raw_json,updated_at) VALUES ('first-task',1,'first-private','{}','2026-07-28 00:00:00')")
        conn.execute("INSERT INTO server_tasks (id,user_id,title,raw_json,updated_at) VALUES ('second-task',?,'second-private','{}','2026-07-28 00:00:00')", (second_id,))
        conn.execute("INSERT INTO server_tasks (id,user_id,title,raw_json,updated_at) VALUES ('second-orphan-parent',?,'private','{}','2026-07-28 00:00:00')", (second_id,))
        conn.execute("INSERT INTO server_reward_ledger (id,user_id,amount,source_type,source_id,description,target_date,created_at,updated_at) VALUES ('second-orphan-reward',?,1,'task_complete','second-orphan-parent','private','2026-07-28','2026-07-28 00:00:00','2026-07-28 00:00:00')", (second_id,))
        ServerDBWrapper(store.db_path).write_server_change(second_id, 'task', 'second-orphan-parent', 'upsert', {'id': 'second-orphan-parent', 'raw_json': '{}'}, change_id='orphan-parent-history', table_name='server_tasks', conn=conn)
        conn.execute("DELETE FROM server_tasks WHERE user_id=? AND id='second-orphan-parent'", (second_id,))
        conn.commit(); conn.close()
        response = client.post('/checklist/ticktick-reset/preview', headers=second, json={'start_date': '2026-07-25'})
        assert response.status_code == 200
        assert response.json()['counts']['tasks'] == 1 and response.json()['counts']['rewards'] == 1 and 'second-private' not in str(response.json())
        assert client.post('/checklist/ticktick-reset/confirm', headers=second, json={'start_date': '2026-07-25', 'summary_hash': 'wrong', 'confirmation_phrase': f'RESET TICKTICK USER {second_id}'}).status_code == 409
        assert client.post('/checklist/ticktick-reset/confirm', headers=second, json={'start_date': '2026-07-25', 'summary_hash': response.json()['summary_hash'], 'confirmation_phrase': f'RESET TICKTICK USER {second_id}'}).status_code == 200
        pulled = client.get('/api/sync/pull?since_version=0', headers=second).json()
        assert any(row['id'] == 'second-task' and row['_sync_operation'] == 'delete' for row in pulled['tables']['tasks'])
        assert any(row['id'] == 'second-orphan-reward' and row['_sync_operation'] == 'delete' for row in pulled['tables']['reward_ledger'])
        assert client.post('/checklist/ticktick-reset/preview', headers=second, json={'start_date': '2026-07-25'}).json()['counts']['tasks'] == 0
        assert client.post('/checklist/ticktick-reset/preview', headers=first, json={'start_date': '2026-07-25'}).json()['counts']['tasks'] == 1
        conn = store._connect()
        value = conn.execute("SELECT value FROM server_system_config WHERE user_id=? AND key='checklist_sync_start_date'", (second_id,)).fetchone()[0]
        deletes = conn.execute("SELECT user_id,table_name,record_id,operation FROM server_change_log WHERE change_id LIKE 'ticktick-reset:%' AND operation='delete'").fetchall()
        markers = conn.execute("SELECT record_id FROM server_change_log WHERE user_id=? AND table_name='server_system_config' AND change_id LIKE 'ticktick-reset:%' ORDER BY server_version", (second_id,)).fetchall()
        conn.close()
        assert value == '2026-07-25'
        assert [(row['user_id'], row['table_name'], row['record_id'], row['operation']) for row in deletes] == [
            (second_id, 'server_reward_ledger', 'second-orphan-reward', 'delete'),
            (second_id, 'server_tasks', 'second-task', 'delete'),
        ]
        assert [row['record_id'] for row in markers] == ['checklist_sync_start_date', 'checklist_ticktick_reset_marker']
    finally:
        server_module.store, server_module.sync_hub = original_store, original_hub


def test_ping_declares_ticktick_reset_capability():
    response = TestClient(app).get('/ping')
    assert response.status_code == 200
    assert response.json()['capabilities']['checklist_ticktick_reset']['version'] == 1


def test_local_startup_requires_ticktick_reset_capability():
    source = Path('scripts/start-local-process.ps1').read_text(encoding='utf-8')
    assert '$checklistResetVersion = 1' in source
    assert '$readiness.capabilities.checklist_ticktick_reset' in source
    assert '[int]$checklistCapability.version -eq $checklistResetVersion' in source
    assert '不复用可能持有陈旧模块缓存的 Vite' in source
    assert 'Git revision 不能证明源码未变' in source
    assert 'Get-ProjectElectronPrimaries' in source
    assert "desktop\\node_modules\\electron\\dist\\electron.exe" in source
