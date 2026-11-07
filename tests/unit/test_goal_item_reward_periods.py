import pytest

from server.store import ServerSleepStore


@pytest.mark.parametrize("period,start,session,now,weekdays", [
    ("weekly", "2026-10-19", "2026-10-19", "2026-10-27", "[]"),
    ("monthly", "2026-09-01", "2026-09-01", "2026-10-02", "[]"),
    ("custom_weekdays", "2026-10-26", "2026-10-26", "2026-10-28", "[1]"),
])
def test_period_goal_item_and_coins_settle_once(tmp_path, monkeypatch, period, start, session, now, weekdays):
    monkeypatch.setattr("server.store.now_str", lambda: now + " 09:00:00")
    store = ServerSleepStore(str(tmp_path / "goal-period.db"))
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES(1,'owner','x',?)", (start,))
        conn.execute("INSERT INTO server_system_config(user_id,key,value,value_type,updated_at) VALUES(1,'statistics_start_date',?,'string',?)", (start, start))
        conn.execute("""INSERT INTO server_goals(id,user_id,title,metric,target_value,period,operator,reward_coins,penalty_coins,weekdays,is_active,created_at,updated_at)
            VALUES('g',1,'目标','duration',1,?,'>=',3,2,?,1,?,?)""", (period, weekdays, start, start))
        conn.execute("""INSERT INTO server_study_sessions(id,user_id,start_time,end_time,net_duration_minutes,date,updated_at)
            VALUES('s',1,?,?,1,?,?)""", (session + " 08:00:00", session + " 08:01:00", session, session))
        conn.execute("""INSERT INTO server_rewards(id,user_id,title,price,redemption_mode,fulfillment_mode,fragment_target_count,is_active,created_at,updated_at)
            VALUES('r',1,'物品',0,'task','fragment',1,1,?,?)""", (start, start))
        conn.execute("""INSERT INTO server_reward_source_bindings(id,user_id,reward_id,source_type,source_id,created_at,updated_at)
            VALUES('b',1,'r','goal','g',?,?)""", (start, start))
    assert store.auto_settle_goals(1)
    assert store.auto_settle_goals(1) == []
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE user_id=1 AND source_type='goal'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy'").fetchone()[0] == 1
        assert conn.execute("SELECT SUM(amount) FROM server_reward_ledger WHERE user_id=1 AND source_type='goal_reward'").fetchone()[0] == 3
    with store._transact() as conn:
        conn.execute("DELETE FROM server_study_sessions WHERE id='s'")
    store.auto_settle_goals(1, rebuild_dates=[session])
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_fragments WHERE user_id=1 AND source_type='goal' AND status='active'").fetchone()[0] == 0
