from server.store import ServerSleepStore
import pytest


def test_goal_fragment_is_granted_once_with_coins(tmp_db_path, monkeypatch):
    monkeypatch.setattr('server.store.now_str', lambda: '2026-08-05 09:00:00')
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'owner','x','2026-08-04 00:00:00')")
        conn.execute("INSERT INTO server_system_config(user_id,key,value,value_type,updated_at) VALUES(1,'statistics_start_date','2026-08-04','string','2026-08-04 00:00:00')")
        conn.execute("""INSERT INTO server_goals(id,user_id,title,metric,target_value,period,operator,reward_coins,penalty_coins,is_active,created_at,updated_at)
            VALUES('g',1,'目标','duration',1,'daily','>=',3,2,1,'2026-08-04 00:00:00','2026-08-04 00:00:00')""")
        conn.execute("""INSERT INTO server_study_sessions(id,user_id,start_time,end_time,net_duration_minutes,date,updated_at)
            VALUES('s',1,'2026-08-04 08:00:00','2026-08-04 08:01:00',1,'2026-08-04','2026-08-04 08:01:00')""")
        conn.execute("""INSERT INTO server_rewards(id,user_id,title,price,redemption_mode,fulfillment_mode,fragment_target_count,is_active,created_at,updated_at)
            VALUES('r',1,'物品',0,'task','fragment',1,1,'2026-08-04 00:00:00','2026-08-04 00:00:00')""")
        conn.execute("""INSERT INTO server_reward_source_bindings(id,user_id,reward_id,source_type,source_id,created_at,updated_at)
            VALUES('b',1,'r','goal','g','2026-08-04 00:00:00','2026-08-04 00:00:00')""")
    assert store.auto_settle_goals(1)
    assert store.auto_settle_goals(1) == []
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE user_id=1 AND source_type='goal'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy'").fetchone()[0] == 1
        assert conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='goal_reward'").fetchone()[0] == 3
    with store._transact() as conn:
        conn.execute("DELETE FROM server_study_sessions WHERE id='s'")
    store.auto_settle_goals(1, rebuild_dates=['2026-08-04'])
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE user_id=1 AND source_type='goal' AND status='active'").fetchone()[0] == 0
        assert conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='goal_penalty'").fetchone()[0] == -2


def test_goal_item_binding_rejects_other_account(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'one','x','2026-08-04 00:00:00'),(2,'two','x','2026-08-04 00:00:00')")
        conn.execute("""INSERT INTO server_goals(id,user_id,title,metric,target_value,period,operator,reward_coins,is_active,created_at,updated_at)
            VALUES('other',2,'目标','duration',1,'daily','>=',3,1,'2026-08-04 00:00:00','2026-08-04 00:00:00')""")
        conn.execute("""INSERT INTO server_rewards(id,user_id,title,price,redemption_mode,fulfillment_mode,is_active,created_at,updated_at)
            VALUES('r',1,'物品',0,'task','fragment',1,'2026-08-04 00:00:00','2026-08-04 00:00:00')""")
    with pytest.raises(ValueError, match='不属于当前账号'):
        store.bind_reward_source(1, 'r', 'goal', 'other')
