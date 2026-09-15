# -*- coding: utf-8 -*-
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SERVER_DIR = os.path.join(ROOT_DIR, "server")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if SERVER_DIR not in sys.path:
    sys.path.insert(1, SERVER_DIR)

import server.server as server_module
import server.sync_hub as sync_hub_module
from server.server import app
from server.db_wrapper import ServerDBWrapper
from server.domain.reward_config_service import RewardConfigService
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


@pytest.fixture
def client_with_temp_store(tmp_db_path):
    test_store = ServerSleepStore(db_path=tmp_db_path)
    original_store = server_module.store
    server_module.store = test_store
    try:
        yield TestClient(app), test_store
    finally:
        server_module.store = original_store


def _login_headers(client, username="arch_user"):
    client.post("/auth/register", json={"username": username, "password": "password123"})
    resp = client.post("/auth/login", json={"username": username, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


class _SyncDb:
    def __init__(self, log_path):
        self.log_path = log_path

    def _get_category_id(self, user_id, project_name, tags, conn=None):
        return None

    def upsert_task(self, user_id, task):
        with sqlite3.connect(self.log_path, timeout=30.0) as conn:
            tags = task.get("tags") or []
            tags_str = ",".join(tags) if isinstance(tags, list) else str(tags)
            conn.execute(
                """
                INSERT INTO server_tasks (id, user_id, title, priority, status, due_date, tags, raw_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-06-12 10:00:00')
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    priority=excluded.priority,
                    status=excluded.status,
                    due_date=excluded.due_date,
                    tags=excluded.tags,
                    raw_json=excluded.raw_json,
                    updated_at=excluded.updated_at
                """,
                (
                    task.get("id") or task.get("ticktick_id"),
                    user_id,
                    task["title"],
                    task.get("priority", 0),
                    task.get("status", 0),
                    task.get("due_date", ""),
                    tags_str,
                    json.dumps(task, ensure_ascii=False),
                ),
            )


def test_uuid_business_ids_are_not_rejected_by_route_layer(client_with_temp_store):
    client, _ = client_with_temp_store
    headers = _login_headers(client)

    habit = client.post("/api/habits", json={"name": "UUID习惯", "icon": "✅"}, headers=headers).json()
    habit_resp = client.put(f"/api/habits/{habit['habit_id']}", json={"name": "UUID习惯改名"}, headers=headers)

    reward = client.post("/api/rewards", json={"title": "UUID奖励", "price": 1}, headers=headers).json()
    reward_resp = client.put(f"/api/rewards/{reward['reward_id']}", json={"title": "UUID奖励改名"}, headers=headers)

    assert habit_resp.status_code != 422
    assert reward_resp.status_code != 422


def test_sync_push_unknown_table_returns_diagnostic(tmp_path):
    db_path = str(tmp_path / "sync.db")
    store = ServerSleepStore(db_path=db_path)
    store.create_user("sync_user", "password123")
    user_id = store.verify_user("sync_user", "password123")
    hub = SyncHub(_SyncDb(db_path))

    result = asyncio.run(hub.handle_push([
        {
            "change_id": "bad-op",
            "table": "not_allowed",
            "operation": "upsert",
            "payload": {"id": "bad-1", "updated_at": "2026-06-06 10:00:00"}
        }
    ], user_id=user_id))

    assert result["accepted"] == 0
    assert result.get("rejected", [])[0]["table"] == "not_allowed"


def test_sync_field_merge_preserves_omitted_existing_values(tmp_path):
    db_path = str(tmp_path / "merge.db")
    store = ServerSleepStore(db_path=db_path)
    store.create_user("merge_user", "password123")
    user_id = store.verify_user("merge_user", "password123")
    hub = SyncHub(_SyncDb(db_path))

    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_tasks
           (id, user_id, title, status, tags, raw_json, updated_at)
           VALUES ('task-1', ?, '旧标题', 0, 'alpha,beta', '{"keep": true}', '2026-06-01 00:00:00')""",
        (user_id,),
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_push([
        {
            "change_id": "op-merge-1",
            "table": "tasks",
            "operation": "upsert",
            "payload": {"id": "task-1", "title": "新标题", "status": 0, "updated_at": "2026-06-02 00:00:00"}
        }
    ], user_id=user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT title, tags, raw_json FROM server_tasks WHERE id='task-1'").fetchone()
    conn.close()

    assert result["accepted"] == 1
    assert row["title"] == "新标题"
    assert row["tags"] == "alpha,beta"
    assert row["raw_json"] == '{"keep": true}'


def _create_user(store: ServerSleepStore, username: str) -> int:
    store.create_user(username, "password123")
    return store.verify_user(username, "password123")


def test_wallet_snapshot_matches_ledger_after_first_entry(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    user_id = _create_user(store, "wallet_first")

    assert store.add_ledger_entry(user_id, 5.0, "manual", "first", "首次入账")

    check = store.verify_wallet_consistency(user_id)
    assert check["ledger_balance"] == 5.0
    assert check["wallet_balance"] == 5.0
    assert check["consistent"] is True


def test_wallet_transaction_failure_rolls_back_ledger_and_snapshot(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    user_id = _create_user(store, "wallet_rollback")

    def fail_wallet_update(*args, **kwargs):
        raise RuntimeError("inject wallet failure")

    store.reward_wallet_service._update_wallet_in_txn = fail_wallet_update

    with pytest.raises(RuntimeError, match="inject wallet failure"):
        store.add_ledger_entry(user_id, 9.0, "manual", "rollback", "失败回滚")

    conn = sqlite3.connect(tmp_db_path)
    ledger_count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=?", (user_id,)).fetchone()[0]
    wallet_count = conn.execute("SELECT COUNT(*) FROM server_user_wallets WHERE user_id=?", (user_id,)).fetchone()[0]
    conn.close()

    assert ledger_count == 0
    assert wallet_count == 0


def test_wallet_snapshot_can_be_rebuilt_from_ledger(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    user_id = _create_user(store, "wallet_rebuild")
    store.add_ledger_entry(user_id, 3.0, "manual", "a", "A")
    store.add_ledger_entry(user_id, 2.0, "manual", "b", "B")

    conn = sqlite3.connect(tmp_db_path)
    conn.execute("UPDATE server_user_wallets SET balance=999 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

    assert store.verify_wallet_consistency(user_id)["consistent"] is False
    rebuilt = store.rebuild_wallet_snapshot(user_id)
    assert rebuilt["balance"] == 5.0
    assert store.verify_wallet_consistency(user_id)["consistent"] is True


def test_external_reward_idempotency_is_scoped_by_user(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    user_a = _create_user(store, "external_a")
    user_b = _create_user(store, "external_b")

    assert store.add_external_reward(user_a, "same-ext", "task", "用户A任务", 4.0)
    assert store.add_external_reward(user_b, "same-ext", "task", "用户B任务", 7.0)

    assert store.claim_rewards(user_a, ["same-ext"]) == 4.0
    assert store.claim_rewards(user_b, ["same-ext"]) == 7.0
    assert store.verify_wallet_consistency(user_a)["wallet_balance"] == 4.0
    assert store.verify_wallet_consistency(user_b)["wallet_balance"] == 7.0


def test_sync_push_rejects_client_reward_ledger(tmp_path):
    db_path = str(tmp_path / "sync-ledger.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "sync_ledger")
    hub = SyncHub(_SyncDb(db_path))

    record = {
        "id": "ledger-sync-1",
        "amount": 6.0,
        "source_type": "manual",
        "source_id": "sync",
        "description": "同步入账",
        "target_date": "2026-06-06",
        "updated_at": "2026-06-06 10:00:00",
    }
    first = asyncio.run(hub.handle_push([{
        "change_id": "ledger-sync-op",
        "table": "reward_ledger",
        "operation": "upsert",
        "payload": record
    }], user_id=user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT amount FROM server_reward_ledger WHERE id='ledger-sync-1'").fetchone()
    conn.close()

    assert first["accepted"] == 0
    assert first["rejected"][0]["reason"] == "server_owned_reward_ledger"
    assert row is None


def test_sync_exercise_and_learning_success_settle_rewards(tmp_path):
    db_path = str(tmp_path / "sync-behavior.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "sync_behavior")
    hub = SyncHub(_SyncDb(db_path))

    exercise_log = {
        "id": "exercise-log-1",
        "date": "2026-06-12",
        "exercise_type": "俯卧撑",
        "duration_minutes": 10,
        "created_at": "2026-06-12 08:00:00",
        "updated_at": "2026-06-12 08:00:00",
    }
    exercise_checkin = {
        "id": "exercise-checkin-1",
        "log_id": "exercise-log-1",
        "status": 1,
        "created_at": "2026-06-12 08:01:00",
        "updated_at": "2026-06-12 08:01:00",
    }
    learning_task = {
        "id": "learning-task-1",
        "kr_id": "kr-1",
        "title": "阅读一章",
        "status": 2,
        "created_at": "2026-06-12 09:00:00",
        "updated_at": "2026-06-12 09:00:00",
    }

    asyncio.run(hub.handle_push([{
        "change_id": "exercise-log-op",
        "table": "exercise_daily_logs",
        "operation": "upsert",
        "payload": exercise_log
    }], user_id=user_id))
    asyncio.run(hub.handle_push([{
        "change_id": "exercise-checkin-op",
        "table": "exercise_checkins",
        "operation": "upsert",
        "payload": exercise_checkin
    }], user_id=user_id))
    asyncio.run(hub.handle_push([{
        "change_id": "learning-task-op",
        "table": "learning_tasks",
        "operation": "upsert",
        "payload": learning_task
    }], user_id=user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT amount, source_type, description FROM server_reward_ledger WHERE user_id=? ORDER BY source_type",
        (user_id,),
    ).fetchall()
    wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=?", (user_id,)).fetchone()
    conn.close()

    assert [row["source_type"] for row in rows] == ["exercise_checkin", "learning_checkin"]
    assert [row["description"] for row in rows] == ["√ 运动 俯卧撑", "√ 学习 阅读一章"]
    assert [row["amount"] for row in rows] == [1.0, 1.0]
    assert wallet["balance"] == 2.0


def test_sync_hub_habit_makeup_uses_reward_rule_service(tmp_path):
    db_path = str(tmp_path / "sync-habit-makeup.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "sync_habit_makeup")
    hub = SyncHub(_SyncDb(db_path))
    hub._reward_rules._now = lambda: "2026-06-12 10:00:00"

    with store._transact() as conn:
        conn.execute(
            """
            INSERT INTO server_habits
                (id, user_id, name, icon, color, sort_order, is_active, difficulty, created_at, updated_at)
            VALUES ('habit-1', ?, '慎独', '', '#A3BE8C', 1, 0, 'easy', '2026-06-01 00:00:00', '2026-06-01 00:00:00')
            """,
            (user_id,),
        )
        reward = hub._reward_rules.calculate_habit_success(user_id, "habit-1", "慎独", "easy", "2026-06-11")
        hub._reward_settlement.settle_habit_success_in_txn(
            conn, user_id, "habit-1", reward.title, reward.amount, "2026-06-11"
        )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT amount, description FROM server_reward_ledger WHERE user_id=? AND source_type='habit_checkin'",
        (user_id,),
    ).fetchone()
    conn.close()

    assert row["amount"] == 0.5
    assert row["description"] == "√ 习惯 [补]慎独"


class _FakeTickTickTasks:
    async def get_projects(self):
        return [{"id": "project-1", "name": "清单"}]

    async def get_project_data(self, project_id):
        return {
            "tasks": [
                {
                    "id": "task-empty-fields",
                    "title": "改后标题",
                    "status": 0,
                    "priority": 5,
                    "tags": [],
                    "etag": "task-empty-fields-v2",
                    "modifiedTime": "2026-06-14T09:30:00+0000",
                }
            ]
        }

    async def get_completed_tasks(self, start_time):
        return []

    async def get_task(self, project_id, task_id):
        return None


class _FakeTickTickPushClient:
    completed = []
    completed_fetches = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def complete_task(self, project_id, task_id):
        type(self).completed.append((project_id, task_id))

    async def update_task(self, project_id, task_id, payload):
        type(self).completed.append((project_id, task_id, payload))

    async def get_completed_tasks(self, start_time):
        type(self).completed_fetches += 1
        return []


class _FakeTickTickCompletedMissingFields:
    def __init__(self):
        self.task_detail_fetches = 0

    async def get_projects(self):
        return [{"id": "project-1", "name": "清单"}]

    async def get_project_data(self, project_id):
        return {"tasks": []}

    async def get_completed_tasks(self, start_time):
        return [{
            "id": "completed-1",
            "status": 2,
            "projectId": "project-1",
            "etag": "completed-1-v2",
            "modifiedTime": "2026-06-18T09:30:00+0000",
            "completedTime": "2026-06-18T09:30:00+0000",
        }]

    async def get_task(self, project_id, task_id):
        self.task_detail_fetches += 1
        return {"id": task_id, "title": "不应读取详情"}


class _FakeTickTickSkippedProjects:
    def __init__(self):
        self.project_data_fetches = []

    async def get_projects(self):
        return [
            {"id": "project-1", "name": "收件箱"},
            {"id": "69edec26e4b02e10952155ab", "name": "📘日志"},
            {"id": "69edec26e4b02e10952155ac", "name": "🔭远期"},
        ]

    async def get_project_data(self, project_id):
        self.project_data_fetches.append(project_id)
        return {"tasks": [{
            "id": f"active-{project_id}",
            "title": "正常项目任务",
            "status": 0,
            "priority": 0,
            "tags": [],
            "etag": f"{project_id}-v1",
            "modifiedTime": "2026-06-18T09:30:00+0000",
        }]}

    async def get_completed_tasks(self, start_time):
        return [{
            "id": "completed-skipped",
            "title": "跳过项目已完成",
            "status": 2,
            "projectId": "69edec26e4b02e10952155ab",
            "priority": 0,
            "tags": [],
            "etag": "completed-skipped-v1",
            "modifiedTime": "2026-06-18T09:30:00+0000",
            "completedTime": "2026-06-18T09:30:00+0000",
        }]

    async def get_task(self, project_id, task_id):
        raise AssertionError("跳过项目不得读取单任务详情")


class _FakeTickTickFailingHabitPush:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def checkin_habit(self, habit_id, stamp, status, value):
        raise RuntimeError("ticktick_500")


def test_task_outbox_push_skips_ticktick_pre_pull_and_post_pull(tmp_path, monkeypatch):
    db_path = str(tmp_path / "task-fast-push.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "task_fast_push")
    hub = SyncHub(_SyncDb(db_path))
    hub._get_ticktick_settings = lambda uid: type("Settings", (), {
        "enabled": True,
        "access_token": "token",
        "host": "https://example.test",
        "verify_tls": True,
        "timeout_seconds": 1,
    })()

    pull_counts = {"tasks": 0, "habits": 0, "trigger": 0}

    async def fake_pull_tasks(client, uid):
        pull_counts["tasks"] += 1
        return {}

    async def fake_pull_habits(client, uid):
        pull_counts["habits"] += 1
        return {}

    async def fake_trigger(client, changed_tables, uid):
        pull_counts["trigger"] += 1

    hub._pull_tasks = fake_pull_tasks
    hub._pull_habits = fake_pull_habits
    hub._trigger_ticktick_pull = fake_trigger
    _FakeTickTickPushClient.completed = []
    _FakeTickTickPushClient.completed_fetches = 0
    monkeypatch.setattr(sync_hub_module, "_get_ticktick_client_class", lambda: _FakeTickTickPushClient)

    result = asyncio.run(hub.handle_push([{
        "change_id": "task-fast-op",
        "table": "tasks",
        "operation": "upsert",
        "payload": {
            "id": "task-fast-1",
            "title": "快速完成",
            "status": 2,
            "priority": 0,
            "project_id": "project-1",
            "updated_at": "2026-06-17 10:00:00",
        },
    }], user_id=user_id))

    assert result["accepted"] == 1
    assert _FakeTickTickPushClient.completed == [("project-1", "task-fast-1")]
    assert _FakeTickTickPushClient.completed_fetches == 0
    assert pull_counts == {"tasks": 0, "habits": 0, "trigger": 0}


def test_habit_push_triggers_habit_scope_pull_only(tmp_path):
    db_path = str(tmp_path / "habit-scope-pull.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "habit_scope_pull")
    hub = SyncHub(_SyncDb(db_path))
    pull_counts = {"tasks": 0, "habits": 0}

    async def fake_pull_tasks(client, uid):
        pull_counts["tasks"] += 1
        return {"active_task_changes": 1}

    async def fake_pull_habits(client, uid):
        pull_counts["habits"] += 1
        return {"habit_changes": 1, "checkin_changes": 1}

    hub._pull_tasks = fake_pull_tasks
    hub._pull_habits = fake_pull_habits
    asyncio.run(hub._trigger_ticktick_pull(object(), ["habit_checkins"], user_id))

    assert pull_counts == {"tasks": 0, "habits": 1}


def test_ticktick_push_failure_is_returned_in_operation_results(tmp_path, monkeypatch):
    db_path = str(tmp_path / "provider-push-failure.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "provider_push_failure")
    hub = SyncHub(_SyncDb(db_path))
    hub._get_ticktick_settings = lambda uid: type("Settings", (), {
        "enabled": True,
        "access_token": "token",
        "host": "https://example.test",
        "verify_tls": True,
        "timeout_seconds": 1,
    })()
    monkeypatch.setattr(sync_hub_module, "_get_ticktick_client_class", lambda: _FakeTickTickFailingHabitPush)

    result = asyncio.run(hub.handle_push([{
        "change_id": "habit-push-fail-op",
        "table": "habit_checkins",
        "operation": "upsert",
        "payload": {
            "id": "habit-1:2026-06-19",
            "habit_id": "habit-1",
            "habit_name": "广告贴",
            "checkin_date": "2026-06-19",
            "status": 2,
            "updated_at": "2026-06-19 10:00:00",
        },
    }], user_id=user_id))

    assert result["operation_results"][0]["status"] == "rejected"
    assert "ticktick_500" in result["operation_results"][0]["reason"]
    assert result["provider_push"]["ok"] is False


def test_ticktick_completed_missing_fields_reuses_local_snapshot_without_task_detail(tmp_path):
    db_path = str(tmp_path / "completed-no-detail.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "completed_no_detail")
    hub = SyncHub(_SyncDb(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_tasks
           (id, user_id, title, priority, status, due_date, tags, source_etag, source_modified_time, raw_json, updated_at)
           VALUES ('completed-1', ?, '本地标题', 3, 0, '2026-06-18 10:00:00', '本地标签',
                   'completed-1-v1', '2026-06-17T09:30:00+0000', '{}', '2026-06-17 10:00:00')""",
        (user_id,),
    )
    conn.commit()
    conn.close()
    client = _FakeTickTickCompletedMissingFields()

    stats = asyncio.run(hub._pull_tasks(client, user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT title, priority, status, due_date, tags FROM server_tasks WHERE id='completed-1'"
    ).fetchone()
    conn.close()

    assert client.task_detail_fetches == 0
    assert stats["completed_detail_skipped"] == 1
    assert row["title"] == "本地标题"
    assert row["priority"] == 3
    assert row["status"] == 2
    assert row["due_date"] == "2026-06-18 10:00:00"
    assert row["tags"] == "本地标签"


def test_ticktick_pull_skips_fixed_project_ids_and_completed_rewards(tmp_path):
    db_path = str(tmp_path / "skipped-projects.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "skipped_projects")
    hub = SyncHub(_SyncDb(db_path))
    reward_calls = []
    hub._reward_task_if_new = lambda *args: reward_calls.append(args)
    client = _FakeTickTickSkippedProjects()

    stats = asyncio.run(hub._pull_tasks(client, user_id))

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT id FROM server_tasks WHERE id='completed-skipped'"
    ).fetchone()
    conn.close()

    assert client.project_data_fetches == ["project-1"]
    assert {item["id"] for item in stats["skipped_projects"]} == {
        "69edec26e4b02e10952155ab",
        "69edec26e4b02e10952155ac",
    }
    assert stats["skipped_completed_projects"] == 1
    assert row is None
    assert reward_calls == []


def test_ticktick_pull_clears_empty_due_date_and_tags(tmp_path):
    db_path = str(tmp_path / "ticktick-fields.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "ticktick_fields")
    hub = SyncHub(_SyncDb(db_path))

    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_tasks
           (id, user_id, title, priority, status, due_date, tags, raw_json, updated_at)
           VALUES ('task-empty-fields', ?, '旧标题', 1, 0, '2026-06-12T10:00:00.000+0000', '旧标签', '{}', '2026-06-12 08:00:00')""",
        (user_id,),
    )
    conn.commit()
    conn.close()

    stats = asyncio.run(hub._pull_tasks(_FakeTickTickTasks(), user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT title, priority, due_date, tags FROM server_tasks WHERE id='task-empty-fields'"
    ).fetchone()
    conn.close()

    assert stats["active_tasks"] == 1
    assert row["title"] == "改后标题"
    assert row["priority"] == 5
    assert row["due_date"] == ""
    assert row["tags"] == ""


class _FakeTickTickHabits:
    async def get_habits(self):
        return [{
            "id": "habit-sync-1",
            "name": "慎独",
            "status": 0,
            "sortOrder": 1,
            "iconRes": "txt_慎",
            "etag": "habit-sync-1-v1",
            "modifiedTime": "2026-06-14T09:30:00+0000",
        }]

    async def get_habit_sections(self):
        return []

    async def get_habit_checkins(self, habit_ids, from_stamp, to_stamp):
        return [{"habitId": "habit-sync-1", "checkins": [{
            "stamp": "20260610",
            "status": 2,
            "opTime": "2026-06-14T09:30:00+0000",
        }]}]


class _FakeTickTickHabitStatus:
    def __init__(self, status_by_date):
        self.status_by_date = status_by_date

    async def get_habits(self):
        return [{
            "id": "habit-status-1",
            "name": "状态习惯",
            "status": 0,
            "sortOrder": 1,
            "iconRes": "txt_状",
            "etag": "habit-status-1-v1",
            "modifiedTime": "2026-06-14T09:30:00+0000",
        }]

    async def get_habit_sections(self):
        return []

    async def get_habit_checkins(self, habit_ids, from_stamp, to_stamp):
        checkins = []
        for date, status in self.status_by_date.items():
            if status in (1, 2):
                checkins.append({
                    "stamp": date.replace("-", ""),
                    "status": status,
                    "opTime": f"{date}T09:30:00+0000",
                })
        return [{"habitId": "habit-status-1", "checkins": checkins}]


class _FakeTickTickHabitMissingBlock(_FakeTickTickHabitStatus):
    async def get_habit_checkins(self, habit_ids, from_stamp, to_stamp):
        return []


class _FakeTickTickHabitCheckinFailure(_FakeTickTickHabitStatus):
    async def get_habit_checkins(self, habit_ids, from_stamp, to_stamp):
        raise RuntimeError("checkin request failed")


def _build_real_sync_hub(db_path, username):
    store = ServerSleepStore(db_path=str(db_path))
    user_id = _create_user(store, username)
    db = ServerDBWrapper()
    db.log_path = str(db_path)
    hub = SyncHub(db)
    hub._reward_rules._now = lambda: "2026-06-17 10:00:00"
    return store, user_id, hub


HABIT_SYNC_DATE = "2026-08-14"


def _seed_habit_checkin(db_path, user_id, status, date=HABIT_SYNC_DATE, source_modified_time="old-op"):
    habit_id = f"ticktick:{user_id}:habit-status-1"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO server_habits
            (id, user_id, name, icon, color, sort_order, is_active, difficulty, source_etag, created_at, updated_at)
        VALUES (?, ?, '状态习惯', '', '#A3BE8C', 1, 0, 'easy', 'habit-status-1-v1',
                '2026-06-01 00:00:00', '2026-06-01 00:00:00')
        ON CONFLICT(id) DO NOTHING
        """,
        (habit_id, user_id),
    )
    RewardConfigService().ensure_item(conn, user_id, "habit", habit_id, difficulty="easy")
    if status is not None:
        conn.execute(
            """
            INSERT INTO server_habit_checkins
                (id, user_id, habit_id, habit_name, checkin_date, checkin_time, status, source_modified_time, updated_at)
            VALUES (?, ?, ?, '状态习惯', ?, ?, ?, ?, ?)
            """,
            (f"checkin-{date}", user_id, habit_id, date, f"{date} 08:00:00", status, source_modified_time, f"{date} 08:00:00"),
        )
    conn.commit()
    conn.close()


@pytest.mark.parametrize(
    "old_status,remote_status,expected",
    [
        (2, 0, 0),
        (1, 0, 0),
        (2, 1, 1),
        (1, 2, 2),
        (None, 1, 1),
        (None, 2, 2),
    ],
)
def test_ticktick_habit_pull_aligns_status_matrix_and_writes_change_log(tmp_path, old_status, remote_status, expected):
    db_path = tmp_path / f"habit-status-{old_status}-{remote_status}.db"
    _, user_id, hub = _build_real_sync_hub(db_path, f"habit_status_{old_status}_{remote_status}")
    target_date = HABIT_SYNC_DATE
    _seed_habit_checkin(db_path, user_id, old_status, date=target_date)

    asyncio.run(hub._pull_habits(_FakeTickTickHabitStatus({target_date: remote_status}), user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT date, checkin_date, status FROM server_habit_checkins WHERE user_id=? AND checkin_date=?",
        (user_id, target_date),
    ).fetchone()
    change_count = conn.execute(
        "SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND table_name='server_habit_checkins'",
        (user_id,),
    ).fetchone()[0]
    conn.close()

    assert row["status"] == expected
    assert row["date"] == row["checkin_date"] == target_date
    assert change_count >= 1


def test_ticktick_habit_pull_persists_provider_operation_time_not_pull_time(tmp_path):
    db_path = tmp_path / "habit-provider-operation-time.db"
    _, user_id, hub = _build_real_sync_hub(db_path, "habit_provider_operation_time")

    asyncio.run(hub._pull_habits(_FakeTickTickHabitStatus({HABIT_SYNC_DATE: 2}), user_id))

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT checkin_time FROM server_habit_checkins WHERE user_id=? AND checkin_date=?",
        (user_id, HABIT_SYNC_DATE),
    ).fetchone()
    conn.close()

    assert row == (f"{HABIT_SYNC_DATE} 17:30:00",)


def test_ticktick_habit_pull_switches_reward_side_effects(tmp_path):
    db_path = tmp_path / "habit-reward-switch.db"
    _, user_id, hub = _build_real_sync_hub(db_path, "habit_reward_switch")
    _seed_habit_checkin(db_path, user_id, 2)
    habit_id = f"ticktick:{user_id}:habit-status-1"

    with hub._transact() as conn:
        reward = hub._reward_rules.calculate_habit_success(user_id, habit_id, "状态习惯", "easy", HABIT_SYNC_DATE)
        hub._reward_settlement.settle_habit_success_in_txn(
            conn, user_id, habit_id, reward.title, reward.amount, HABIT_SYNC_DATE
        )

    asyncio.run(hub._pull_habits(_FakeTickTickHabitStatus({HABIT_SYNC_DATE: 1}), user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT source_type, amount FROM server_reward_ledger WHERE user_id=? ORDER BY source_type",
        (user_id,),
    ).fetchall()
    wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=?", (user_id,)).fetchone()
    reward_versions = conn.execute(
        "SELECT operation FROM server_change_log WHERE user_id=? AND table_name='server_reward_ledger' ORDER BY server_version",
        (user_id,),
    ).fetchall()
    wallet_versions = conn.execute(
        "SELECT operation FROM server_change_log WHERE user_id=? AND table_name='server_user_wallets' ORDER BY server_version",
        (user_id,),
    ).fetchall()
    conn.close()

    assert [row["source_type"] for row in rows] == ["habit_fail"]
    assert rows[0]["amount"] < 0
    assert wallet["balance"] == rows[0]["amount"]
    assert [row["operation"] for row in reward_versions] == ["delete", "upsert"]
    assert [row["operation"] for row in wallet_versions] == ["upsert"]


def test_reward_state_rolls_back_when_version_write_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "reward-version-rollback.db"
    _, user_id, hub = _build_real_sync_hub(db_path, "reward_version_rollback")
    with hub._transact() as conn:
        hub._reward_settlement.settle_habit_success_in_txn(
            conn, user_id, "habit-status-1", "状态习惯", 1.0, "2026-06-10"
        )

    def fail_write(*args, **kwargs):
        raise RuntimeError("version write failed")

    monkeypatch.setattr(hub.db, "write_server_change", fail_write)
    with pytest.raises(RuntimeError, match="version write failed"):
        with hub._transact() as conn:
            hub._replace_habit_reward_in_txn(
                conn, user_id, "habit-status-1", "状态习惯", "easy", "2026-06-10", 1
            )

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT source_type, amount FROM server_reward_ledger WHERE user_id=?", (user_id,)
    ).fetchall()
    wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=?", (user_id,)).fetchone()
    conn.close()

    assert rows == [("habit_checkin", 1.0)]
    assert wallet == (1.0,)


def test_client_habit_toggle_does_not_create_final_reward_locally():
    source = (Path(__file__).parents[2] / "core" / "models" / "Database.ts").read_text(encoding="utf-8")
    body = source[source.index("  toggleCheckin("):source.index("  getTodayCheckins(")]

    assert "addLedgerEntry(" not in body
    assert "removeLedgerForCancelledCheckin(" not in body


@pytest.mark.parametrize(
    "old_status,source_type",
    [
        (2, "habit_checkin"),
        (1, "habit_fail"),
    ],
)
def test_ticktick_habit_pull_clears_reward_side_effects_and_versions_wallet(tmp_path, old_status, source_type):
    db_path = tmp_path / f"habit-reward-clear-{old_status}.db"
    _, user_id, hub = _build_real_sync_hub(db_path, f"habit_reward_clear_{old_status}")
    _seed_habit_checkin(db_path, user_id, old_status)
    habit_id = f"ticktick:{user_id}:habit-status-1"

    with hub._transact() as conn:
        if old_status == 2:
            reward = hub._reward_rules.calculate_habit_success(user_id, habit_id, "状态习惯", "easy", HABIT_SYNC_DATE)
            hub._reward_settlement.settle_habit_success_in_txn(
                conn, user_id, habit_id, reward.title, reward.amount, HABIT_SYNC_DATE
            )
        else:
            reward = hub._reward_rules.calculate_habit_fail(user_id, habit_id, "状态习惯", "easy")
            hub._reward_settlement.settle_habit_fail_in_txn(
                conn, user_id, habit_id, reward.title, reward.amount, HABIT_SYNC_DATE
            )

    asyncio.run(hub._pull_habits(_FakeTickTickHabitStatus({HABIT_SYNC_DATE: 0}), user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    checkin = conn.execute(
        "SELECT status FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND checkin_date=?",
        (user_id, habit_id, HABIT_SYNC_DATE),
    ).fetchone()
    ledger_count = conn.execute(
        "SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=? AND source_type=?",
        (user_id, source_type),
    ).fetchone()[0]
    wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=?", (user_id,)).fetchone()
    delete_change = conn.execute(
        "SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND table_name='server_reward_ledger' AND operation='delete'",
        (user_id,),
    ).fetchone()[0]
    wallet_change = conn.execute(
        "SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND table_name='server_user_wallets' AND operation='upsert'",
        (user_id,),
    ).fetchone()[0]
    conn.close()

    assert checkin["status"] == 0
    assert ledger_count == 0
    assert wallet["balance"] == 0.0
    assert delete_change >= 1
    assert wallet_change >= 1


def test_ticktick_habit_pull_unchanged_op_time_does_not_duplicate_change_log(tmp_path):
    db_path = tmp_path / "habit-unchanged-op-time.db"
    _, user_id, hub = _build_real_sync_hub(db_path, "habit_unchanged_op")
    _seed_habit_checkin(db_path, user_id, 2, source_modified_time=f"{HABIT_SYNC_DATE}T09:30:00+0000")

    asyncio.run(hub._pull_habits(_FakeTickTickHabitStatus({HABIT_SYNC_DATE: 2}), user_id))

    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND table_name='server_habit_checkins'",
        (user_id,),
    ).fetchone()[0]
    conn.close()

    assert count == 0


@pytest.mark.parametrize("old_status", [1, 2])
def test_ticktick_habit_pull_missing_block_clears_local_checkin(tmp_path, old_status):
    db_path = tmp_path / f"habit-missing-block-{old_status}.db"
    _, user_id, hub = _build_real_sync_hub(db_path, f"habit_missing_block_{old_status}")
    _seed_habit_checkin(db_path, user_id, old_status)

    stats = asyncio.run(hub._pull_habits(_FakeTickTickHabitMissingBlock({}), user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM server_habit_checkins WHERE user_id=? AND checkin_date=?",
        (user_id, HABIT_SYNC_DATE),
    ).fetchone()
    change_count = conn.execute(
        "SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND table_name='server_habit_checkins'",
        (user_id,),
    ).fetchone()[0]
    conn.close()

    assert stats["missing_checkin_blocks"] == 1
    assert row["status"] == 0
    assert change_count >= 1


def test_ticktick_habit_pull_failed_checkins_do_not_clear_local_checkin(tmp_path):
    db_path = tmp_path / "habit-checkin-failure.db"
    _, user_id, hub = _build_real_sync_hub(db_path, "habit_checkin_failure")
    _seed_habit_checkin(db_path, user_id, 2)

    with pytest.raises(RuntimeError, match="checkin request failed"):
        asyncio.run(hub._pull_habits(_FakeTickTickHabitCheckinFailure({}), user_id))

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status FROM server_habit_checkins WHERE user_id=? AND checkin_date=?",
        (user_id, HABIT_SYNC_DATE),
    ).fetchone()
    conn.close()

    assert row[0] == 2


def test_ticktick_habit_list_timeout_preserves_original_error(tmp_path):
    _, user_id, hub = _build_real_sync_hub(tmp_path / "habit-list-timeout.db", "habit_list_timeout")

    class FailingHabitList:
        async def get_habits(self):
            raise TimeoutError("habit list timeout")

    with pytest.raises(TimeoutError, match="habit list timeout"):
        asyncio.run(hub._pull_habits(FailingHabitList(), user_id))


def test_provider_reconcile_is_single_flight(tmp_path):
    db_path = tmp_path / "provider-single-flight.db"
    _, user_id, hub = _build_real_sync_hub(db_path, "provider_single_flight")
    calls = {"count": 0}

    async def run_case():
        release = asyncio.Event()

        async def slow_reconcile(uid, request_id=None):
            calls["count"] += 1
            await release.wait()
            return {"ok": True, "request_id": request_id, "merged_count": 0, "errors": []}

        hub._force_pull_ticktick_impl = slow_reconcile
        first = asyncio.create_task(hub.force_pull_ticktick(user_id, "first"))
        await asyncio.sleep(0)
        second = await hub.force_pull_ticktick(user_id, "second")
        release.set()
        first_result = await first
        return first_result, second

    first_result, second = asyncio.run(run_case())

    assert calls["count"] == 1
    assert first_result["request_id"] == "first"
    assert second["skipped"] is True
    assert second["reason"] == "in_flight"


def test_ticktick_habit_makeup_pull_is_ledger_idempotent(tmp_path):
    db_path = str(tmp_path / "ticktick-habit-idempotent.db")
    store = ServerSleepStore(db_path=db_path)
    user_id = _create_user(store, "ticktick_habit_idempotent")
    hub = SyncHub(_SyncDb(db_path))
    hub._reward_rules._now = lambda: "2026-06-12 10:00:00"

    asyncio.run(hub._pull_habits(_FakeTickTickHabits(), user_id))
    asyncio.run(hub._pull_habits(_FakeTickTickHabits(), user_id))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT amount, source_type, source_id, target_date
           FROM server_reward_ledger
           WHERE user_id=? AND source_type='habit_checkin'""",
        (user_id,),
    ).fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0]["source_id"] == "habit-sync-1"
    assert rows[0]["target_date"] == "2026-06-10"


def test_store_buy_reward_uses_transactional_settlement(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    user_id = _create_user(store, "buy_reward")
    with store._transact() as conn:
        conn.execute(
            """
            INSERT INTO server_rewards (id, user_id, title, icon, price, is_active, created_at, updated_at)
            VALUES ('reward-1', ?, '看电影', '', 3.0, 1, '2026-06-12 10:00:00', '2026-06-12 10:00:00')
            """,
            (user_id,),
        )
        store.reward_settlement_service.settle_task_success_in_txn(
            conn, user_id, "task-1", "准备金币", 5.0, "2026-06-12"
        )

    assert store.buy_reward(user_id, "reward-1") == (True, "购买成功")
    assert store.verify_wallet_consistency(user_id)["wallet_balance"] == 2.0

    conn = sqlite3.connect(tmp_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT amount, description FROM server_reward_ledger WHERE user_id=? AND source_type='reward_buy'",
        (user_id,),
    ).fetchone()
    conn.close()

    assert row["amount"] == -3.0
    assert row["description"] == "√ 兑换 看电影"
