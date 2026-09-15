# -*- coding: utf-8 -*-
from server.store import ServerSleepStore
from server.domain.source_reward_service import SourceRewardService
import server.domain.reward_fragment_service as fragment_module
import pytest


def test_same_completion_event_only_issues_one_fragment(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', '2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_habits (id, user_id, name, is_active, created_at, updated_at) VALUES ('habit-1', 1, '刷牙', 0, '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
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


def test_habit_and_one_time_task_can_fill_the_same_fragment_pool(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', '2026-08-01 00:00:00')")
        conn.execute("INSERT INTO server_habits (id,user_id,name,is_active,created_at,updated_at) VALUES ('habit-a',1,'刷牙',0,'2026-08-01','2026-08-01')")
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
        conn.execute("INSERT INTO server_habits (id,user_id,name,is_active,created_at,updated_at) VALUES ('habit-a',1,'刷牙',0,'2026-08-01','2026-08-01')")
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


def test_random_progress_units_are_persisted_and_replay_does_not_reroll(tmp_db_path, monkeypatch):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-09-05')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,created_at,updated_at) VALUES('brush',1,'刷牙',0,'2026-09-05','2026-09-05')")
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment', fragment_target_count=7)
    store.bind_reward_source(1, reward_id, 'habit', 'brush', 'random', 10, 20)
    rolls = []
    monkeypatch.setattr(fragment_module.secrets, "randbelow", lambda width: rolls.append(width) or 7)
    with store._transact() as conn:
        for _ in range(2):
            store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'habit:brush:2026-09-05', '刷牙', '2026-09-05')
        row = conn.execute("SELECT progress_units,consumed_units FROM server_reward_fragments WHERE reward_id=?", (reward_id,)).fetchone()
    assert tuple(row) == (17, 0)
    assert rolls == [11]


def test_random_multi_source_progress_is_shared_and_each_100_composes_once(tmp_db_path, monkeypatch):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-09-05')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,created_at,updated_at) VALUES('brush',1,'刷牙',0,'2026-09-05','2026-09-05')")
        conn.execute("INSERT INTO server_tasks(id,user_id,title,status,updated_at) VALUES('ad',1,'发广告帖',0,'2026-09-05')")
    reward_id = store.create_reward(1, '解锁手机', price=0, redemption_mode='task', fulfillment_mode='fragment',
                                    fragment_target_count=100, inventory_mode='monthly', inventory_limit=10)
    store.bind_reward_source(1, reward_id, 'habit', 'brush', 'random', 10, 20)
    store.bind_reward_source(1, reward_id, 'checklist_task', 'ad', 'random', 10, 20)
    rolls = []
    monkeypatch.setattr(fragment_module.secrets, "randbelow", lambda width: rolls.append(width) or 5)
    with store._transact() as conn:
        for index in range(7):
            kind, source = ('habit', 'brush') if index % 2 == 0 else ('checklist_task', 'ad')
            store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, kind, source, f'event:{index}', source, '2026-09-06')
        store.reward_settlement_service.grant_task_unlocks_in_txn(conn, 1, 'habit', 'brush', 'event:0', '刷牙', '2026-09-06')
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='reward_buy'").fetchone()[0] == 1
    summaries = [SourceRewardService(store._connect).summary(1, kind, source) for kind, source in (('habit', 'brush'), ('checklist_task', 'ad'))]
    assert [item['fragmentProgress'][reward_id]['percent'] for item in summaries] == [5, 5]
    assert all(item['fragmentProgress'][reward_id]['inventoryUsed'] == 1 for item in summaries)
    assert store.reward_wallet_service.list_backpack_fragments(1)[0]['progress_percent'] == 5
    assert len(rolls) == 7
