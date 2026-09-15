import hashlib
import sqlite3
from types import SimpleNamespace

import pytest

from server.store import ServerSleepStore
from server.domain.reward_rebuild_diagnostics import failure_report
from server.ticktick_reset import preview_ticktick_reset
from server.ticktick_reset_execute import TickTickResetError, reset_ticktick_data


def test_same_snapshot_can_reset_twice_and_conflict_rolls_back(tmp_path, monkeypatch):
    store = ServerSleepStore(str(tmp_path / "reset.db")); user_id = 1; now = "2026-08-25 13:00:00"
    conn = store._connect(); conn.execute("INSERT INTO users (id,username,password_hash,created_at) VALUES (1,'u','p',?)", (now,)); conn.commit(); conn.close()

    def seed():
        conn = store._connect()
        conn.execute("INSERT OR REPLACE INTO server_tasks (id,user_id,title,raw_json,updated_at) VALUES ('task',1,'任务','{}',?)", (now,))
        conn.execute("INSERT OR REPLACE INTO server_habits (id,user_id,name,raw_json,created_at,updated_at) VALUES ('habit',1,'习惯','{}',?,?)", (now, now))
        conn.execute("INSERT OR REPLACE INTO server_habit_checkins (id,user_id,habit_id,updated_at) VALUES ('checkin',1,'habit',?)", (now,))
        conn.execute("INSERT OR REPLACE INTO server_reward_ledger (id,user_id,amount,source_type,source_id,description,target_date,created_at,updated_at) VALUES ('ledger',1,1,'task_complete','task','奖励','2026-08-25',?,?)", (now, now))
        conn.execute("INSERT OR REPLACE INTO server_user_wallets (user_id,balance,updated_at) VALUES (1,1,?)", (now,))
        conn.execute("INSERT OR REPLACE INTO server_sync_state (user_id,system,direction,last_status,created_at,updated_at) VALUES (1,'ticktick','ticktick_to_server','success',?,?)", (now, now)); conn.commit(); conn.close()

    seed(); first = preview_ticktick_reset(store.db_path, user_id, "2026-08-01")
    reset_ticktick_data(store.db_path, user_id, "2026-08-01", first["summary_hash"], "RESET TICKTICK USER 1", "trace-a", True)
    seed(); assert preview_ticktick_reset(store.db_path, user_id, "2026-08-01")["summary_hash"] == first["summary_hash"]
    reset_ticktick_data(store.db_path, user_id, "2026-08-01", first["summary_hash"], "RESET TICKTICK USER 1", "trace-b", True)
    conn = store._connect(); ids = [row[0] for row in conn.execute("SELECT change_id FROM server_change_log WHERE user_id=1 AND change_id LIKE 'ticktick-reset:%'")]; conn.close()
    assert len(ids) == len(set(ids)) and len(ids) == 12

    seed(); trace = "trace-conflict"; token = hashlib.sha256(trace.encode()).hexdigest()[:12]
    conn = store._connect(); conn.execute("INSERT INTO server_change_log (user_id,server_version,change_id,table_name,record_id,entity_type,entity_id,operation,changed_fields_json,status,changed_at,created_at) VALUES (1,999,?,'server_reward_ledger','ledger','reward_ledger','ledger','delete','{}','applied',?,?)", (f"ticktick-reset:{token}:000000000000:server_reward_ledger:ledger", now, now)); before = [conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=1").fetchone()[0] for table in ("server_tasks", "server_habits", "server_habit_checkins", "server_reward_ledger", "server_sync_state", "server_user_wallets", "server_system_config", "ticktick_reset_audit", "server_change_log")]; conn.commit(); conn.close()
    monkeypatch.setattr("server.ticktick_reset_execute.uuid.uuid4", lambda: SimpleNamespace(hex="0" * 32))
    with pytest.raises(TickTickResetError, match="ticktick_reset_tombstone_conflict") as raised:
        reset_ticktick_data(store.db_path, user_id, "2026-08-01", first["summary_hash"], "RESET TICKTICK USER 1", trace, True)
    conn = store._connect(); after = [conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=1").fetchone()[0] for table in ("server_tasks", "server_habits", "server_habit_checkins", "server_reward_ledger", "server_sync_state", "server_user_wallets", "server_system_config", "ticktick_reset_audit", "server_change_log")]; conn.close()
    report = failure_report(raised.value, trace_id="trace", job_id="job", failed_stage="ticktick_reset")
    assert before == after and report["code"] == "ticktick_reset_tombstone_conflict" and report["causes"][-1]["chain"] == "ticktick_reset"
