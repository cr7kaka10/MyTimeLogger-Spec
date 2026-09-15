# -*- coding: utf-8 -*-
from server.models.server_schema import ensure_server_schema
from server.store import ServerSleepStore


def test_goal_and_reward_legacy_migration_is_idempotent_and_user_scoped(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    now = "2026-08-01 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', ?)", (now,))
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (2, 'u2', 'x', ?)", (now,))
        conn.execute("INSERT INTO server_categories (id, user_id, name, group_name, updated_at) VALUES (101, 1, '输入', '工作', ?)", (now,))
        conn.execute("INSERT INTO server_categories (id, user_id, name, group_name, updated_at) VALUES (202, 2, '输出', '工作', ?)", (now,))
        conn.execute("INSERT INTO server_goals (id, user_id, title, category_id, metric, target_value, period, reward_coins, created_at, updated_at) VALUES ('g1', 1, '目标一', 101, 'duration', 360, 'daily', 1, ?, ?)", (now, now))
        conn.execute("INSERT INTO server_goals (id, user_id, title, category_id, metric, target_value, period, reward_coins, created_at, updated_at) VALUES ('g2', 2, '目标二', 202, 'duration', 360, 'daily', 1, ?, ?)", (now, now))
        conn.execute("INSERT INTO server_rewards (id, user_id, title, price, unlock_task_id, created_at, updated_at) VALUES ('r1', 1, '清单奖品', 0, 'task-1', ?, ?)", (now, now))
        conn.execute("INSERT INTO server_rewards (id, user_id, title, price, unlock_task_id, created_at, updated_at) VALUES ('r2', 2, '目标奖品', 0, 'goal_g2', ?, ?)", (now, now))
        ensure_server_schema(conn)
        ensure_server_schema(conn)
        bindings = conn.execute("SELECT user_id, goal_id, category_id FROM server_goal_category_bindings ORDER BY user_id").fetchall()
        rewards = conn.execute("SELECT id, user_id, unlock_source_type, unlock_source_id FROM server_rewards ORDER BY id").fetchall()

    assert [tuple(row) for row in bindings] == [(1, 'g1', 101), (2, 'g2', 202)]
    assert [tuple(row) for row in rewards] == [
        ('r1', 1, 'checklist_task', 'task-1'),
        ('r2', 2, 'goal', 'g2'),
    ]
