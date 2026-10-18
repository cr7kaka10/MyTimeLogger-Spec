import pytest
from datetime import datetime, timedelta

from server.domain.reward_candidate_builder import RewardCandidateBuilder
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


@pytest.mark.parametrize(('mode', 'event_date', 'boundary', 'expired'), [
    ('daily', '2026-10-01', '2026-10-02 00:00:00', True),
    ('weekly', '2026-10-04', '2026-10-05 00:00:00', True),
    ('monthly', '2026-09-30', '2026-10-01 00:00:00', True),
    ('unlimited', '2026-09-30', '2026-10-01 00:00:00', False),
])
def test_candidate_rebuild_keeps_period_assets_and_provenance(mode, event_date, boundary, expired, tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x',?)", (event_date,))
        for habit in ('fragment-habit', 'card-habit'):
            conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES(?,1,?,0,'local',?,?)", (habit, habit, event_date, event_date))
            conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'habit',?,0,0,?)", (habit, event_date))
            conn.execute("""INSERT INTO server_habit_checkins
                (id,user_id,habit_id,checkin_date,checkin_time,status,updated_at)
                VALUES(?,1,?,?,?,2,?)""", (f'check:{habit}', habit, event_date, f'{event_date} 08:00:00', f'{event_date} 08:00:00'))
    limit = None if mode == 'unlimited' else 10
    fragment_reward = store.create_reward(1, '碎片商品', price=0, unlock_source_type='habit', unlock_source_id='fragment-habit', fulfillment_mode='fragment', fragment_target_count=7, inventory_mode=mode, inventory_limit=limit)
    card_reward = store.create_reward(1, '完整商品', price=0, unlock_source_type='habit', unlock_source_id='card-habit', fulfillment_mode='fragment', fragment_target_count=1, inventory_mode=mode, inventory_limit=limit)
    store.reward_wallet_service._now = lambda: boundary
    store.reward_settlement_service._fragments._now = lambda: boundary

    first = RewardCandidateBuilder(store).build(1, event_date)
    with store._connect() as conn:
        state = (
            tuple(conn.execute("SELECT status,expires_at FROM server_reward_fragments WHERE reward_id=?", (fragment_reward,)).fetchone()),
            tuple(conn.execute("SELECT expires_at FROM server_reward_ledger WHERE source_type='reward_buy' AND source_id LIKE ?", (f'unlock:{card_reward}:fragment:%',)).fetchone()),
            tuple(conn.execute("SELECT provenance_kind,required_units,output_quantity FROM server_reward_fragment_batches WHERE reward_id=?", (card_reward,)).fetchone()),
        )
    second = RewardCandidateBuilder(store).build(1, event_date)
    with store._connect() as conn:
        repeated_state = (
            tuple(conn.execute("SELECT status,expires_at FROM server_reward_fragments WHERE reward_id=?", (fragment_reward,)).fetchone()),
            tuple(conn.execute("SELECT expires_at FROM server_reward_ledger WHERE source_type='reward_buy' AND source_id LIKE ?", (f'unlock:{card_reward}:fragment:%',)).fetchone()),
            tuple(conn.execute("SELECT provenance_kind,required_units,output_quantity FROM server_reward_fragment_batches WHERE reward_id=?", (card_reward,)).fetchone()),
        )
    stable_keys = ('ledger_rows', 'balance', 'source_counts', 'backpack_items', 'fragment_rows', 'habit_events')
    assert {key: first[key] for key in stable_keys} == {key: second[key] for key in stable_keys}
    assert state == repeated_state
    assert state[0][0] == ('expired' if expired else 'active')
    assert state[1][0] == (boundary if expired else None)
    assert state[2] == ('exact', 1, 1)
