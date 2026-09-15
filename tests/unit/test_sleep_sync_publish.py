# -*- coding: utf-8 -*-
import pytest

from server.domain.sleep_automation_service import SleepAutomationService
from server.store import ServerSleepStore


def _metrics():
    return {"sleep_start": "23:00", "sleep_end": "07:00", "sleep_score": 90,
            "deep_sleep_min": 95, "sleep_cycles": 5.5, "awake_min": 10,
            "awake_count": 1, "fall_asleep_min": 20, "wake_up_min": 10}


def test_sleep_facts_publish_change_log_atomically(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_sync_publish", "password123")
    service = SleepAutomationService(store._transact, store._record_server_change)

    service.create_timer_switch(1, "2026-08-28")
    store.sleep_reward_service.settle(1, "2026-08-28", _metrics())

    with store._connect() as conn:
        tables = {row[0] for row in conn.execute("SELECT table_name FROM server_change_log")}
    assert {"server_sleep_automation_commands", "server_sleep_notifications",
            "server_sleep_score_settlements"} <= tables


def test_timer_publish_rolls_back_facts_when_change_log_fails(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_sync_rollback", "password123")

    def fail_on_notification(conn, user_id, table, record_id, operation, fields):
        store._record_server_change(conn, user_id, table, record_id, operation, fields)
        if table == "server_sleep_notifications":
            raise RuntimeError("change log unavailable")

    service = SleepAutomationService(store._transact, fail_on_notification)
    with pytest.raises(RuntimeError, match="change log unavailable"):
        service.create_timer_switch(1, "2026-08-28")

    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_automation_commands").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_notifications").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_change_log").fetchone()[0] == 0
