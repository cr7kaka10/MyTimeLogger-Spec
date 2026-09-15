import server.server as server_module
from server.store import ServerSleepStore


def _store_with_scores(tmp_db_path, scores):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'exercise','x','2026-08-28 00:00:00')")
        for index, (earned, maximum) in enumerate(scores):
            conn.execute("""INSERT INTO server_exercise_item_scores
                (id,user_id,date,plan_version,item_key,earned_points,max_points,score_rule_version,status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (f's{index}', 1, '2026-08-28', 'v2', f'item-{index}', earned, maximum, 'v2', 'active', '2026-08-28 23:00:00'))
    return store


def test_exercise_completion_reward_requires_all_persisted_applicable_scores(monkeypatch, tmp_db_path):
    store = _store_with_scores(tmp_db_path, [(10, 10), (5, 5)])
    monkeypatch.setattr(server_module, 'store', store)
    with store._transact() as conn:
        status = server_module._settle_exercise_completion_reward_in_txn(conn, 1, '2026-08-28', 'v2', '2026-08-29 00:00:00')
    assert status == (True, 100.0, '全部应评分条目满分')
    with store._connect() as conn:
        rows = conn.execute("SELECT amount FROM server_reward_ledger WHERE source_type='exercise_completion_reward'").fetchall()
    assert [row['amount'] for row in rows] == [100.0]


def test_exercise_completion_reward_records_zero_then_updates_same_fact_on_replay(monkeypatch, tmp_db_path):
    store = _store_with_scores(tmp_db_path, [(10, 10), (4, 5)])
    monkeypatch.setattr(server_module, 'store', store)
    with store._transact() as conn:
        assert server_module._settle_exercise_completion_reward_in_txn(conn, 1, '2026-08-28', 'v2', '2026-08-29 00:00:00')[0] is False
        conn.execute("UPDATE server_exercise_item_scores SET earned_points=max_points")
        server_module._settle_exercise_completion_reward_in_txn(conn, 1, '2026-08-28', 'v2', '2026-08-29 00:00:00')
        server_module._settle_exercise_completion_reward_in_txn(conn, 1, '2026-08-28', 'v2', '2026-08-29 00:00:00')
    with store._connect() as conn:
        rows = conn.execute("SELECT amount FROM server_reward_ledger WHERE source_type='exercise_completion_reward'").fetchall()
    assert [row['amount'] for row in rows] == [100.0]
