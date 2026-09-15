# -*- coding: utf-8 -*-
import sqlite3
import pytest

from server.models.server_schema import ensure_server_schema


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "sleep_schema.db")
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id, username, password_hash, created_at) VALUES(1, 'sleep', 'x', '2026-08-28 00:00:00')")
    return conn


def test_sleep_automation_run_is_unique_per_user_day_and_step(tmp_path):
    conn = _conn(tmp_path)
    args = ("run-1", 1, "2026-08-28", "timer_switch", "done", "", "2026-08-28 22:30:00", "2026-08-28 22:30:00")
    conn.execute("INSERT INTO server_sleep_automation_runs VALUES(?,?,?,?,?,?,?,?)", args)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO server_sleep_automation_runs VALUES(?,?,?,?,?,?,?,?)", ("run-2", *args[1:]))


def test_sleep_receipts_are_independent_per_device(tmp_path):
    conn = _conn(tmp_path)
    now = "2026-08-28 22:30:00"
    conn.execute("INSERT INTO server_sleep_command_receipts VALUES('r1',1,'pc','cmd','done',?,?)", (now, now))
    conn.execute("INSERT INTO server_sleep_command_receipts VALUES('r2',1,'android','cmd','done',?,?)", (now, now))
    assert conn.execute("SELECT COUNT(*) FROM server_sleep_command_receipts").fetchone()[0] == 2


def test_sleep_score_settlement_is_unique_per_rule_version(tmp_path):
    conn = _conn(tmp_path)
    args = ("s1", 1, "2026-08-28", "{}", "{}", 100, 80, 0, 80, "done", None, "sleep-score-v1", "2026-08-29 08:00:00", "2026-08-29 08:00:00", "2026-08-29 08:00:00")
    columns = "id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at"
    conn.execute(f"INSERT INTO server_sleep_score_settlements ({columns}) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", args)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO server_sleep_score_settlements ({columns}) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("s2", *args[1:]))


def test_sleep_score_settlement_v2_columns_are_compatible(tmp_path):
    conn = _conn(tmp_path)
    names = {row[1] for row in conn.execute("PRAGMA table_info(server_sleep_score_settlements)")}
    assert {"report_completed_at", "completion_reward_amount", "is_all_complete", "completion_reason"} <= names
