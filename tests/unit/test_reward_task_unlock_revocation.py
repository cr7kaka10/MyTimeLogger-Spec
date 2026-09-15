# -*- coding: utf-8 -*-
import pytest

from server.store import ServerSleepStore


def _store(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    now = "2026-08-01 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u1', 'x', ?)", (now,))
        conn.execute("INSERT INTO server_rewards (id, user_id, title, price, unlock_source_type, unlock_source_id, created_at, updated_at) VALUES ('habit-reward', 1, '习惯奖品', 0, 'habit', 'habit-1', ?, ?)", (now, now))
    return store


def test_task_unlock_revocation_removes_only_matching_event_and_rebuilds_wallet(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    first = service.completion_event_key("habit", "habit-1", "2026-08-01")
    second = service.completion_event_key("habit", "habit-1", "2026-08-02")
    with store._transact() as conn:
        service.grant_task_unlocks_in_txn(conn, 1, "habit", "habit-1", first, "习惯", "2026-08-01")
        service.grant_task_unlocks_in_txn(conn, 1, "habit", "habit-1", second, "习惯", "2026-08-02")
        removed = service.remove_task_unlocks_in_txn(conn, 1, "habit", "habit-1", first)
    assert len(removed) == 1
    with store._connect() as conn:
        remaining = conn.execute("SELECT source_id FROM server_reward_ledger WHERE user_id=1 AND source_type='reward_buy'").fetchall()
        wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()
    assert len(remaining) == 1 and second in remaining[0]["source_id"]
    assert wallet["balance"] == 0


def test_used_task_unlock_blocks_source_cancellation(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    event_key = service.completion_event_key("habit", "habit-1", "2026-08-01")
    with store._transact() as conn:
        purchase_id = service.grant_task_unlocks_in_txn(conn, 1, "habit", "habit-1", event_key, "习惯", "2026-08-01")[0]
        store.reward_wallet_service.append_ledger_in_txn(conn, 1, 0, "backpack_use", purchase_id, "使用", "2026-08-01")
        with pytest.raises(ValueError, match="已使用"):
            service.remove_task_unlocks_in_txn(conn, 1, "habit", "habit-1", event_key)
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_reward_ledger WHERE id=?", (purchase_id,)).fetchone() is not None


def test_habit_unlock_revocation_reverses_used_unlock_without_touching_unrelated_purchase(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    event_key = service.completion_event_key("habit", "habit-1", "2026-08-01")
    with store._transact() as conn:
        purchase_id = service.grant_task_unlocks_in_txn(conn, 1, "habit", "habit-1", event_key, "习惯", "2026-08-01")[0]
        used_id = store.reward_wallet_service.append_ledger_in_txn(conn, 1, 0, "backpack_use", purchase_id, "使用自动商品", "2026-08-01")
        other_purchase_id = store.reward_wallet_service.append_ledger_in_txn(conn, 1, 0, "reward_buy", "manual-purchase", "独立购买", "2026-08-01")
        other_used_id = store.reward_wallet_service.append_ledger_in_txn(conn, 1, 0, "backpack_use", other_purchase_id, "使用独立商品", "2026-08-01")
        removed = service.remove_task_unlocks_in_txn(conn, 1, "habit", "habit-1", event_key, reverse_used=True)
    assert [row["id"] for row in removed] == [purchase_id]
    with store._connect() as conn:
        ids = {row["id"] for row in conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=1").fetchall()}
    assert purchase_id not in ids and used_id not in ids
    assert {other_purchase_id, other_used_id}.issubset(ids)


def test_habit_unlock_reverse_rolls_back_use_and_purchase_together(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    event_key = service.completion_event_key("habit", "habit-1", "2026-08-01")
    with store._transact() as conn:
        purchase_id = service.grant_task_unlocks_in_txn(conn, 1, "habit", "habit-1", event_key, "习惯", "2026-08-01")[0]
        used_id = store.reward_wallet_service.append_ledger_in_txn(conn, 1, 0, "backpack_use", purchase_id, "使用", "2026-08-01")
    with pytest.raises(RuntimeError, match="force rollback"):
        with store._transact() as conn:
            service.remove_task_unlocks_in_txn(conn, 1, "habit", "habit-1", event_key, reverse_used=True)
            raise RuntimeError("force rollback")
    with store._connect() as conn:
        ids = {row["id"] for row in conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=1").fetchall()}
    assert {purchase_id, used_id}.issubset(ids)


def test_checklist_source_revocation_removes_all_unconsumed_unlocks(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    with store._transact() as conn:
        conn.execute("INSERT INTO server_rewards (id, user_id, title, price, unlock_source_type, unlock_source_id, created_at, updated_at) VALUES ('task-reward', 1, 'test', 0, 'checklist_task', 'task-1', '2026-08-01 12:00:00', '2026-08-01 12:00:00')")
        first = service.completion_event_key('checklist_task', 'task-1', '2026-08-01', 'first')
        second = service.completion_event_key('checklist_task', 'task-1', '2026-08-02', 'second')
        service.grant_task_unlocks_in_txn(conn, 1, 'checklist_task', 'task-1', first, 'test', '2026-08-01')
        service.grant_task_unlocks_in_txn(conn, 1, 'checklist_task', 'task-1', second, 'test', '2026-08-02')
        removed = service.remove_task_unlocks_for_source_in_txn(conn, 1, 'checklist_task', 'task-1')
    assert len(removed) == 2


def test_used_checklist_unlock_blocks_source_revocation(tmp_db_path):
    store = _store(tmp_db_path)
    service = store.reward_settlement_service
    with store._transact() as conn:
        conn.execute("INSERT INTO server_rewards (id, user_id, title, price, unlock_source_type, unlock_source_id, created_at, updated_at) VALUES ('task-reward', 1, 'test', 0, 'checklist_task', 'task-1', '2026-08-01 12:00:00', '2026-08-01 12:00:00')")
        event_key = service.completion_event_key('checklist_task', 'task-1', '2026-08-01', 'completed')
        purchase_id = service.grant_task_unlocks_in_txn(conn, 1, 'checklist_task', 'task-1', event_key, 'test', '2026-08-01')[0]
        store.reward_wallet_service.append_ledger_in_txn(conn, 1, 0, 'backpack_use', purchase_id, '使用', '2026-08-01')
        with pytest.raises(ValueError, match='已使用'):
            service.remove_task_unlocks_for_source_in_txn(conn, 1, 'checklist_task', 'task-1')
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_reward_ledger WHERE id=?", (purchase_id,)).fetchone() is not None
