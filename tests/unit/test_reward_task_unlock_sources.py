# -*- coding: utf-8 -*-
import pytest

from server.store import ServerSleepStore
from server.sync_hub import SyncHub


def _store(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    now = "2026-08-25 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', ?)", (now,))
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (2, 'u2', 'x', ?)", (now,))
        conn.execute("INSERT INTO server_tasks (id, user_id, title, status, updated_at) VALUES ('task-1', 1, '普通任务', 0, ?)", (now,))
        conn.execute("INSERT INTO server_tasks (id, user_id, title, status, updated_at) VALUES ('source-1', 1, '任务来源', 0, ?)", (now,))
        conn.execute("INSERT INTO server_habits (id, user_id, name, is_active, created_at, updated_at) VALUES ('source-2', 1, '习惯来源', 0, ?, ?)", (now, now))
        conn.execute("INSERT INTO server_learning_objectives (id, user_id, title, status, created_at, updated_at) VALUES ('o1', 1, '目标', 0, ?, ?)", (now, now))
        conn.execute("INSERT INTO server_learning_krs (id, user_id, objective_id, title, target_value, current_value, created_at, updated_at) VALUES ('k1', 1, 'o1', '结果', 1, 0, ?, ?)", (now, now))
        conn.execute("INSERT INTO server_learning_tasks (id, user_id, kr_id, title, status, created_at, updated_at) VALUES ('source-3', 1, 'k1', '学习来源', 0, ?, ?)", (now, now))
    for index, source_type in enumerate(("checklist_task", "habit", "learning_task"), start=1):
        store.create_reward(1, source_type, price=0, unlock_source_type=source_type, unlock_source_id=f"source-{index}")
    return store


def test_task_unlocks_have_stable_event_keys_and_idempotent_zero_price_backpack_entries(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    keys = [
        service.completion_event_key("checklist_task", "source-1", "2026-08-25", "revision-1"),
        service.completion_event_key("habit", "source-2", "2026-08-25"),
        service.completion_event_key("learning_task", "source-3", "2026-08-25", "revision-1"),
    ]
    assert keys == [
        "checklist:source-1:revision-1",
        "habit:source-2:2026-08-25",
        "learning:source-3:revision-1",
    ]
    with store._transact() as conn:
        for index, (source_type, event_key) in enumerate(zip(("checklist_task", "habit", "learning_task"), keys), start=1):
            service.grant_task_unlocks_in_txn(conn, 1, source_type, f"source-{index}", event_key, source_type, "2026-08-25")
            service.grant_task_unlocks_in_txn(conn, 1, source_type, f"source-{index}", event_key, source_type, "2026-08-25")
    with store._connect() as conn:
        rows = conn.execute("SELECT id, amount, source_id FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy'").fetchall()
        other_user_rows = conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=2").fetchall()
    assert len(rows) == 3
    assert all(row["amount"] == 0 for row in rows)
    assert other_user_rows == []


def test_task_unlock_source_requires_zero_price(tmp_db_path):
    store = _store(tmp_db_path)
    with pytest.raises(ValueError, match="价格必须为 0"):
        store.create_reward(1, "错误价格", price=1, unlock_source_type="checklist_task", unlock_source_id="task-1")
    reward_id = store.create_reward(1, "正确价格", price=0, unlock_source_type="checklist_task", unlock_source_id="task-1")
    with store._connect() as conn:
        row = conn.execute("SELECT price, unlock_source_type, unlock_source_id FROM server_rewards WHERE id=?", (reward_id,)).fetchone()
    assert tuple(row) == (0.0, "checklist_task", "task-1")


def test_completed_provider_task_immediately_creates_idempotent_store_unlock(tmp_db_path):
    store = _store(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'task','task-1',0.1,0.1,'2026-08-25 12:00:00')")
    reward_id = store.create_reward(1, "test", price=0, unlock_source_type="checklist_task", unlock_source_id="task-1")
    store.log_path = store.db_path
    store.write_server_change = lambda *_args, **_kwargs: None
    hub = SyncHub(store)
    completed = {"completedTime": "2026-08-25T04:00:00.000+0000"}
    hub._reward_task_if_new('task-1', '滴答清单今日计划打钩打标签', completed, 1)
    hub._reward_task_if_new('task-1', '滴答清单今日计划打钩打标签', completed, 1)
    hub._reward_task_if_new('task-1', '滴答清单今日计划打钩打标签', {"completedTime": "2026-08-25 12:00:00+08:00"}, 1)
    with store._connect() as conn:
        unlocks = conn.execute("SELECT source_id FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy' AND source_id LIKE ?", (f"unlock:{reward_id}:%",)).fetchall()
        completions = conn.execute("SELECT source_id FROM server_reward_ledger WHERE user_id=1 AND source_type='task_complete'").fetchall()
    assert len(unlocks) == len(completions) == 1
