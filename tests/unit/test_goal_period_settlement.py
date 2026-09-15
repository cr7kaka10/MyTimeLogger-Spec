from server.store import ServerSleepStore


def _goal(conn, goal_id, period, created_at):
    conn.execute(
        """INSERT INTO server_goals
           (id,user_id,title,metric,target_value,period,operator,reward_coins,penalty_coins,is_active,created_at,updated_at)
           VALUES (?,1,?,'duration',1,?,'>=',3,2,1,?,?)""",
        (goal_id, goal_id, period, created_at, created_at),
    )


def test_daily_backfill_settles_each_completed_date_once(tmp_db_path, monkeypatch):
    monkeypatch.setattr('server.store.now_str', lambda: '2026-08-04 09:00:00')
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-08-01 00:00:00')")
        _goal(conn, 'daily', 'daily', '2026-08-01 00:00:00')

    first = store.auto_settle_goals(1)
    second = store.auto_settle_goals(1)
    with store._connect() as conn:
        claims = [row['ext_id'] for row in conn.execute("SELECT ext_id FROM server_external_rewards ORDER BY ext_id")]
        targets = [row['target_date'] for row in conn.execute("SELECT target_date FROM server_reward_ledger ORDER BY target_date")]

    assert [row['claim_id'] for row in first] == [
        'goal_daily_20260801', 'goal_daily_20260802', 'goal_daily_20260803',
    ]
    assert second == []
    assert claims == [
        'goal_daily_20260801', 'goal_daily_20260802', 'goal_daily_20260803',
    ]
    assert targets == ['2026-08-01', '2026-08-02', '2026-08-03']


def test_next_day_daily_settlement_keeps_the_completed_target_date(tmp_db_path, monkeypatch):
    monkeypatch.setattr('server.store.now_str', lambda: '2026-08-05 00:00:01')
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-08-04 00:00:00')")
        _goal(conn, 'daily', 'daily', '2026-08-04 00:00:00')

    store.auto_settle_goals(1)
    assert store.auto_settle_goals(1) == []
    with store._connect() as conn:
        row = conn.execute(
            "SELECT target_date FROM server_reward_ledger WHERE user_id=1 AND source_id='goal_daily_20260804'"
        ).fetchone()

    assert row['target_date'] == '2026-08-04'


def test_weekly_and_monthly_backfill_only_complete_windows(tmp_db_path, monkeypatch):
    monkeypatch.setattr('server.store.now_str', lambda: '2026-09-02 00:00:01')
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-07-01 00:00:00')")
        _goal(conn, 'weekly', 'weekly', '2026-07-27 00:00:00')
        _goal(conn, 'monthly', 'monthly', '2026-07-01 00:00:00')

    store.auto_settle_goals(1)
    assert store.auto_settle_goals(1) == []
    with store._connect() as conn:
        claims = {row['ext_id'] for row in conn.execute("SELECT ext_id FROM server_external_rewards")}

    assert 'goal_weekly_20260727_20260802' in claims
    assert 'goal_weekly_20260824_20260830' in claims
    assert 'goal_weekly_20260831_20260906' not in claims
    assert 'goal_monthly_20260701_20260731' in claims
    assert 'goal_monthly_20260801_20260831' in claims
    assert 'goal_monthly_20260901_20260930' not in claims


def test_weekly_and_monthly_settlement_use_completed_period_end_date(tmp_db_path, monkeypatch):
    monkeypatch.setattr('server.store.now_str', lambda: '2026-09-01 00:00:01')
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-08-01 00:00:00')")
        _goal(conn, 'weekly', 'weekly', '2026-08-24 00:00:00')
        _goal(conn, 'monthly', 'monthly', '2026-08-01 00:00:00')

    store.auto_settle_goals(1)
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT source_id,target_date FROM server_reward_ledger WHERE user_id=1 ORDER BY source_id"
        ).fetchall()
        details = conn.execute(
            "SELECT ext_id,item_name FROM server_external_rewards WHERE user_id=1 ORDER BY ext_id"
        ).fetchall()

    assert [tuple(row) for row in rows] == [
        ('goal_monthly_20260801_20260831', '2026-08-31'),
        ('goal_weekly_20260824_20260830', '2026-08-30'),
    ]
    assert [tuple(row) for row in details] == [
        ('goal_monthly_20260801_20260831', '目标未达标[2026-08-31]: monthly (0m / >=1m)'),
        ('goal_weekly_20260824_20260830', '目标未达标[2026-08-30]: weekly (0m / >=1m)'),
    ]


def test_historical_manual_session_rebuilds_goal_fact_and_wallet(tmp_db_path, monkeypatch):
    monkeypatch.setattr('server.store.now_str', lambda: '2026-08-02 09:00:00')
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-08-01 00:00:00')")
        conn.execute(
            """INSERT INTO server_goals
               (id,user_id,title,metric,target_value,period,operator,reward_coins,penalty_coins,is_active,created_at,updated_at)
               VALUES ('daily',1,'daily','duration',60,'daily','>=',3,2,1,'2026-08-01 00:00:00','2026-08-01 00:00:00')"""
        )
    store.auto_settle_goals(1)
    with store._transact() as conn:
        conn.execute(
            """INSERT INTO server_study_sessions
               (id,user_id,start_time,end_time,net_duration_minutes,date,updated_at)
               VALUES ('manual',1,'2026-08-01 08:00:00','2026-08-01 09:00:00',60,'2026-08-01','2026-08-02 09:00:00')"""
        )
    store.recalculate_goal_periods(1, ['2026-08-01'])
    with store._connect() as conn:
        ledgers = conn.execute("SELECT amount,source_type,source_id FROM server_reward_ledger WHERE user_id=1").fetchall()
        wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()['balance']
        external = conn.execute("SELECT COUNT(*) FROM server_external_rewards WHERE user_id=1 AND ext_id='goal_daily_20260801'").fetchone()[0]

    assert [tuple(row) for row in ledgers] == [(3.0, 'goal_reward', 'goal_daily_20260801')]
    assert wallet == 3.0
    assert external == 1


def test_goal_period_fact_diagnostic_is_read_only_and_uses_period_end_date(tmp_db_path, monkeypatch):
    monkeypatch.setattr('server.store.now_str', lambda: '2026-08-05 00:00:01')
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users VALUES (1,'u','x','2026-08-04 00:00:00')")
        _goal(conn, 'daily', 'daily', '2026-08-04 00:00:00')
    store.auto_settle_goals(1)

    facts = store.inspect_goal_period_facts(1, ['2026-08-04', '2026-08-03'])

    assert facts == [
        {'target_date': '2026-08-03', 'claim_ids': [], 'ledger_ids': [], 'ledger_count': 0, 'ledger_amount': 0, 'has_server_fact': False},
        {'target_date': '2026-08-04', 'claim_ids': ['goal_daily_20260804'], 'ledger_ids': ['ledger_1_goal_penalty_goal_daily_20260804_2026-08-04'], 'ledger_count': 1, 'ledger_amount': -2.0, 'has_server_fact': True},
    ]
