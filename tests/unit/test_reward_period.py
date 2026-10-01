import pytest
from datetime import datetime, timedelta

from server.domain.reward_period import period_end
from server.store import ServerSleepStore


@pytest.mark.parametrize(('target', 'mode', 'expected'), [
    ('2026-10-01', 'daily', '2026-10-02 00:00:00'),
    ('2026-09-30 23:59:59', 'weekly', '2026-10-05 00:00:00'),
    ('2026-10-04', 'weekly', '2026-10-05 00:00:00'),
    ('2026-10-05', 'weekly', '2026-10-12 00:00:00'),
    ('2026-10-31', 'monthly', '2026-11-01 00:00:00'),
    ('2026-12-31', 'monthly', '2027-01-01 00:00:00'),
    ('2026-10-01', 'unlimited', None),
])
def test_period_end_uses_beijing_natural_boundaries(target, mode, expected):
    assert period_end(target, mode) == expected


def test_period_end_rejects_unknown_mode():
    with pytest.raises(ValueError, match='库存周期无效'):
        period_end('2026-10-01', 'rolling')


@pytest.mark.parametrize(('mode', 'target_date', 'expected'), [
    ('daily', '2026-10-04', '2026-10-05 00:00:00'),
    ('weekly', '2026-10-04', '2026-10-05 00:00:00'),
    ('monthly', '2026-10-31', '2026-11-01 00:00:00'),
    ('unlimited', '2026-10-31', '2026-11-07 00:00:00'),
])
def test_fragment_expires_at_period_boundary(mode, target_date, expected, tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        conn.execute("""INSERT INTO server_habits
            (id,user_id,name,is_active,source,created_at,updated_at)
            VALUES('h',1,'习惯',0,'local','2026-10-01','2026-10-01')""")
    reward_id = store.create_reward(
        1, '商品', price=0, unlock_source_type='habit', unlock_source_id='h',
        fulfillment_mode='fragment', fragment_target_count=7,
        inventory_mode=mode, inventory_limit=None if mode == 'unlimited' else 10,
    )
    with store._transact() as conn:
        store.reward_settlement_service.grant_task_unlocks_in_txn(
            conn, 1, 'habit', 'h', f'{mode}:1', '习惯', target_date,
        )
        fragment = conn.execute("SELECT id,expires_at FROM server_reward_fragments WHERE reward_id=?", (reward_id,)).fetchone()
    assert fragment['expires_at'] == expected
    service = store.reward_settlement_service._fragments
    before = (datetime.fromisoformat(expected) - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')
    service._now = lambda: before
    with store._transact() as conn:
        assert service.expire_for_user_in_txn(conn, 1) == []
    service._now = lambda: expected
    with store._transact() as conn:
        assert service.expire_for_user_in_txn(conn, 1) == [fragment['id']]
