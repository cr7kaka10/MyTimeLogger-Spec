# -*- coding: utf-8 -*-
import sqlite3

from server.domain.source_reward_service import SourceRewardService
from server.store import ServerSleepStore


def _store(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x','2026-08-15 00:00:00')")
    return store


def _reward(conn, reward_id, source_type, source_id, title="奖励"):
    conn.execute(
        """INSERT INTO server_rewards(id,user_id,title,price,unlock_source_type,unlock_source_id,created_at,updated_at)
           VALUES(?,1,?,0,?,?, '2026-08-15 00:00:00','2026-08-15 00:00:00')""",
        (reward_id, title, source_type, source_id),
    )


def test_summary_keeps_same_id_isolated_by_source_type(tmp_db_path):
    store = _store(tmp_db_path)
    with store._transact() as conn:
        for item_type, coins in (("task", 2), ("habit", 3), ("learning", 4)):
            conn.execute(
                """INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at)
                   VALUES(1,?,?,?,?, '2026-08-15 00:00:00')""",
                (item_type, "same", coins, coins + 1),
            )
        _reward(conn, "r-task", "checklist_task", "same", "任务奖")
        _reward(conn, "r-habit", "habit", "same", "习惯奖")
        _reward(conn, "r-learning", "learning_task", "same", "学习奖")
    service = SourceRewardService(store._connect)
    assert [(service.summary(1, kind, "same")["coins"], service.summary(1, kind, "same")["itemReward"]["id"])
            for kind in ("checklist_task", "habit", "learning_task")] == [(2, "r-task"), (3, "r-habit"), (4, "r-learning")]


def test_summary_empty_and_duplicate_preflight_is_read_only(tmp_db_path):
    store = _store(tmp_db_path)
    service = SourceRewardService(store._connect)
    assert service.summary(1, "checklist_task", "missing")["itemReward"] is None
    assert service.summary(1, "checklist_task", "missing")["coins"] == 0
    with store._transact() as conn:
        conn.execute("DROP INDEX uq_server_rewards_active_source")
        _reward(conn, "r1", "habit", "duplicate")
        _reward(conn, "r2", "habit", "duplicate")
    with store._connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM server_rewards").fetchone()[0]
    conflicts = service.duplicate_bindings()
    with store._connect() as conn:
        after = conn.execute("SELECT COUNT(*) FROM server_rewards").fetchone()[0]
    assert conflicts[0]["binding_count"] == 2
    assert before == after == 2


def test_schema_rejects_second_active_binding(tmp_db_path):
    store = _store(tmp_db_path)
    with store._transact() as conn:
        _reward(conn, "r1", "learning_task", "one")
        try:
            _reward(conn, "r2", "learning_task", "one")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("unique source binding was not enforced")
