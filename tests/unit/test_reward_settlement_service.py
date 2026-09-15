# -*- coding: utf-8 -*-
import pytest

from server.store import ServerSleepStore


def _store(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', ?)",
            ("2026-06-12 10:00:00",),
        )
    return store


def test_format_description_removes_ticktick_icon_key(tmp_db_path):
    store = _store(tmp_db_path)

    desc = store.reward_settlement_service.format_description(False, "habit", "habit_yoga慎独")

    assert desc == "× 习惯 慎独"
    assert "habit_yoga" not in desc


def test_settle_is_idempotent_and_rebuilds_wallet(tmp_db_path):
    store = _store(tmp_db_path)

    for _ in range(2):
        store.reward_settlement_service.settle(
            1,
            1.0,
            "habit",
            "慎独",
            "habit_checkin",
            source_id="h1",
            target_date="2026-06-12",
        )

    conn = store._connect()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM server_reward_ledger WHERE user_id=1").fetchone()["c"]
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()["balance"]
    finally:
        conn.close()

    assert count == 1
    assert balance == 1.0


def test_wallet_rebuild_matches_ledger_sum(tmp_db_path):
    store = _store(tmp_db_path)
    store.reward_settlement_service.settle(1, 2.5, "task", "任务A", "task_complete", "t1", "2026-06-12")
    store.reward_settlement_service.settle(1, -1.0, "habit", "慎独", "habit_fail", "h1", "2026-06-12", success=False)

    result = store.rebuild_wallet_snapshot(1)

    assert result["balance"] == 1.5
    assert result["wallet_balance"] == 1.5
    assert result["consistent"] is True


def test_makeup_habit_settlement_uses_discounted_rule_result(tmp_db_path):
    store = _store(tmp_db_path)
    store.set_item_reward(1, "habit", "h1", 2, 1)

    reward = store.reward_rule_service.calculate_habit_success(
        1, "h1", "慎独", "easy", "2026-06-11", "2026-06-12 08:00:00"
    )
    with store._transact() as conn:
        store.reward_settlement_service.settle_habit_success_in_txn(
            conn, 1, "h1", reward.title, reward.amount, "2026-06-11"
        )

    conn = store._connect()
    try:
        row = conn.execute(
            "SELECT amount, description FROM server_reward_ledger WHERE user_id=1 AND source_type='habit_checkin'"
        ).fetchone()
        wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()["balance"]
    finally:
        conn.close()

    assert row["amount"] == reward.amount
    assert row["description"] == "√ 习惯 [补]慎独"
    assert wallet == reward.amount


def test_reconcile_habit_success_updates_stable_ledger_and_wallet_once(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    with store._transact() as conn:
        ledger_id = service.settle_habit_success_in_txn(
            conn, 1, "h1", "[补]慎独", 1, "2026-08-23", "2026-08-23 19:14:00"
        )
        _, first = service.reconcile_habit_success_in_txn(
            conn, 1, "h1", "慎独", 2, "2026-08-23", "2026-08-23 19:14:00"
        )
        _, second = service.reconcile_habit_success_in_txn(
            conn, 1, "h1", "慎独", 2, "2026-08-23", "2026-08-23 19:14:00"
        )
    with store._connect() as conn:
        rows = conn.execute("SELECT id,amount,description FROM server_reward_ledger").fetchall()
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]

    assert [(row[0], row[1], row[2]) for row in rows] == [(ledger_id, 2.0, "√ 习惯 慎独")]
    assert balance == 2.0
    assert (first, second) == ("corrected", "unchanged")


def test_settle_transaction_rolls_back_on_wallet_failure(tmp_db_path, monkeypatch):
    store = _store(tmp_db_path)

    def fail_rebuild(conn, user_id, now_fn):
        raise RuntimeError("wallet failed")

    monkeypatch.setattr(store.reward_wallet_service, "rebuild_wallet_snapshot_in_txn", fail_rebuild)

    with pytest.raises(RuntimeError):
        store.reward_settlement_service.settle(
            1,
            1.0,
            "task",
            "任务A",
            "task_complete",
            source_id="t1",
            target_date="2026-06-12",
        )

    conn = store._connect()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM server_reward_ledger WHERE user_id=1").fetchone()["c"]
        wallet = conn.execute("SELECT COUNT(*) AS c FROM server_user_wallets WHERE user_id=1").fetchone()["c"]
    finally:
        conn.close()

    assert count == 0
    assert wallet == 0


def test_remove_state_ledgers_keeps_only_current_habit_state(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    service.settle(1, 1.0, "habit", "慎独", "habit_checkin", "h1", "2026-06-12")
    service.settle(1, -1.0, "habit", "慎独", "habit_fail", "h1", "2026-06-12", False)

    with store._transact() as conn:
        deleted = service.remove_state_ledgers_in_txn(
            conn, 1, "h1", ("habit_checkin", "habit_fail"), "2026-06-12", "habit_fail"
        )
        store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(
            conn, 1, lambda: "2026-06-12 10:00:00"
        )

    conn = store._connect()
    try:
        rows = conn.execute(
            "SELECT source_type FROM server_reward_ledger WHERE user_id=1 AND source_id='h1'"
        ).fetchall()
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()["balance"]
    finally:
        conn.close()

    assert [row["source_type"] for row in deleted] == ["habit_checkin"]
    assert [row["source_type"] for row in rows] == ["habit_fail"]
    assert balance == -1.0


@pytest.mark.parametrize("source_type,config_type,coin_ledger", [
    ("checklist_task", "task", "task_complete"),
    ("habit", "habit", "habit_checkin"),
    ("learning_task", "learning", "learning_checkin"),
])
def test_source_rewards_settle_coins_and_one_item_idempotently(tmp_db_path, source_type, config_type, coin_ledger):
    store = _store(tmp_db_path)
    source_id, stamp = f"{source_type}-1", "2026-08-15"
    with store._transact() as conn:
        if source_type == "checklist_task":
            conn.execute("INSERT INTO server_tasks(id,user_id,title,status,updated_at) VALUES(?,1,'任务',0,?)", (source_id, f"{stamp} 10:00:00"))
        elif source_type == "habit":
            conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,created_at,updated_at) VALUES(?,1,'习惯',0,?,?)", (source_id, stamp, stamp))
        else:
            conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('o1',1,'目标',0,?,?)", (stamp, stamp))
            conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('k1',1,'o1','结果',1,0,?,?)", (stamp, stamp))
            conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES(?,1,'k1','学习',0,?,?)", (source_id, stamp, stamp))
        conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,?,?,4,0,?)", (config_type, source_id, stamp))
    store.create_reward(1, "唯一物品", price=0, unlock_source_type=source_type, unlock_source_id=source_id)
    rule = getattr(store.reward_rule_service, f"calculate_{'task' if source_type == 'checklist_task' else 'learning' if source_type == 'learning_task' else 'habit'}_success")
    reward = rule(1, source_id, "来源", "easy", stamp) if source_type == "habit" else rule(1, source_id, "来源")
    with store._transact() as conn:
        if source_type == "habit":
            conn.execute("INSERT INTO server_habit_checkins(id,user_id,habit_id,date,checkin_date,status,created_at,updated_at) VALUES('c1',1,?,?,?,2,?,?)", (source_id, stamp, stamp, stamp, stamp))
        else:
            table = "server_tasks" if source_type == "checklist_task" else "server_learning_tasks"
            conn.execute(f"UPDATE {table} SET status=2,updated_at=? WHERE id=?", (f"{stamp} 10:00:00", source_id))
        settle = getattr(store.reward_settlement_service, f"settle_{'task' if source_type == 'checklist_task' else 'learning' if source_type == 'learning_task' else 'habit'}_success_in_txn")
        settle(conn, 1, source_id, "来源", reward.amount, stamp)
        settle(conn, 1, source_id, "来源", reward.amount, stamp)
    store.auto_unlock_rewards(1); store.auto_unlock_rewards(1)
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type=?", (coin_ledger,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy'").fetchone()[0] == 1
        assert conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0] == 4
