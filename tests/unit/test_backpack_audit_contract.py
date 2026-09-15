import pytest
from server.store import ServerSleepStore


def test_audit_cleanup_is_user_scoped_and_rolls_back(tmp_db_path, monkeypatch):
    store = ServerSleepStore(db_path=tmp_db_path)
    service = store.reward_settlement_service
    monkeypatch.setattr(service, '_now', lambda: '2026-08-04 12:00:00')
    with store._transact() as conn:
        for user_id in (1, 2):
            conn.execute("INSERT INTO users VALUES (?,?,'x','2026-08-01 00:00:00')", (user_id, f'u{user_id}'))
        wallet = store.reward_wallet_service
        wallet.append_ledger_in_txn(conn, 1, 0, 'reward_buy', 'unlock:r:habit:h', 'invalid', '2026-08-03', 'invalid-id')
        wallet.append_ledger_in_txn(conn, 1, 0, 'reward_buy', 'manual', 'manual', '2026-08-03', 'manual-id')
        wallet.append_ledger_in_txn(conn, 2, 0, 'reward_buy', 'unlock:r:habit:h', 'foreign', '2026-08-03', 'foreign-id')
    preview = service.preview_invalid_habit_unlocks(1)
    assert preview['count'] == 1 and preview['items'][0]['id'] == 'invalid-id'
    original = service._reward_wallet.remove_ledger_entries_in_txn
    monkeypatch.setattr(service._reward_wallet, 'remove_ledger_entries_in_txn', lambda conn, *args: (original(conn, *args), (_ for _ in ()).throw(RuntimeError('rollback')))[0])
    with pytest.raises(RuntimeError, match='rollback'):
        service.remove_invalid_habit_unlocks(1, preview['summary_hash'])
    monkeypatch.setattr(service._reward_wallet, 'remove_ledger_entries_in_txn', original)
    assert service.remove_invalid_habit_unlocks(1, preview['summary_hash']) == 1
    with store._connect() as conn:
        ids = {row['id'] for row in conn.execute('SELECT id FROM server_reward_ledger')}
        events = [row['event_type'] for row in conn.execute("SELECT event_type FROM server_backpack_events WHERE user_id=1")]
    assert {'manual-id', 'foreign-id'}.issubset(ids) and 'invalid-id' not in ids and events.count('revoked') == 1
