import pytest
from server.store import ServerSleepStore


@pytest.fixture
def store(tmp_db_path):
    result = ServerSleepStore(db_path=tmp_db_path)
    with result._transact() as conn:
        for uid in (1, 2):
            conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)", (uid, str(uid), 'x', '2026-09-22 00:00:00'))
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES('local_h',1,'阅读',0,'local','2026-09-22 00:00:00','2026-09-22 00:00:00')")
    return result


def test_parent_required_and_other_users_rejected(store):
    for uid, hid in ((1, 'missing'), (2, 'local_h')):
        with pytest.raises(ValueError, match='来源不存在'):
            store.set_item_reward(uid, 'habit', hid, 3)


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True, '5'])
def test_invalid_amounts_rejected(store, value):
    with pytest.raises(ValueError, match='非负有限数字'):
        store.set_item_reward(1, 'habit', 'local_h', value)


def test_stable_configuration_and_version_delivery_without_settlement(store):
    store.set_item_reward(1, 'habit', 'local_h', 3)
    with store._transact() as conn:
        first = dict(conn.execute("SELECT * FROM server_reward_config WHERE item_id='local_h'").fetchone())
        ledger_count = conn.execute('SELECT COUNT(*) FROM server_reward_ledger').fetchone()[0]
        conn.execute("UPDATE server_habits SET name='改名' WHERE id='local_h'")
    store.set_item_reward(1, 'habit', 'local_h', 5)
    with store._transact() as conn:
        row = dict(conn.execute("SELECT * FROM server_reward_config WHERE item_id='local_h'").fetchone())
        assert row['id'] == first['id'] and row['coins'] == 5 and row['updated_at']
        assert conn.execute("SELECT COUNT(*) FROM server_change_log WHERE table_name='server_reward_config' AND record_id=?", (str(row['id']),)).fetchone()[0] == 2
        assert conn.execute('SELECT COUNT(*) FROM server_reward_ledger').fetchone()[0] == ledger_count
        conn.execute("UPDATE server_habits SET is_active=1 WHERE id='local_h'")
    with pytest.raises(ValueError, match='来源不存在'):
        store.set_item_reward(1, 'habit', 'local_h', 99)
    assert store.get_item_reward(1, 'habit', 'local_h')['coins'] == 5
