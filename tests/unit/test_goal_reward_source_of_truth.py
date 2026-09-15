from server.store import ServerSleepStore


def test_goal_rewards_use_store_bindings_once_and_ignore_legacy_goal_field(tmp_db_path, monkeypatch):
    monkeypatch.setattr("server.store.now_str", lambda: "2026-08-05 00:00:01")
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1, 'owner', 'x', '2026-08-04 00:00:00')")
        conn.execute(
            """INSERT INTO server_rewards (id,user_id,title,price,is_active,created_at,updated_at)
               VALUES ('legacy-reward',1,'历史字段商品',0,1,'2026-08-04 00:00:00','2026-08-04 00:00:00')"""
        )
        conn.execute(
            """INSERT INTO server_goals
               (id,user_id,title,metric,target_value,period,operator,reward_coins,reward_id,penalty_coins,is_active,created_at,updated_at)
               VALUES ('goal',1,'目标','duration',1,'daily','>=',3,'legacy-reward',2,1,'2026-08-04 00:00:00','2026-08-04 00:00:00')"""
        )
        for reward_id in ("store-reward-a", "store-reward-b"):
            conn.execute(
                """INSERT INTO server_rewards
                   (id,user_id,title,price,unlock_source_type,unlock_source_id,is_active,created_at,updated_at)
                   VALUES (?,1,?,0,'goal','goal',1,'2026-08-04 00:00:00','2026-08-04 00:00:00')""",
                (reward_id, reward_id),
            )
        conn.execute(
            """INSERT INTO server_study_sessions
               (id,user_id,start_time,end_time,net_duration_minutes,date,updated_at)
               VALUES ('session',1,'2026-08-04 08:00:00','2026-08-04 08:01:00',1,'2026-08-04','2026-08-04 08:01:00')"""
        )

    first = store.auto_settle_goals(1)
    assert store.auto_settle_goals(1) == []

    with store._connect() as conn:
        purchases = conn.execute(
            "SELECT id,source_id,amount,target_date FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy' ORDER BY id"
        ).fetchall()
        coins = conn.execute(
            "SELECT amount,source_type FROM server_reward_ledger WHERE user_id=1 AND source_type='goal_reward'"
        ).fetchall()

    assert [row["id"] for row in purchases] == [
        "reward_unlock_store-reward-a_goal_goal_20260804",
        "reward_unlock_store-reward-b_goal_goal_20260804",
    ]
    assert [row["source_id"] for row in purchases] == [
        "store-reward-a:goal:goal_goal_20260804",
        "store-reward-b:goal:goal_goal_20260804",
    ]
    assert all(row["amount"] == 0 and row["target_date"] == "2026-08-04" for row in purchases)
    assert [tuple(row) for row in coins] == [(3.0, "goal_reward")]
    assert len(first) == 3


def test_goal_create_ignores_legacy_reward_id(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1, 'owner', 'x', '2026-08-05 00:00:00')")

    goal_id = store.create_goal(1, "目标", None, "count", 1, "daily", 1, reward_id="missing")

    with store._connect() as conn:
        row = conn.execute("SELECT reward_id FROM server_goals WHERE id=? AND user_id=1", (goal_id,)).fetchone()
    assert row["reward_id"] is None
