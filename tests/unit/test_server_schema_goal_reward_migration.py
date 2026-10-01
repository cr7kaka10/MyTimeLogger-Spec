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


def test_reward_period_columns_exist_and_upgrade_preserves_ledger(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        new_columns = {
            table: {row['name'] for row in conn.execute(f"PRAGMA table_info({table})")}
            for table in ('server_rewards', 'server_reward_fragments', 'server_reward_ledger')
        }
        assert 'fragment_measure_mode' in new_columns['server_rewards']
        assert 'fragment_measure_mode' in new_columns['server_reward_fragments']
        assert 'expires_at' in new_columns['server_reward_ledger']
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x','2026-10-01')")
        conn.execute("""INSERT INTO server_reward_ledger
            (id,user_id,amount,source_type,source_id,description,target_date,occurred_at,created_at,updated_at)
            VALUES('ledger-1',1,0,'reward_buy','reward-1:event','奖品','2026-10-01','2026-10-01','2026-10-01','2026-10-01')""")
        conn.execute("ALTER TABLE server_rewards DROP COLUMN fragment_measure_mode")
        conn.execute("ALTER TABLE server_reward_fragments DROP COLUMN fragment_measure_mode")
        conn.execute("ALTER TABLE server_reward_ledger DROP COLUMN expires_at")
        ensure_server_schema(conn)
        ensure_server_schema(conn)
        saved = conn.execute("SELECT source_id,amount,expires_at FROM server_reward_ledger WHERE id='ledger-1'").fetchone()
        assert tuple(saved) == ('reward-1:event', 0, None)


def test_fragment_measure_migration_is_explicit_and_idempotent(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x','2026-10-01')")
        conn.execute("""INSERT INTO server_habits
            (id,user_id,name,is_active,source,created_at,updated_at)
            VALUES('habit-1',1,'刷牙',0,'local','2026-10-01','2026-10-01')""")
    count_id = store.create_reward(1, '七枚商品', price=0, redemption_mode='task',
                                   fulfillment_mode='fragment', fragment_target_count=7)
    percent_id = store.create_reward(1, '百分比商品', price=0, redemption_mode='task',
                                     fulfillment_mode='fragment', fragment_target_count=100)
    store.bind_reward_source(1, percent_id, 'habit', 'habit-1', 'fixed', 15, 15)

    ServerSleepStore(db_path=tmp_db_path)
    with store._connect() as conn:
        first = [tuple(row) for row in conn.execute(
            "SELECT id,fragment_measure_mode,fragment_rule_version FROM server_rewards WHERE id IN (?,?) ORDER BY title",
            (count_id, percent_id),
        )]
    ServerSleepStore(db_path=tmp_db_path)
    with store._connect() as conn:
        second = [tuple(row) for row in conn.execute(
            "SELECT id,fragment_measure_mode,fragment_rule_version FROM server_rewards WHERE id IN (?,?) ORDER BY title",
            (count_id, percent_id),
        )]
    assert {row[1] for row in first} == {'count', 'percent'}
    assert first == second


def test_period_expiry_migration_keeps_unlimited_and_expires_old_week(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x','2026-09-01')")
    weekly = store.create_reward(1, '周商品', price=0, redemption_mode='task', fulfillment_mode='fragment',
                                 fragment_target_count=2, inventory_mode='weekly', inventory_limit=10)
    unlimited = store.create_reward(1, '永久商品', price=0, redemption_mode='task', fulfillment_mode='fragment')
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_reward_fragments
            (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,progress_units,issued_at,expires_at,status,created_at,updated_at)
            VALUES('old-fragment',1,?,'habit','h','e',1,1,'2026-09-20','2099-01-01','active','2026-09-20','2026-09-20')""", (weekly,))
        for ledger_id, reward_id in (('weekly-buy', weekly), ('unlimited-buy', unlimited)):
            conn.execute("""INSERT INTO server_reward_ledger
                (id,user_id,amount,source_type,source_id,description,target_date,created_at,updated_at)
                VALUES(?,1,0,'reward_buy',?,'商品','2026-09-20','2026-09-20','2026-09-20')""", (ledger_id, reward_id))
    ServerSleepStore(db_path=tmp_db_path)
    with store._connect() as conn:
        fragment = conn.execute("SELECT expires_at,status FROM server_reward_fragments WHERE id='old-fragment'").fetchone()
        weekly_expiry = conn.execute("SELECT expires_at FROM server_reward_ledger WHERE id='weekly-buy'").fetchone()[0]
        unlimited_expiry = conn.execute("SELECT expires_at FROM server_reward_ledger WHERE id='unlimited-buy'").fetchone()[0]
        expired_events = conn.execute("SELECT COUNT(*) FROM server_backpack_events WHERE ledger_id='weekly-buy' AND event_type='backpack_expired'").fetchone()[0]
        first_updates = tuple(conn.execute("SELECT updated_at FROM server_reward_fragments WHERE id='old-fragment'").fetchone()) + tuple(conn.execute("SELECT updated_at FROM server_reward_ledger WHERE id='weekly-buy'").fetchone())
    ServerSleepStore(db_path=tmp_db_path)
    with store._connect() as conn:
        second_updates = tuple(conn.execute("SELECT updated_at FROM server_reward_fragments WHERE id='old-fragment'").fetchone()) + tuple(conn.execute("SELECT updated_at FROM server_reward_ledger WHERE id='weekly-buy'").fetchone())
        repeated_events = conn.execute("SELECT COUNT(*) FROM server_backpack_events WHERE ledger_id='weekly-buy' AND event_type='backpack_expired'").fetchone()[0]
    assert tuple(fragment) == ('2026-09-21 00:00:00', 'expired')
    assert (weekly_expiry, unlimited_expiry, expired_events) == ('2026-09-21 00:00:00', None, 1)
    assert first_updates == second_updates
    assert repeated_events == 1
