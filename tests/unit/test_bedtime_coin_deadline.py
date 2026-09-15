# -*- coding: utf-8 -*-
from datetime import datetime, timezone

import server.server as server_module
from server.domain.sleep_automation_service import BEIJING, STEP_BEDTIME_DEADLINE, due_step
from server.store import ServerSleepStore


def test_bedtime_deadline_uses_beijing_noon():
    assert due_step(datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc)) == STEP_BEDTIME_DEADLINE


def test_bedtime_deadline_does_not_create_a_missing_sleep_penalty(monkeypatch, tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("bedtime_deadline", "password123")
    service = server_module.SleepAutomationService(store._transact, store._record_server_change)
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "sleep_automation_service", service)
    at_deadline = datetime(2026, 9, 9, 12, 0, tzinfo=BEIJING)
    # 截止结算是账本维护，不改变该函数既有的“新建睡眠任务数”返回语义。
    assert server_module._run_scheduled_sleep_automation(at_deadline) == 0
    assert server_module._run_scheduled_sleep_automation(at_deadline) == 0
    with store._connect() as conn:
        ledgers = conn.execute("SELECT amount FROM server_reward_ledger WHERE source_type='sleep_bedtime_adjustment'").fetchall()
        run = conn.execute("SELECT status FROM server_sleep_automation_runs WHERE step='bedtime_coin_deadline'").fetchone()
    assert ledgers == []
    assert run["status"] == "done"


def test_startup_retires_legacy_noon_penalties_without_blocking_startup(monkeypatch, tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(store.sleep_reward_service, "rollback_bedtime_coins", lambda: {
        "deleted_ledgers": 1, "affected_users": 1,
    })
    assert server_module._retire_legacy_noon_bedtime_penalties_on_startup() == {
        "deleted_ledgers": 1, "affected_users": 1,
    }
