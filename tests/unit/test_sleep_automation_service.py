# -*- coding: utf-8 -*-
import json
from datetime import datetime, timedelta, timezone

from server.domain.sleep_automation_service import (
    BEIJING, STEP_FULL_ANALYSIS, STEP_TIMER_SWITCH, SleepAutomationService, due_step,
)
from server.store import ServerSleepStore


def _service(store):
    return SleepAutomationService(store._transact, store._record_server_change, lambda: datetime(2026, 8, 28, 22, 30, tzinfo=BEIJING))


def test_due_step_uses_beijing_boundaries_even_for_utc_input():
    assert due_step(datetime(2026, 8, 28, 14, 30, tzinfo=timezone.utc)) == STEP_TIMER_SWITCH
    assert due_step(datetime(2026, 8, 28, 14, 35, tzinfo=timezone.utc)) == STEP_FULL_ANALYSIS
    assert due_step(datetime(2026, 8, 28, 14, 31, tzinfo=timezone.utc)) is None


def test_step_claim_and_timer_switch_are_idempotent(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_automation", "password123")
    service = _service(store)

    first = service.create_timer_switch(1, "2026-08-28")
    second = service.create_timer_switch(1, "2026-08-28")

    assert first["command"]["scheduled_at"] == "2026-08-28 22:30:00"
    assert first["notification"]["title"] == "睡眠时间到"
    assert second is None
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_automation_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_automation_commands").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_notifications").fetchone()[0] == 1


def test_full_analysis_notifies_only_newly_generated_report(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_automation_full", "password123")
    service = _service(store)
    assert service.claim_full_analysis(1, "2026-08-28")

    service.finish_full_analysis(1, "2026-08-28", "reused")
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_notifications").fetchone()[0] == 0

    service.finish_full_analysis(1, "2026-08-28", "done")
    with store._connect() as conn:
        row = conn.execute("SELECT title,body FROM server_sleep_notifications").fetchone()
        assert tuple(row) == ("完整睡眠报告已生成", "完整睡眠报告已生成")


def test_waiting_full_analysis_retries_with_backoff_and_limit(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_retry", "password123")
    clock = [datetime(2026, 8, 28, 22, 35, tzinfo=BEIJING)]
    service = SleepAutomationService(store._transact, store._record_server_change, lambda: clock[0])
    assert service.claim_full_analysis(1, "2026-08-28")
    for attempt in range(1, 9):
        service.finish_full_analysis(1, "2026-08-28", "waiting_for_records", json.dumps({
            "reason": "insufficient_time_records", "tracked_duration_seconds": 40131,
        }))
        with store._connect() as conn:
            row = conn.execute("SELECT status,detail FROM server_sleep_automation_runs WHERE step='full_analysis'").fetchone()
            assert row["status"] == "waiting_for_records"
            assert json.loads(row["detail"])["attempts"] == attempt
            assert conn.execute("SELECT COUNT(*) FROM server_sleep_notifications").fetchone()[0] == 0
        assert not service.claim_full_analysis(1, "2026-08-28")
        clock[0] += timedelta(minutes=10)
        assert service.claim_full_analysis(1, "2026-08-28") is (attempt < 8)


def test_waiting_full_analysis_can_complete_once_after_records_arrive(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_retry_complete", "password123")
    clock = [datetime(2026, 8, 28, 22, 35, tzinfo=BEIJING)]
    service = SleepAutomationService(store._transact, store._record_server_change, lambda: clock[0])
    assert service.claim_full_analysis(1, "2026-08-28")
    service.finish_full_analysis(1, "2026-08-28", "waiting_for_records", '{"reason":"insufficient_time_records"}')
    clock[0] += timedelta(minutes=10)
    assert service.claim_full_analysis(1, "2026-08-28")
    service.finish_full_analysis(1, "2026-08-28", "done")
    assert not service.claim_full_analysis(1, "2026-08-28")
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_notifications WHERE event_type='analysis_done'").fetchone()[0] == 1
