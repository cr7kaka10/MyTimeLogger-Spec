# -*- coding: utf-8 -*-
from server.store import ServerSleepStore
import pytest


def test_fragment_save_requires_explicit_legacy_conversion(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES('brush',1,'刷牙',0,'local','2026-10-01','2026-10-01')")
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=100)
    store.bind_reward_source(1, reward_id, 'habit', 'brush')
    with store._transact() as conn:
        conn.execute("UPDATE server_rewards SET fragment_measure_mode='percent' WHERE id=?", (reward_id,))
        conn.execute("UPDATE server_reward_source_bindings SET drop_mode='random',drop_min_units=10,drop_max_units=20 WHERE reward_id=?", (reward_id,))
    reward = next(item for item in store.list_rewards(1) if item['id'] == reward_id)
    assert reward['legacy_percent_binding_count'] == 1
    version = reward['fragment_rule_version']
    with pytest.raises(ValueError, match='显式转换'):
        store.update_reward(1, reward_id, fragment_target_count=10, convert_fragment_to_count=False)
    reward = next(item for item in store.list_rewards(1) if item['id'] == reward_id)
    assert (reward['fragment_measure_mode'], reward['fragment_target_count'], reward['legacy_percent_binding_count'], reward['fragment_rule_version']) == ('percent', 100, 1, version)
    assert store.update_reward(1, reward_id, fragment_target_count=10, convert_fragment_to_count=True)
    reward = next(item for item in store.list_rewards(1) if item['id'] == reward_id)
    assert (reward['fragment_measure_mode'], reward['fragment_target_count'], reward['legacy_percent_binding_count']) == ('count', 10, 0)


def test_preexisting_count_fragment_joins_pool_after_explicit_conversion(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES('brush',1,'刷牙',0,'local','2026-10-01','2026-10-01')")
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=100)
    store.bind_reward_source(1, reward_id, 'habit', 'brush', 'fixed', 50, 50)
    service = store.reward_settlement_service
    with store._transact() as conn:
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'old-percent', '刷牙', '2026-10-01')
    store.update_reward(1, reward_id, fragment_target_count=10, convert_fragment_to_count=True)
    with store._transact() as conn:
        for index in range(1, 10):
            service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', f'count:{index}', '刷牙', '2026-10-01')
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 1
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'count:10', '刷牙', '2026-10-01')
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'count:10', '刷牙', '2026-10-01')
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 1
        assert conn.execute("SELECT SUM(progress_units-consumed_units) FROM server_reward_fragments WHERE status='active'").fetchone()[0] == 1
        assert conn.execute("SELECT progress_units FROM server_reward_fragments WHERE completion_event_key='old-percent'").fetchone()[0] == 1


def test_same_completion_event_only_issues_one_fragment(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', '2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_habits (id, user_id, name, is_active, source, created_at, updated_at) VALUES ('habit-1', 1, '刷牙', 0, 'local', '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
    reward_id = store.create_reward(
        1, '手机', price=0, unlock_source_type='habit', unlock_source_id='habit-1',
        unlock_required_count=2, fulfillment_mode='fragment', fragment_target_count=2,
    )
    service = store.reward_settlement_service
    today = service._now()[:10]
    with store._transact() as conn:
        for _ in range(2):
            service.grant_task_unlocks_in_txn(
                conn, 1, 'habit', 'habit-1', f'habit:habit-1:{today}', '刷牙', today,
            )
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE reward_id=?", (reward_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 0


def test_same_item_count_fragments_compose_across_rule_versions_and_habits(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        for habit_id, name in (('brush', '刷牙'), ('face', '洗脸')):
            conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES(?,?,?,0,'local','2026-10-01','2026-10-01')", (habit_id, 1, name))
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=10)
    store.bind_reward_source(1, reward_id, 'habit', 'brush')
    store.bind_reward_source(1, reward_id, 'habit', 'face')
    service = store.reward_settlement_service
    with store._transact() as conn:
        conn.execute("UPDATE server_rewards SET fragment_rule_version=4 WHERE id=?", (reward_id,))
        for index in range(2):
            service.grant_task_unlocks_in_txn(conn, 1, 'habit', ('brush', 'face')[index], f'v4:{index}', '习惯', '2026-10-04')
        conn.execute("UPDATE server_rewards SET fragment_rule_version=5 WHERE id=?", (reward_id,))
        for index in range(8):
            service.grant_task_unlocks_in_txn(conn, 1, 'habit', ('brush', 'face')[index % 2], f'v5:{index}', '习惯', '2026-10-05')
        versions = [row[0] for row in conn.execute("SELECT DISTINCT rule_version FROM server_reward_fragment_contributions c JOIN server_reward_fragments f ON f.id=c.fragment_id ORDER BY rule_version")]
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 1
        assert conn.execute("SELECT SUM(units) FROM server_reward_fragment_contributions").fetchone()[0] == 10
        assert versions == [4, 5]


def test_same_event_remains_idempotent_after_rule_version_changes(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES('brush',1,'刷牙',0,'local','2026-10-01','2026-10-01')")
    reward_id = store.create_reward(1, '解锁手机', price=0, unlock_source_type='habit', unlock_source_id='brush', fulfillment_mode='fragment', fragment_target_count=10)
    with store._transact() as conn:
        service = store.reward_settlement_service
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'same-event', '刷牙', '2026-10-05')
        conn.execute("UPDATE server_rewards SET fragment_rule_version=fragment_rule_version+1 WHERE id=?", (reward_id,))
        service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'same-event', '刷牙', '2026-10-05')
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE reward_id=?", (reward_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_backpack_events WHERE event_type='fragment_acquired'").fetchone()[0] == 1


def test_seven_count_fragments_compose_exactly_once_without_residue(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-10-01')")
        conn.execute("""INSERT INTO server_habits
            (id,user_id,name,is_active,source,created_at,updated_at)
            VALUES('brush',1,'刷牙',0,'local','2026-10-01','2026-10-01')""")
    reward_id = store.create_reward(
        1, '解锁手机', price=0, unlock_source_type='habit', unlock_source_id='brush',
        fulfillment_mode='fragment', fragment_target_count=7,
    )
    with store._transact() as conn:
        for index in range(1, 8):
            created = store.reward_settlement_service.grant_task_unlocks_in_txn(
                conn, 1, 'habit', 'brush', f'brush:{index}', '刷牙', '2026-10-01',
            )
            assert len(created) == (1 if index == 7 else 0)
        active = conn.execute(
            """SELECT COALESCE(SUM(progress_units-consumed_units),0) FROM server_reward_fragments
               WHERE reward_id=? AND fragment_measure_mode='count' AND status='active'""", (reward_id,),
        ).fetchone()[0]
        purchases = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0]
        units = conn.execute("SELECT SUM(units) FROM server_reward_fragment_contributions").fetchone()[0]
    assert (active, purchases, units) == (0, 1, 7)


def test_habit_and_one_time_task_can_fill_the_same_fragment_pool(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', '2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_habits (id,user_id,name,is_active,source,created_at,updated_at) VALUES ('habit-a',1,'刷牙',0,'local','2026-08-01','2026-08-01')")
        conn.execute("INSERT INTO server_tasks (id,user_id,title,status,updated_at) VALUES ('task-c',1,'提交作业',0,'2026-08-01')")
    reward_id = store.create_reward(1, '手机', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=2)
    store.bind_reward_source(1, reward_id, 'habit', 'habit-a')
    store.bind_reward_source(1, reward_id, 'checklist_task', 'task-c')
    with store._transact() as conn:
        store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'habit-a', 'habit:habit-a:2026-08-23', '刷牙', '2026-08-23')
        store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, 'checklist_task', 'task-c', 'checklist:task-c:2026-08-23', '提交作业', '2026-08-23')
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE reward_id=? AND status='consumed'", (reward_id,)).fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy'").fetchone()[0] == 1


def test_custom_spend_template_cannot_be_bound_as_completion_reward(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', '2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_habits (id,user_id,name,is_active,source,created_at,updated_at) VALUES ('habit-a',1,'刷牙',0,'local','2026-08-01','2026-08-01')")
    custom = store.create_reward(1, '零食', price=0, redemption_mode='custom_spend')
    with pytest.raises(ValueError, match='只有完成奖励型商品'):
        store.bind_reward_source(1, custom, 'habit', 'habit-a')


def test_fragment_lifecycle_is_visible_in_backpack_events(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_tasks (id,user_id,title,status,updated_at) VALUES ('t1',1,'任务一',0,'2026-08-01')")
        conn.execute("INSERT INTO server_tasks (id,user_id,title,status,updated_at) VALUES ('t2',1,'任务二',0,'2026-08-01')")
    reward_id = store.create_reward(1, '手机', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=2)
    store.bind_reward_source(1, reward_id, 'checklist_task', 't1')
    store.bind_reward_source(1, reward_id, 'checklist_task', 't2')
    with store._transact() as conn:
        settlement = store.reward_settlement_service
        settlement.grant_task_unlocks_in_txn(conn, 1, 'checklist_task', 't1', 'checklist:t1:1', '任务一', '2026-08-23')
        settlement.grant_task_unlocks_in_txn(conn, 1, 'checklist_task', 't2', 'checklist:t2:1', '任务二', '2026-08-23')
    events = store.list_backpack_events(1)
    types = [event['event_type'] for event in events]
    assert types.count('fragment_acquired') == 2
    assert 'fragment_composed' in types
    composed = next(event for event in events if event['event_type'] == 'fragment_composed')
    assert composed['item_title'] == '手机' and composed['quantity'] == 1


def test_backpack_reconciles_and_lists_only_recent_expired_fragments(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u1','x','2026-09-01')")
        conn.execute("INSERT INTO users VALUES (2,'u2','x','2026-09-01')")
    reward1 = store.create_reward(1, '解锁手机', 0, fulfillment_mode='fragment')
    reward2 = store.create_reward(2, '其他用户物品', 0, fulfillment_mode='fragment')
    rows = [('recent', 1, reward1, 'active', '2026-09-24 08:00:00'),
            ('old', 1, reward1, 'expired', '2026-08-01 08:00:00'),
            ('foreign', 2, reward2, 'active', '2026-09-24 08:00:00')]
    with store._transact() as conn:
        for fragment_id, user_id, reward_id, status, expires_at in rows:
            conn.execute("""INSERT INTO server_reward_fragments
                (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,progress_units,consumed_units,issued_at,expires_at,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,1,25,0,'2026-09-20',?,?,?,?)""",
                (fragment_id, user_id, str(reward_id), 'habit', 'h', fragment_id, expires_at, status, '2026-09-20', '2026-09-20'))
    store.reward_settlement_service._fragments._now = lambda: '2026-09-24 18:00:00'
    store.reward_wallet_service._now = lambda: '2026-09-24 18:00:00'
    for _ in range(2):
        with store._transact() as conn:
            store.reward_settlement_service.expire_fragments_for_user_in_txn(conn, 1)
    expired = store.reward_wallet_service.list_expired_backpack_fragments(1)
    assert [row['fragment_id'] for row in expired] == ['recent']
    with store._connect() as conn:
        assert conn.execute("SELECT status FROM server_reward_fragments WHERE id='foreign'").fetchone()[0] == 'active'
        assert conn.execute("SELECT COUNT(*) FROM server_backpack_events WHERE fragment_id='recent' AND event_type='fragment_expired'").fetchone()[0] == 1


@pytest.mark.parametrize(("drop_mode", "minimum", "maximum"), [
    ("fixed", 60, 60), ("random", 10, 20), ("fixed", None, None),
])
def test_legacy_drop_fields_still_grant_one_fragment(tmp_db_path, drop_mode, minimum, maximum):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-09-05')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES('brush',1,'刷牙',0,'local','2026-09-05','2026-09-05')")
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=7)
    store.bind_reward_source(1, reward_id, 'habit', 'brush', drop_mode, minimum, maximum)
    with store._transact() as conn:
        for _ in range(2):
            store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'habit:brush:2026-09-05', '刷牙', '2026-09-05')
        row = conn.execute("SELECT progress_units,consumed_units FROM server_reward_fragments WHERE reward_id=?", (reward_id,)).fetchone()
        purchases = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0]
    assert tuple(row) == (1, 0)
    assert purchases == 0


def test_legacy_random_sources_share_canonical_count_pool(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-09-05')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES('brush',1,'刷牙',0,'local','2026-09-05','2026-09-05')")
        conn.execute("INSERT INTO server_tasks(id,user_id,title,status,updated_at) VALUES('ad',1,'发广告帖',0,'2026-09-05')")
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment',
                                    fragment_target_count=7, inventory_mode='monthly', inventory_limit=10)
    store.bind_reward_source(1, reward_id, 'habit', 'brush', 'random', 10, 20)
    store.bind_reward_source(1, reward_id, 'checklist_task', 'ad', 'random', 10, 20)
    with store._transact() as conn:
        for index in range(7):
            kind, source = ('habit', 'brush') if index % 2 == 0 else ('checklist_task', 'ad')
            store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, kind, source, f'event:{index}', source, '2026-09-06')
        store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'event:0', '刷牙', '2026-09-06')
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE reward_id=? AND progress_units=1", (reward_id,)).fetchone()[0] == 7
        assert conn.execute("SELECT SUM(units) FROM server_reward_fragment_contributions").fetchone()[0] == 7


def test_legacy_percent_binding_cannot_create_fractional_remainder(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-09-05')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,source,created_at,updated_at) VALUES('h',1,'习惯',0,'local','2026-09-05','2026-09-05')")
    reward_id = store.create_reward(1, '卡片', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=7,
                                    inventory_mode='monthly', inventory_limit=10)
    store.bind_reward_source(1, reward_id, 'habit', 'h', 'fixed', 60, 60)
    with store._transact() as conn:
        for index in range(7):
            store.reward_settlement_service.grant_task_unlocks_in_txn(
                conn, 1, 'habit', 'h', f'event:{index}', '习惯', '2026-09-06' if index < 2 else '2026-09-07')
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE progress_units<>1").fetchone()[0] == 0
        assert [row[0] for row in conn.execute("""SELECT actual FROM (
            SELECT SUM(units) actual FROM server_reward_fragment_contributions GROUP BY batch_id)""")] == [7]
