# -*- coding: utf-8 -*-
import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from server.store import ServerSleepStore
from server.domain.source_reward_service import SourceRewardService


def _store(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', '2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_habits (id, user_id, name, is_active, source, created_at, updated_at) VALUES ('habit-1', 1, '刷牙', 0, 'local', '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
    return store


def test_weekly_inventory_is_supported_and_requires_positive_limit(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(1, '周商品', price=1, inventory_mode='weekly', inventory_limit=1)
    with store._connect() as conn:
        assert tuple(conn.execute("SELECT inventory_mode,inventory_limit FROM server_rewards WHERE id=?", (reward_id,)).fetchone()) == ('weekly', 1)
    with pytest.raises(ValueError, match='正整数'):
        store.create_reward(1, '非法周商品', price=1, inventory_mode='weekly', inventory_limit=0)


def test_updating_weekly_reward_preserves_weekly_mode(tmp_db_path):
    store = _store(tmp_db_path)
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_rewards
               (id,user_id,title,icon,price,inventory_mode,inventory_limit,is_active,created_at,updated_at)
               VALUES ('legacy-weekly',1,'旧商品','🎁',1,'weekly',1,1,'2026-08-01 00:00:00','2026-08-01 00:00:00')"""
        )
    assert store.update_reward(1, 'legacy-weekly', title='已迁移商品')
    with store._connect() as conn:
        assert conn.execute("SELECT inventory_mode FROM server_rewards WHERE id='legacy-weekly'").fetchone()[0] == 'weekly'


def test_weekly_inventory_window_resets_on_beijing_monday():
    window = ServerSleepStore._validate_reward_rules('weekly', 10, None, 1)
    assert window[:2] == ('weekly', 10)
    from server.domain.reward_settlement_service import RewardSettlementService
    assert RewardSettlementService._inventory_window('2026-10-04', 'weekly') == ('2026-09-28', '2026-10-04')
    assert RewardSettlementService._inventory_window('2026-10-05', 'weekly') == ('2026-10-05', '2026-10-11')


def test_one_time_source_can_contribute_to_shared_fragment_target():
    assert ServerSleepStore._validate_fragment_rules('checklist_task', 'fragment', 2) == ('fragment', 2)


def test_habit_fragments_compose_after_target_count(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '三次刷牙奖品', price=0, unlock_source_type='habit', unlock_source_id='habit-1',
        unlock_required_count=3, fulfillment_mode='fragment', fragment_target_count=3,
    )
    service = store.reward_settlement_service
    today = service._now()[:10]
    with store._transact() as conn:
        for index in range(1, 4):
            created = service.grant_task_unlocks_in_txn(
                conn, 1, 'habit', 'habit-1', f'habit:habit-1:{today}:{index}', '刷牙', today,
            )
            assert len(created) == (1 if index == 3 else 0)
        fragments = conn.execute(
            "SELECT status,expires_at,progress_units,consumed_units FROM server_reward_fragments WHERE reward_id=? ORDER BY id", (reward_id,),
        ).fetchall()
        assert len(fragments) == 3
        assert sum(row['progress_units'] - row['consumed_units'] for row in fragments) == 0
        assert all(row['expires_at'] > service._now() for row in fragments)
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy'").fetchone()[0] == 1


def test_period_reconcile_composes_cross_version_pool_once(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment',
        fragment_target_count=10, inventory_mode='monthly', inventory_limit=1,
    )
    with store._transact() as conn:
        for index in range(10):
            version = 4 if index < 2 else 5
            conn.execute("""INSERT INTO server_reward_fragments
                (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,
                 fragment_measure_mode,progress_units,consumed_units,issued_at,expires_at,status,created_at,updated_at)
                VALUES(?,1,?,'habit',?, ?,?,'count',1,0,?,'2026-11-01 00:00:00','active',?,?)""",
                (f'f{index}', reward_id, f'h{index}', f'event:{index}', version,
                 f'2026-10-0{4 if version == 4 else 5} 00:00:00', '2026-10-05 00:00:00', '2026-10-05 00:00:00'))
        store.reward_settlement_service._fragments._now = lambda: '2026-10-16 12:00:00'
        first = store.reward_settlement_service.reconcile_period_inventory_in_txn(conn, 1)
        second = store.reward_settlement_service.reconcile_period_inventory_in_txn(conn, 1)
        assert (len(first['composed_items']), len(second['composed_items'])) == (1, 0)
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 1
        assert conn.execute("SELECT SUM(units) FROM server_reward_fragment_contributions").fetchone()[0] == 10


def test_backpack_projects_one_count_progress_per_reward_across_versions(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=10)
    with store._transact() as conn:
        for index in range(8):
            conn.execute("""INSERT INTO server_reward_fragments
                (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,
                 fragment_measure_mode,progress_units,consumed_units,issued_at,expires_at,status,created_at,updated_at)
                VALUES(?,1,?,'habit','h',?,?, 'count',1,0,'2026-10-05','2026-11-01','active','2026-10-05','2026-10-05')""",
                (f'f{index}', reward_id, f'event:{index}', 4 if index < 2 else 5))
    store.reward_wallet_service._now = lambda: '2026-10-16 12:00:00'
    progress = store.reward_wallet_service.list_backpack_fragments(1)
    assert len(progress) == 1
    assert (progress[0]['id'], progress[0]['current_count'], progress[0]['target_count']) == (f'fragment:{reward_id}', 8, 10)


def test_monthly_limit_is_checked_before_consuming_piece_units(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment',
                                    fragment_target_count=2, inventory_mode='monthly', inventory_limit=1)
    store.bind_reward_source(1, reward_id, 'habit', 'habit-1', 'fixed', 50, 50)
    service = store.reward_settlement_service
    with store._transact() as conn:
        for index in range(4):
            service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'habit-1', f'sep:{index}', '刷牙', '2026-09-05')
        held = conn.execute("SELECT SUM(progress_units-consumed_units) FROM server_reward_fragments WHERE reward_id=? AND status='active'", (reward_id,)).fetchone()[0]
        purchases = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0]
        assert (held, purchases) == (2, 1)
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'habit-1', 'oct:1', '刷牙', '2026-10-01')
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'habit-1', 'oct:2', '刷牙', '2026-10-01')
        held_next = conn.execute("SELECT COALESCE(SUM(progress_units-consumed_units),0) FROM server_reward_fragments WHERE reward_id=? AND status='active'", (reward_id,)).fetchone()[0]
        purchases_next = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0]
    assert (held_next, purchases_next) == (0, 2)


def test_monthly_seven_piece_reward_caps_at_ten_without_consuming_overflow(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment',
        fragment_target_count=7, inventory_mode='monthly', inventory_limit=10,
    )
    store.bind_reward_source(1, reward_id, 'habit', 'habit-1')
    with store._transact() as conn:
        for index in range(77):
            store.reward_settlement_service.grant_task_unlocks_in_txn(
                conn, 1, 'habit', 'habit-1', f'oct:{index}', '刷牙', '2026-10-01',
            )
        purchases = conn.execute(
            "SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy' AND source_id LIKE ?",
            (f'unlock:{reward_id}:%',),
        ).fetchone()[0]
        held = conn.execute(
            """SELECT SUM(progress_units-consumed_units) FROM server_reward_fragments
               WHERE reward_id=? AND status='active'""", (reward_id,),
        ).fetchone()[0]
        for index in range(77):
            store.reward_settlement_service.grant_task_unlocks_in_txn(
                conn, 1, 'habit', 'habit-1', f'oct:{index}', '刷牙', '2026-10-01',
            )
    assert (purchases, held) == (10, 7)


def test_concurrent_fragment_events_do_not_exceed_period_limit(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '限量卡', price=0, redemption_mode='task', fulfillment_mode='fragment',
        fragment_target_count=1, inventory_mode='monthly', inventory_limit=1,
    )
    store.bind_reward_source(1, reward_id, 'habit', 'habit-1')
    gate = Barrier(2)

    def grant(index):
        local = ServerSleepStore(db_path=tmp_db_path)
        gate.wait()
        with local._transact() as conn:
            return local.reward_settlement_service.grant_task_unlocks_in_txn(
                conn, 1, 'habit', 'habit-1', f'parallel:{index}', '刷牙', '2026-10-01',
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(grant, range(2)))
    with store._connect() as conn:
        purchases = conn.execute(
            "SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy' AND source_id LIKE ?",
            (f'unlock:{reward_id}:%',),
        ).fetchone()[0]
        held = conn.execute(
            "SELECT COUNT(*) FROM server_reward_fragments WHERE reward_id=? AND status='active'", (reward_id,),
        ).fetchone()[0]
    assert sum(len(item) for item in results) == 1
    assert (purchases, held) == (1, 1)


def test_weekly_count_summary_reports_pieces_usage_and_expiry(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '周卡', price=0, unlock_source_type='habit', unlock_source_id='habit-1',
        fulfillment_mode='fragment', fragment_target_count=7,
        inventory_mode='weekly', inventory_limit=10,
    )
    with store._transact() as conn:
        store.reward_settlement_service.grant_task_unlocks_in_txn(
            conn, 1, 'habit', 'habit-1', 'week:1', '刷牙', '2026-10-04',
        )
    summary = SourceRewardService(store._connect, lambda: '2026-10-04 23:59:59').summary(1, 'habit', 'habit-1')
    progress = summary['fragmentProgress'][reward_id]
    assert (progress['activePieces'], progress['targetPieces']) == (1, 7)
    assert (progress['periodUsed'], progress['availableItems']) == (0, 0)
    assert (progress['periodMode'], progress['expiresAt']) == ('weekly', '2026-10-05 00:00:00')


def test_fragment_expiry_and_consumed_fragment_cancellation(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '两次刷牙奖品', price=0, unlock_source_type='habit', unlock_source_id='habit-1',
        unlock_required_count=2, fulfillment_mode='fragment', fragment_target_count=2,
    )
    service = store.reward_settlement_service
    fragments = service._fragments
    fragments._now = lambda: '2026-09-06 12:00:00'
    with store._transact() as conn:
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'habit-1', 'habit:habit-1:2026-09-06', '刷牙', '2026-09-06')
        fragments._now = lambda: '2026-09-08 12:00:00'
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'habit-1', 'habit:habit-1:2026-09-08', '刷牙', '2026-09-08')
        rows = conn.execute("SELECT status FROM server_reward_fragments WHERE reward_id=? ORDER BY issued_at", (reward_id,)).fetchall()
        assert [row['status'] for row in rows] == ['expired', 'active']

        fragments._now = lambda: '2026-09-08 13:00:00'
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'habit-1', 'habit:habit-1:2026-09-08:second', '刷牙', '2026-09-08')
        service.revoke_fragments_for_event_in_txn(conn, 1, 'habit', 'habit-1', 'habit:habit-1:2026-09-08')
        states = [row['status'] for row in conn.execute(
            "SELECT status FROM server_reward_fragments WHERE reward_id=? ORDER BY issued_at", (reward_id,),
        ).fetchall()]
        assert states == ['expired', 'revoked', 'active']
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 0


def test_update_cannot_introduce_a_new_exercise_unlock_source(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(1, '普通商品', price=1)
    with pytest.raises(ValueError, match='解锁来源无效'):
        store.update_reward(
            1, reward_id, price=0, unlock_source_type='exercise_checkin', unlock_source_id='exercise-1'
        )


def test_habit_unlock_source_accepts_normal_and_rejects_archived_or_foreign(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '正常习惯商品', price=0, unlock_source_type='habit', unlock_source_id='habit-1'
    )

    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (2, 'u2', 'x', '2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_habits (id, user_id, name, is_active, created_at, updated_at) VALUES ('habit-archived', 1, '已归档', 1, '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_habits (id, user_id, name, is_active, created_at, updated_at) VALUES ('habit-foreign', 2, '其他账号', 0, '2026-08-01 00:00:00', '2026-08-01 00:00:00')")

    assert reward_id
    for habit_id in ('habit-archived', 'habit-foreign'):
        with pytest.raises(ValueError, match='解锁来源不存在或不属于当前账号'):
            store.create_reward(1, f'{habit_id} 商品', price=0, unlock_source_type='habit', unlock_source_id=habit_id)

    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=1").fetchone()[0] == 1


def test_new_source_reward_replaces_binding_but_keeps_old_store_item(tmp_db_path):
    store = _store(tmp_db_path)
    old_id = store.create_reward(1, '旧奖励', price=0, unlock_source_type='habit', unlock_source_id='habit-1')
    new_id = store.create_reward(1, '新奖励', price=0, unlock_source_type='habit', unlock_source_id='habit-1')
    with store._connect() as conn:
        old = conn.execute("SELECT is_active,unlock_source_id FROM server_rewards WHERE id=?", (old_id,)).fetchone()
        new = conn.execute("SELECT is_active,unlock_source_id FROM server_rewards WHERE id=?", (new_id,)).fetchone()
        assert tuple(old) == (1, None)
        assert tuple(new) == (1, 'habit-1')

    assert store.update_reward(1, new_id, unlock_source_type=None, unlock_source_id=None, unlock_task_id=None)
    with store._connect() as conn:
        detached = conn.execute(
            "SELECT is_active,unlock_source_type,unlock_source_id,unlock_required_count FROM server_rewards WHERE id=?",
            (new_id,),
        ).fetchone()
        assert tuple(detached) == (1, None, None, 1)


def test_habit_reward_edit_keeps_fragment_fields(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '刷牙奖品', price=0, unlock_source_type='habit', unlock_source_id='habit-1',
        inventory_mode='monthly', inventory_limit=2, unlock_required_count=5,
        fulfillment_mode='fragment', fragment_target_count=5,
    )

    reward = next(item for item in store.list_rewards(1) if item['id'] == reward_id)
    assert reward['unlock_source_type'] == 'habit'
    assert reward['unlock_source_id'] == 'habit-1'
    assert reward['inventory_mode'] == 'monthly'
    assert reward['inventory_limit'] == 2
    assert reward['unlock_required_count'] == 5
    assert reward['fulfillment_mode'] == 'fragment'
    assert reward['fragment_target_count'] == 5


def test_existing_reward_saves_seven_fragments_and_monthly_ten(tmp_db_path):
    store = _store(tmp_db_path)
    reward_id = store.create_reward(
        1, '解锁手机', price=0, unlock_source_type='habit', unlock_source_id='habit-1',
        fulfillment_mode='fragment', fragment_target_count=5,
    )
    with store._transact() as conn:
        conn.execute("DELETE FROM server_change_log WHERE user_id=1")

    assert store.update_reward(
        1, reward_id, inventory_mode='monthly', inventory_limit=10,
        fulfillment_mode='fragment', fragment_target_count=7,
    )
    with store._connect() as conn:
        reward = conn.execute(
            "SELECT inventory_mode,inventory_limit,fulfillment_mode,fragment_target_count "
            "FROM server_rewards WHERE id=?", (reward_id,),
        ).fetchone()
        published = conn.execute(
            "SELECT COUNT(*) FROM server_change_log WHERE user_id=1 AND table_name='server_rewards' AND record_id=?",
            (reward_id,),
        ).fetchone()[0]
    assert tuple(reward) == ('monthly', 10, 'fragment', 7)
    assert published == 1
