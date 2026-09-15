# -*- coding: utf-8 -*-
from datetime import datetime

import server.server as server_module
import pytest
from server.domain.sleep_automation_service import BEIJING
from server.store import ServerSleepStore


def test_worker_creates_one_command_and_sleep_time_event_after_restart(monkeypatch, tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_worker", "password123")
    with store._connect() as conn:
        conn.execute("INSERT INTO server_categories(user_id,name,group_name,sort_order) VALUES(1,'睡觉','生活',1)")
        conn.commit()
    service = server_module.SleepAutomationService(store._transact, store._record_server_change)
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "sleep_automation_service", service)
    at_sleep_time = datetime(2026, 8, 28, 22, 30, tzinfo=BEIJING)

    assert server_module._run_scheduled_sleep_automation(at_sleep_time) == 1
    assert server_module._run_scheduled_sleep_automation(at_sleep_time) == 0
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_automation_commands").fetchone()[0] == 1
        notification = conn.execute("SELECT title FROM server_sleep_notifications").fetchone()
        run = conn.execute("SELECT status FROM server_sleep_automation_runs WHERE step='timer_switch'").fetchone()
    assert notification["title"] == "睡眠时间到"
    assert run["status"] == "done"


def test_full_analysis_skips_when_huawei_data_is_missing(monkeypatch, tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_analysis_skip", "password123")
    service = server_module.SleepAutomationService(store._transact, store._record_server_change)
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "sleep_automation_service", service)

    assert server_module._run_scheduled_sleep_automation(datetime(2026, 8, 28, 22, 35, tzinfo=BEIJING)) == 0
    with store._connect() as conn:
        run = conn.execute("SELECT status FROM server_sleep_automation_runs WHERE step='full_analysis'").fetchone()
        notification = conn.execute("SELECT event_type FROM server_sleep_notifications").fetchone()
    assert run["status"] == "skipped_missing_source"
    assert notification["event_type"] == "sleep_time"


def test_timer_switch_is_server_authoritative_and_catches_up_once(monkeypatch, tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_catchup", "password123")
    with store._connect() as conn:
        conn.execute("INSERT INTO server_categories(user_id,name,group_name,sort_order) VALUES(1,'睡觉','生活',1)")
        conn.commit()
    service = server_module.SleepAutomationService(store._transact, store._record_server_change)
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "sleep_automation_service", service)

    delayed = datetime(2026, 8, 28, 22, 36, tzinfo=BEIJING)
    assert server_module._run_scheduled_sleep_automation(delayed) == 1
    assert server_module._run_scheduled_sleep_automation(delayed) == 0
    current = server_module._live_timer_service().read(1)["state"]
    assert current["active"] and current["category_name"] == "睡觉"


def test_full_analysis_uses_existing_full_path_for_valid_huawei_data(monkeypatch, tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_analysis_full", "password123")
    store.save_huawei_sleep_data(1, "2026-08-28", {
        "sleep_score": 90, "deep_sleep_min": 100, "deep_sleep_ratio": 25,
        "light_sleep_min": 180, "rem_sleep_min": 80, "total_sleep_min": 360,
        "sleep_start": "23:00", "sleep_end": "07:00", "official_advice": "完整华为建议原文。",
    })
    service = server_module.SleepAutomationService(store._transact, store._record_server_change)
    invoked = []

    class ImmediateThread:
        def __init__(self, target, args, daemon): self.target, self.args = target, args
        def start(self): self.target(*self.args)

    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "sleep_automation_service", service)
    monkeypatch.setattr(server_module.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(server_module, "_run_scheduled_full_sleep_analysis", lambda *args: invoked.append(args))

    assert server_module._run_scheduled_sleep_automation(datetime(2026, 8, 28, 22, 35, tzinfo=BEIJING)) == 1
    assert invoked == [("sleep-auto:1:2026-08-28", 1, "2026-08-28", "")]


@pytest.mark.parametrize("sleep_data,report,expected", [
    ({"report_status": 1, "full_report_state": "insufficient_time_records", "tracked_duration_seconds": 40131}, "", "waiting_for_records"),
    ({"report_status": 2, "full_report_state": "generated"}, "", "error"),
    ({"report_status": 2, "full_report_state": "generated"}, "完整报告正文", "done"),
])
def test_scheduled_full_analysis_requires_real_report(monkeypatch, tmp_db_path, sleep_data, report, expected):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_job_status", "password123")
    service = server_module.SleepAutomationService(store._transact, store._record_server_change)
    request_id = "sleep-auto:1:2026-08-28"
    store.create_job(request_id, "", user_id=1, date="2026-08-28")
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "sleep_automation_service", service)
    monkeypatch.setattr(server_module, "_run_analysis", lambda *_args, **_kwargs: store.mark_done(request_id, "2026-08-28", sleep_data, report))
    assert service.claim_full_analysis(1, "2026-08-28")

    server_module._run_scheduled_full_sleep_analysis(request_id, 1, "2026-08-28", "")

    with store._connect() as conn:
        run = conn.execute("SELECT status,detail FROM server_sleep_automation_runs WHERE step='full_analysis'").fetchone()
        notifications = conn.execute("SELECT COUNT(*) FROM server_sleep_notifications WHERE event_type='analysis_done'").fetchone()[0]
    assert run["status"] == expected
    assert notifications == (1 if expected == "done" else 0)
    if expected == "waiting_for_records":
        assert "40131" in run["detail"]
