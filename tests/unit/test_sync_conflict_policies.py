# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import sqlite3

from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub
from server.domain.sample_data_initialization_service import SampleDataInitializationService


def _ensure_tasks_lookup_table(conn):
    """sync_hub._push_one_ticktick 在缺少 project_id 时会回查 tasks 表。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            project_id TEXT,
            raw_json TEXT,
            PRIMARY KEY (id, user_id)
        )
        """
    )


def _hub(tmp_path):
    db_path = tmp_path / "sync_conflict_policies.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    _ensure_tasks_lookup_table(conn)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-06-13 00:00:00')"
    )
    conn.commit()
    conn.close()

    db = ServerDBWrapper()
    db.log_path = str(db_path)
    return db_path, SyncHub(db)


def test_completed_task_does_not_block_reopen(tmp_path):
    _, hub = _hub(tmp_path)
    remote = {"status": 0, "updated_at": "2026-06-19 13:00:00"}

    action = hub._resolve(
        {"status": 2, "updated_at": "2026-06-19 12:00:00"},
        remote,
    )

    assert action == "pull"
    assert remote["status"] == 0


def test_categories_use_account_scoped_name_when_client_ids_collide(tmp_path):
    db_path, hub = _hub(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (2, 'u2', 'p', '2026-06-13 00:00:00')"
    )
    # ID=16 已被另一账号占用，模拟本地客户端的自增 ID 冲突。
    conn.execute(
        "INSERT INTO server_categories (id,user_id,name,group_name,sort_order,updated_at) VALUES (16,2,'别人的分类','默认',1,'2026-06-13 00:00:00')"
    )
    conn.commit(); conn.close()

    result = asyncio.run(hub.handle_push([{
        "table": "categories", "change_id": "local-rest-16", "operation": "upsert",
        "payload": {"id": 16, "name": "休息", "group_name": "生活", "icon": "x", "color": "#fff", "sort_order": 13, "updated_at": "2026-08-29 00:00:00"},
    }], user_id=1))

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id,name FROM server_categories WHERE user_id=1 AND name='休息'").fetchone()
    foreign = conn.execute("SELECT name FROM server_categories WHERE id=16").fetchone()
    conn.close()
    assert row is not None and row[0] != 16
    assert foreign == ('别人的分类',)
    assert result["operation_results"][0]["record_id"] == str(row[0])


def test_default_timer_categories_are_visible_in_versioned_pull(tmp_path):
    db_path, hub = _hub(tmp_path)
    SampleDataInitializationService(str(db_path)).ensure_user_sample_data(1)

    result = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=500))
    categories = result["tables"]["categories"]

    assert len(categories) == 19
    assert [row["name"] for row in sorted(categories, key=lambda row: row["sort_order"])] == [
        "输入", "输出", "副业生产", "副业营销", "副业研发", "工作", "吃饭", "带娃", "家务", "娱乐",
        "交通", "个人杂事", "休息", "活动", "运动", "松鼠病", "状态切换", "睡觉", "拉屎",
    ]
    assert len({row["id"] for row in categories}) == 19


def test_wallet_and_reward_ledger_are_server_owned(tmp_path):
    _, hub = _hub(tmp_path)

    result = asyncio.run(hub.handle_push([
        {
            "table": "wallet",
            "change_id": "wallet-op",
            "operation": "upsert",
            "payload": {"id": "wallet-1", "balance": 999},
        },
        {
            "table": "reward_ledger",
            "change_id": "ledger-op",
            "operation": "upsert",
            "payload": {"id": "ledger-1", "amount": 999, "source_type": "manual"},
        },
        {
            "table": "goals",
            "change_id": "goal-op",
            "operation": "upsert",
            "payload": {"id": "goal-1", "title": "local"},
        },
        {
            "table": "rewards",
            "change_id": "reward-op",
            "operation": "upsert",
            "payload": {"id": "reward-1", "title": "local"},
        },
        {
            "table": "external_rewards",
            "change_id": "external-reward-op",
            "operation": "upsert",
            "payload": {"ext_id": "external-1", "item_type": "goal"},
        },
    ], user_id=1))

    reasons = {item["reason"] for item in result["operation_results"]}
    assert "server_owned_wallet" in reasons
    assert "server_owned_reward_ledger" in reasons
    assert "server_owned_goals" in reasons
    assert "server_owned_rewards" in reasons
    assert "server_owned_external_rewards" in reasons


def test_atimelogger_provider_config_is_server_owned_and_cannot_be_overwritten_by_sync(tmp_path):
    db_path, hub = _hub(tmp_path)
    authoritative = {
        "enabled": True,
        "username": "fixture-user",
        "password": "fixture-server-password",
        "token": "fixture-valid-token",
        "auth_verified_at": "2026-07-19 21:40:00",
        "auth_required": False,
    }
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO server_system_config (user_id, key, value, value_type, updated_at) VALUES (1, 'atimelogger_config', ?, 'json', '2026-07-19 21:40:00')",
        (json.dumps(authoritative),),
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_push([{
        "table": "system_config",
        "change_id": "stale-atimelogger-config",
        "operation": "upsert",
        "payload": {
            "key": "atimelogger_config",
            "value": json.dumps({"password": "WEB_ENC:local-value", "token": "", "auth_required": False}),
            "value_type": "json",
            "updated_at": "2026-07-19 21:42:00",
        },
    }], user_id=1))

    conn = sqlite3.connect(db_path)
    saved = json.loads(conn.execute(
        "SELECT value FROM server_system_config WHERE user_id=1 AND key='atimelogger_config'"
    ).fetchone()[0])
    conn.close()

    assert result["accepted"] == 0
    assert result["operation_results"][0]["reason"] == "server_owned_atimelogger_config"
    assert saved == authoritative


def test_account_scoped_config_cannot_contaminate_second_user_or_return_habits(tmp_path):
    db_path, hub = _hub(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (2, 'u2', 'p', '2026-07-28 01:00:00')")
    conn.execute("INSERT INTO server_habits (id, user_id, name, icon, is_active, created_at, updated_at) VALUES ('a-habit', 1, 'A', 'x', 1, '2026-07-28 01:00:00', '2026-07-28 01:00:00')")
    conn.commit(); conn.close()

    result = asyncio.run(hub.handle_push([{
        "table": "system_config", "change_id": "copied-provider", "operation": "upsert",
        "payload": {"key": "ticktick_config", "value": "{}", "value_type": "json"},
    }], user_id=2))
    pull = asyncio.run(hub.handle_pull_by_version(0, user_id=2, limit=50))

    assert result["operation_results"][0]["reason"] == "account_scoped_config"
    assert pull["tables"].get("habits", []) == []
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM server_system_config WHERE user_id=2").fetchone()[0]
    finally:
        conn.close()
    assert count == 0


def test_environment_verified_user_marker_is_not_written_to_server_config(tmp_path):
    db_path, hub = _hub(tmp_path)
    result = asyncio.run(hub.handle_push([{
        "table": "system_config", "change_id": "local-identity-marker", "operation": "upsert",
        "payload": {"key": "env_development_verified_user_id", "value": "1", "value_type": "string"},
    }], user_id=1))

    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM server_system_config WHERE user_id=1 AND key='env_development_verified_user_id'"
    ).fetchone()[0]
    conn.close()

    assert result["accepted"] == 0
    assert result["operation_results"][0]["reason"] == "account_scoped_config"
    assert count == 0


def test_client_habit_checkin_write_is_rejected_without_mutating_server_fact(tmp_path):
    db_path, hub = _hub(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_habits
           (id, user_id, name, icon, is_active, difficulty, created_at, updated_at)
           VALUES ('h1', 1, '慎独', 'x', 0, 'easy', '2026-06-13 00:00:00', '2026-06-13 00:00:00')"""
    )
    conn.execute(
        """INSERT INTO server_habit_checkins
           (id, user_id, habit_id, checkin_date, status, updated_at)
           VALUES ('ci-server', 1, 'h1', '2026-06-13', 0, '2026-06-13 00:00:00')"""
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_push([
        {
            "table": "habit_checkins",
            "change_id": "ci-op",
            "operation": "upsert",
            "payload": {
                "id": "ci-client",
                "habit_id": "h1",
                "checkin_date": "2026-06-13",
                "status": 2,
                "updated_at": "2026-06-13 08:00:00",
            },
        }
    ], user_id=1))

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, status FROM server_habit_checkins WHERE user_id=1 AND habit_id='h1' AND checkin_date='2026-06-13'"
    ).fetchall()
    conn.close()

    assert result["accepted"] == 0
    assert result["operation_results"][0]["reason"] == "server_authoritative_habit_checkin_command_required"
    assert rows == [("ci-server", 0)]


def test_tombstone_blocks_stale_task_resurrection_and_logs_conflict(tmp_path):
    db_path, hub = _hub(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_tasks
           (id, user_id, title, status, updated_at, deleted_at)
           VALUES ('t1', 1, '旧任务', 0, '2026-06-13 09:00:00', '2026-06-13 09:00:00')"""
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_push([
        {
            "table": "tasks",
            "change_id": "task-stale",
            "device_id": "pc-1",
            "operation": "upsert",
            "payload": {
                "id": "t1",
                "title": "试图复活",
                "status": 0,
                "updated_at": "2026-06-13 08:00:00",
            },
        }
    ], user_id=1))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    task = conn.execute("SELECT title, status, deleted_at FROM server_tasks WHERE id='t1'").fetchone()
    conflict = conn.execute("SELECT strategy, result FROM server_sync_conflicts WHERE record_id='t1'").fetchone()
    conn.close()

    assert result["operation_results"][0]["reason"] == "tombstone_protected"
    assert task["title"] == "旧任务"
    assert task["status"] == 0
    assert task["deleted_at"] == "2026-06-13 09:00:00"
    assert conflict["strategy"] == "tombstone_wins"
    assert conflict["result"] == "rejected_stale_update"


def test_task_title_edit_is_rejected_until_it_uses_the_command_api(tmp_path):
    db_path, hub = _hub(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO server_tasks
           (id, user_id, title, priority, status, updated_at)
           VALUES ('t2', 1, '服务端标题', 0, 0, '2026-06-13 09:00:00')"""
    )
    conn.commit()
    conn.close()

    result = asyncio.run(hub.handle_push([
        {
            "table": "tasks",
            "change_id": "task-merge",
            "device_id": "pc-1",
            "operation": "upsert",
            "payload": {
                "id": "t2",
                "title": "客户端标题",
                "priority": 5,
                "status": 0,
                "updated_at": "2026-06-13 08:00:00",
            },
        }
    ], user_id=1))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    task = conn.execute("SELECT title, priority FROM server_tasks WHERE id='t2'").fetchone()
    conn.close()

    assert result["accepted"] == 0
    assert result["operation_results"][0]["reason"] == "task_structure_requires_command"
    assert task["title"] == "服务端标题"
    assert task["priority"] == 0


class _FakeTickTickPush:
    def __init__(self):
        self.completed = []
        self.tasks = {}

    async def complete_task(self, project_id, task_id):
        self.completed.append(task_id)
        self.tasks[task_id] = {"id": task_id, "project_id": project_id, "status": 2}
        return {}

    async def update_task(self, project_id, task_id, data):
        self.tasks[task_id] = {"id": task_id, "project_id": project_id, **data}
        return {}

    async def get_task(self, project_id, task_id):
        return self.tasks.get(task_id)

    async def get_completed_tasks(self, start_time):
        return [task for task in self.tasks.values() if task.get("status") == 2]


def test_push_delta_selection_uses_id_only_for_tasks_and_habits(tmp_path):
    _, hub = _hub(tmp_path)

    task_delta, task_error = hub._select_push_delta("tasks", {"id": "task-1", "status": 2}, "push")
    habit_delta, habit_error = hub._select_push_delta("habits", {"id": "habit-1", "name": "慎独"}, "push")

    assert task_error is None
    assert task_delta["record_id"] == "task-1"
    assert task_delta["record"] == {"id": "task-1", "status": 2}
    assert habit_error is None
    assert habit_delta["record_id"] == "habit-1"


def test_push_delta_selection_rejects_missing_id_with_table_action_log(tmp_path, caplog):
    _, hub = _hub(tmp_path)

    with caplog.at_level(logging.WARNING):
        delta, error = hub._select_push_delta("tasks", {"status": 2}, "push")

    assert delta is None
    assert error == {"table": "tasks", "record_id": None, "reason": "missing_id", "action": "push"}
    assert "table=tasks" in caplog.text
    assert "action=push" in caplog.text


def test_ticktick_task_push_uses_task_id_only_and_rejects_status_four(tmp_path):
    db_path, hub = _hub(tmp_path)
    client = _FakeTickTickPush()

    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO tasks (id, user_id, project_id) VALUES (?, 1, ?)",
        [("task-complete", "proj-1"), ("task-invalid", "proj-1")],
    )
    conn.commit()
    conn.close()

    complete = asyncio.run(hub._push_one_ticktick(client, "tasks", {
        "id": "task-complete",
        "status": 2,
    }, user_id=1))
    invalid = asyncio.run(hub._push_one_ticktick(client, "tasks", {
        "id": "task-invalid",
        "status": 4,
    }, user_id=1))

    assert complete["action"] == "complete_task"
    assert complete["record_id"] == "task-complete"
    assert invalid == {"table": "tasks", "record_id": "task-invalid", "ok": False, "error": "invalid_task_status"}
    assert client.completed == ["task-complete"]
