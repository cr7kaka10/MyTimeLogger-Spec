# -*- coding: utf-8 -*-
import asyncio
import sqlite3
from datetime import datetime
from types import SimpleNamespace

from server.db_wrapper import ServerDBWrapper
import server.sync_hub as sync_hub_module
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


def _db(tmp_path):
    db_path = tmp_path / "provider_versioned_sync.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-06-13 00:00:00')"
    )
    conn.commit()
    conn.close()
    db = ServerDBWrapper()
    db.log_path = str(db_path)
    return db_path, db


def test_ticktick_unchanged_task_does_not_create_new_version(tmp_path):
    db_path, db = _db(tmp_path)
    task = {
        "id": "tt-1",
        "title": "安排人工智能训练师学习计划",
        "priority": 0,
        "status": 0,
        "due_date": "2026-06-13 00:00:00",
        "tags": ["输出"],
    }

    assert db.upsert_task(1, task) is True
    assert db.upsert_task(1, task) is False

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0]
    conn.close()

    assert count == 1


def test_ticktick_same_semantics_with_reordered_raw_json_does_not_create_new_version(tmp_path):
    db_path, db = _db(tmp_path)
    first = {
        "id": "tt-canonical",
        "title": "字段顺序不应产生增量",
        "priority": 0,
        "status": 0,
        "tags": ["输出"],
        "raw": {"alpha": 1, "beta": 2},
    }
    same_semantics = {
        "raw": {"beta": 2, "alpha": 1},
        "tags": ["输出"],
        "status": 0,
        "priority": 0,
        "title": "字段顺序不应产生增量",
        "id": "tt-canonical",
    }

    assert db.upsert_task(1, first) is True
    assert db.upsert_task(1, same_semantics) is False

    conn = sqlite3.connect(db_path)
    versions = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0]
    updated_at = conn.execute("SELECT updated_at FROM server_tasks WHERE user_id=1 AND id='tt-canonical'").fetchone()[0]
    conn.close()
    assert versions == 1
    assert updated_at


def test_ticktick_transport_metadata_does_not_create_new_version(tmp_path):
    db_path, db = _db(tmp_path)
    task = {
        "id": "tt-transport",
        "title": "传输标记不属于业务变更",
        "priority": 0,
        "status": 0,
        "tags": ["输出"],
        "request_id": "first-pull",
        "pulled_at": "2026-09-12 10:00:00",
    }

    assert db.upsert_task(1, task) is True
    assert db.upsert_task(1, {
        **task,
        "request_id": "second-pull",
        "pulled_at": "2026-09-12 10:00:01",
        "transport_diagnostics": {"elapsed_ms": 3},
    }) is False

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0] == 1
    conn.close()


def test_ticktick_due_date_change_creates_versioned_delta(tmp_path):
    _, db = _db(tmp_path)
    hub = SyncHub(db)

    assert db.upsert_task(1, {
        "id": "tt-delay",
        "title": "6.12 延期任务",
        "priority": 0,
        "status": 0,
        "dueDate": "2026-06-12T00:00:00+0800",
        "tags": ["输出"],
    }) is True

    assert db.upsert_task(1, {
        "id": "tt-delay",
        "title": "6.12 延期任务",
        "priority": 0,
        "status": 0,
        "dueDate": "2026-06-14T00:00:00+0800",
        "tags": ["输出"],
    }) is True

    result = asyncio.run(hub.handle_pull_by_version(1, user_id=1, limit=20))

    assert result["to_version"] == 2
    assert result["changes"][0]["entity_id"] == "tt-delay"
    assert '"due_date": "2026-06-14 00:00:00"' in result["changes"][0]["changed_fields_json"]
    assert result["tables"]["tasks"][0]["due_date"] == "2026-06-14 00:00:00"


def test_ticktick_completed_task_appears_in_versioned_pull(tmp_path):
    _, db = _db(tmp_path)
    hub = SyncHub(db)
    db.upsert_task(1, {
        "id": "tt-done",
        "title": "带孩打针",
        "priority": 0,
        "status": 2,
        "due_date": "2026-06-13 00:00:00",
        "tags": ["家庭"],
    })

    result = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=20))

    assert result["to_version"] == 1
    assert result["changes"][0]["entity_type"] == "task"
    assert result["changes"][0]["entity_id"] == "tt-done"
    assert '"status": 2' in result["changes"][0]["changed_fields_json"]


def test_force_pull_ticktick_records_diagnostics_when_not_configured(tmp_path):
    db_path, db = _db(tmp_path)
    hub = SyncHub(db)

    diagnostics = asyncio.run(hub.force_pull_ticktick(1))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT last_status, last_error, diagnostics_json FROM server_sync_state WHERE user_id=1 AND system='ticktick' AND direction='ticktick_to_server'"
    ).fetchone()
    conn.close()

    assert diagnostics["ok"] is False
    assert row["last_status"] == "error"
    assert row["last_error"] == "ticktick_not_configured"
    assert "ticktick_not_configured" in row["diagnostics_json"]


def test_force_pull_ticktick_records_non_empty_task_error(monkeypatch, tmp_path):
    _, db = _db(tmp_path)
    hub = SyncHub(db)

    class FakeTickTickClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def raise_empty_task_error(client, user_id):
        raise TimeoutError()

    async def pull_habits_ok(client, user_id):
        return {"habits": 0, "checkins": 0}

    monkeypatch.setattr(sync_hub_module, "_get_ticktick_client_class", lambda: FakeTickTickClient)
    monkeypatch.setattr(
        hub,
        "_get_ticktick_settings",
        lambda user_id: SimpleNamespace(
            enabled=True,
            access_token="token",
            host="dida365.com",
            verify_tls=False,
            timeout_seconds=1,
        ),
    )
    monkeypatch.setattr(hub, "_pull_tasks", raise_empty_task_error)
    monkeypatch.setattr(hub, "_pull_habits", pull_habits_ok)

    diagnostics = asyncio.run(hub.force_pull_ticktick(1))

    assert diagnostics["ok"] is False
    assert diagnostics["errors"]
    assert diagnostics["errors"][0].startswith("tasks:TimeoutError")
    assert diagnostics["errors"][0] != "tasks:"


class ChangedHabitsClient:
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def get_habits(self):
        return [{"id": f"habit-{index}", "name": f"习惯{index}", "status": 0, "sortOrder": index,
                 "iconRes": "txt_✅", "sectionId": "daily", "repeatRule": "RRULE:FREQ=DAILY", "etag": f"etag-{index}"}
                for index in range(1, 5)]
    async def get_habit_sections(self): return [{"id": "daily", "name": "日常"}]
    async def get_habit_checkins(self, habit_ids, *_):
        stamp = datetime.now(sync_hub_module.CST).strftime("%Y%m%d")
        return [{"habitId": habit_id, "checkins": [{"stamp": stamp, "status": 2, "opTime": f"op-{habit_id}"}]} for habit_id in habit_ids]


def test_changed_habits_do_not_block_four_ticktick_checkins(monkeypatch, tmp_path):
    db_path, db = _db(tmp_path)
    hub = SyncHub(db)
    async def pull_tasks_ok(*_): return {"task_changes": 0, "complete": True}
    monkeypatch.setattr(sync_hub_module, "_get_ticktick_client_class", lambda: ChangedHabitsClient)
    monkeypatch.setattr(hub, "_pull_tasks", pull_tasks_ok)
    monkeypatch.setattr(hub, "_get_ticktick_settings", lambda _: SimpleNamespace(enabled=True, access_token="token", host="dida365.com", verify_tls=False, timeout_seconds=1))

    diagnostics = asyncio.run(hub.force_pull_ticktick(1))
    delta = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=50))
    conn = sqlite3.connect(db_path)
    habits = conn.execute("SELECT COUNT(*) FROM server_habits WHERE user_id=1").fetchone()[0]
    checkins = conn.execute("SELECT COUNT(*) FROM server_habit_checkins WHERE user_id=1 AND status=2").fetchone()[0]
    watermark = conn.execute("SELECT last_status FROM server_sync_state WHERE user_id=1 AND system='ticktick' AND direction='ticktick_to_server'").fetchone()[0]
    conn.close()

    assert diagnostics["ok"] is True and diagnostics["habits"]["checkin_changes"] == 4
    assert habits == checkins == 4 and watermark == "success"
    assert len(delta["tables"]["habits"]) == len(delta["tables"]["habit_checkins"]) == 4


def test_provider_habit_cancellation_reverses_used_unlocks(monkeypatch, tmp_path):
    _, db = _db(tmp_path)
    hub = SyncHub(db)
    captured = {}
    monkeypatch.setattr(hub._reward_settlement, "remove_state_ledgers_in_txn", lambda *args: [])
    monkeypatch.setattr(
        hub._reward_settlement,
        "remove_task_unlocks_in_txn",
        lambda *args, **kwargs: captured.setdefault("reverse_used", kwargs.get("reverse_used")) and [],
    )
    monkeypatch.setattr(hub, "_publish_reward_changes_in_txn", lambda *args: None)

    conn = sqlite3.connect(db.log_path)
    try:
        hub._replace_habit_reward_in_txn(conn, 1, "habit-1", "fixture", "easy", "2026-08-04", 0)
    finally:
        conn.close()

    assert captured["reverse_used"] is True


class EmptyTaskSnapshotClient:
    def __init__(self, fail_project=False, fail_completed=False):
        self.fail_project = fail_project
        self.fail_completed = fail_completed
        self.single_reads = 0

    async def get_projects(self):
        return [{"id": "p1", "name": "收件箱"}]

    async def get_project_data(self, project_id):
        if self.fail_project:
            raise TimeoutError("project")
        return {"tasks": []}

    async def get_completed_tasks(self, start_time):
        if self.fail_completed:
            raise TimeoutError("completed")
        return []

    async def get_task(self, project_id, task_id):
        self.single_reads += 1
        raise AssertionError("缺失判定禁止逐任务读取")


def test_ticktick_complete_snapshot_deletes_task_and_rolls_back_reward(tmp_path):
    db_path, db = _db(tmp_path)
    hub = SyncHub(db)
    db.upsert_task(1, {"id": "gone", "title": "已删除", "status": 2, "priority": 0, "tags": []})
    hub._reward_task_if_new("gone", "已删除", {"completedTime": "2026-07-18T08:00:00+0800"}, 1)
    before = db.allocate_server_version(1)
    client = EmptyTaskSnapshotClient()

    stats = asyncio.run(hub._pull_tasks(client, 1))
    delta = asyncio.run(hub.handle_pull_by_version(before, 1, limit=20))

    conn = sqlite3.connect(db_path)
    task = conn.execute("SELECT deleted_at FROM server_tasks WHERE user_id=1 AND id='gone'").fetchone()
    ledger_count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_id='gone'").fetchone()[0]
    wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    conn.close()
    assert stats["deleted_tasks"] == 1 and client.single_reads == 0
    assert task[0] and ledger_count == 0 and wallet == 0
    assert delta["tables"]["tasks"][0]["_sync_operation"] == "delete"
    assert delta["tables"]["reward_ledger"][0]["_sync_operation"] == "delete"


def test_ticktick_complete_snapshot_deletes_active_task_without_wallet_change(tmp_path):
    db_path, db = _db(tmp_path)
    hub = SyncHub(db)
    db.upsert_task(1, {"id": "active-gone", "title": "未完成删除", "status": 0, "priority": 0, "tags": []})

    stats = asyncio.run(hub._pull_tasks(EmptyTaskSnapshotClient(), 1))

    conn = sqlite3.connect(db_path)
    deleted_at = conn.execute("SELECT deleted_at FROM server_tasks WHERE id='active-gone'").fetchone()[0]
    ledger_count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1").fetchone()[0]
    conn.close()
    assert stats["deleted_tasks"] == 1 and deleted_at and ledger_count == 0


def test_ticktick_incomplete_snapshot_never_deletes(tmp_path):
    for fail_project, fail_completed, reason in ((True, False, "project_pull_failed"), (False, True, "completed_pull_failed")):
        case_path = tmp_path / reason
        case_path.mkdir()
        db_path, db = _db(case_path)
        hub = SyncHub(db)
        task_id = f"keep-{reason}"
        db.upsert_task(1, {"id": task_id, "title": "保留", "status": 0, "priority": 0, "tags": []})
        stats = asyncio.run(hub._pull_tasks(EmptyTaskSnapshotClient(fail_project, fail_completed), 1))
        conn = sqlite3.connect(db_path)
        deleted_at = conn.execute("SELECT deleted_at FROM server_tasks WHERE id=?", (task_id,)).fetchone()[0]
        conn.close()
        assert deleted_at is None and reason in stats["deletion_skipped_reason"]


def test_ticktick_request_budget_exhaustion_never_deletes(monkeypatch, tmp_path):
    db_path, db = _db(tmp_path)
    hub = SyncHub(db)
    db.upsert_task(1, {"id": "keep-budget", "title": "保留", "status": 0, "priority": 0, "tags": []})
    monkeypatch.setattr(sync_hub_module, "TICKTICK_PULL_REQUEST_BUDGET", 1)

    stats = asyncio.run(hub._pull_tasks(EmptyTaskSnapshotClient(), 1))

    conn = sqlite3.connect(db_path)
    deleted_at = conn.execute("SELECT deleted_at FROM server_tasks WHERE id='keep-budget'").fetchone()[0]
    conn.close()
    assert deleted_at is None
    assert stats["request_budget_exceeded"] is True
    assert "request_budget_exceeded" in stats["deletion_skipped_reason"]
