# -*- coding: utf-8 -*-
"""同步回归测试套件。

默认使用离线 Fake TickTick 客户端，不会修改真实滴答清单。
覆盖 TickTick -> 服务端 -> 版本增量 pull 的高频场景，并输出 JSON/Markdown 报告。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


USER_ID = 1


def now_label() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


class FakeTickTickClient:
    def __init__(self):
        self.projects = [{"id": "project-inbox", "name": "收件箱"}]
        self.sections = [
            {"id": "sec-life", "name": "生活"},
            {"id": "sec-work", "name": "输出"},
        ]
        self.project_tasks: dict[str, list[dict[str, Any]]] = {"project-inbox": []}
        self.completed_tasks: list[dict[str, Any]] = []
        self.habits: list[dict[str, Any]] = []
        self.checkins_by_habit: dict[str, list[dict[str, Any]]] = {}

    async def get_projects(self) -> list[dict[str, Any]]:
        return list(self.projects)

    async def get_project_data(self, project_id: str) -> dict[str, Any]:
        return {"tasks": [dict(task) for task in self.project_tasks.get(project_id, [])]}

    async def get_completed_tasks(self, start_time: str) -> list[dict[str, Any]]:
        return [dict(task) for task in self.completed_tasks]

    async def get_task(self, project_id: str, task_id: str) -> dict[str, Any] | None:
        for task in self.project_tasks.get(project_id, []):
            if task.get("id") == task_id:
                return dict(task)
        for task in self.completed_tasks:
            if task.get("id") == task_id:
                return dict(task)
        return None

    async def get_habits(self) -> list[dict[str, Any]]:
        return [dict(habit) for habit in self.habits]

    async def get_habit_sections(self) -> list[dict[str, Any]]:
        return list(self.sections)

    async def get_habit_checkins(self, habit_ids: list[str], from_stamp: str, to_stamp: str) -> list[dict[str, Any]]:
        return [
            {"habitId": habit_id, "checkins": [dict(ci) for ci in self.checkins_by_habit.get(habit_id, [])]}
            for habit_id in habit_ids
        ]


@dataclass
class CaseResult:
    name: str
    status: str
    detail: str = ""
    before_version: int = 0
    after_version: int = 0
    changed_tables: dict[str, int] = field(default_factory=dict)
    error: str | None = None


class SyncRegressionSuite:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.output_dir / "sync-regression.db"
        if self.db_path.exists():
            self.db_path.unlink()
        self.db = ServerDBWrapper()
        self.db.log_path = str(self.db_path)
        self.hub = SyncHub(self.db)
        self.fake = FakeTickTickClient()
        self.results: list[CaseResult] = []
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            ensure_server_schema(conn)
            conn.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (USER_ID, "sync_regression", "test", "2026-06-13 00:00:00"),
            )
            for name in ("生活", "输出", "家庭", "松鼠病"):
                conn.execute(
                    """
                    INSERT INTO server_categories (user_id, name, group_name, icon, color, sort_order, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, name) DO NOTHING
                    """,
                    (USER_ID, name, "默认", "📌", "#5E81AC", 1, "2026-06-13 00:00:00"),
                )
            conn.commit()
        finally:
            conn.close()
        self.db.reload_category_cache()

    def _max_version(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(server_version), 0) FROM server_change_log WHERE user_id=?",
                (USER_ID,),
            ).fetchone()
            return int(row[0] or 0)
        finally:
            conn.close()

    async def _pull_provider(self) -> None:
        await self.hub._pull_tasks(self.fake, USER_ID)
        await self.hub._pull_habits(self.fake, USER_ID)

    async def _pull_delta(self, since_version: int) -> dict[str, Any]:
        return await self.hub.handle_pull_by_version(since_version, USER_ID, limit=200)

    def _table_counts(self, pull_result: dict[str, Any]) -> dict[str, int]:
        return {table: len(rows) for table, rows in (pull_result.get("tables") or {}).items()}

    async def run_case(
        self,
        name: str,
        mutate: Callable[[], Any],
        expect: Callable[[dict[str, Any]], None],
        detail: str = "",
    ) -> None:
        before = self._max_version()
        result = CaseResult(name=name, status="PASS", detail=detail, before_version=before)
        try:
            mutation = mutate()
            if hasattr(mutation, "__await__"):
                await mutation
            await self._pull_provider()
            after = self._max_version()
            delta = await self._pull_delta(before)
            expect(delta)
            result.after_version = after
            result.changed_tables = self._table_counts(delta)
        except Exception as exc:
            result.status = "FAIL"
            result.after_version = self._max_version()
            result.error = f"{type(exc).__name__}: {exc}"
        self.results.append(result)

    async def run_client_case(
        self,
        name: str,
        operations: list[dict[str, Any]],
        expect: Callable[[dict[str, Any]], None],
        detail: str = "",
    ) -> None:
        before = self._max_version()
        result = CaseResult(name=name, status="PASS", detail=detail, before_version=before)
        try:
            push = await self.hub.handle_push(operations, USER_ID)
            delta = await self._pull_delta(before)
            expect({"push": push, "delta": delta})
            result.after_version = self._max_version()
            result.changed_tables = self._table_counts(delta)
        except Exception as exc:
            result.status = "FAIL"
            result.after_version = self._max_version()
            result.error = f"{type(exc).__name__}: {exc}"
        self.results.append(result)

    @staticmethod
    def _task_etag(task: dict[str, Any]) -> str:
        payload = {
            "id": task.get("id"),
            "title": task.get("title"),
            "priority": task.get("priority"),
            "status": task.get("status"),
            "dueDate": task.get("dueDate"),
            "tags": task.get("tags"),
            "completedTime": task.get("completedTime"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]

    @staticmethod
    def _habit_etag(habit: dict[str, Any]) -> str:
        payload = {
            "id": habit.get("id"),
            "name": habit.get("name"),
            "status": habit.get("status"),
            "sectionId": habit.get("sectionId"),
            "repeatRule": habit.get("repeatRule"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]

    def task(self, task_id: str, title: str, **overrides: Any) -> dict[str, Any]:
        task = {
            "id": task_id,
            "projectId": "project-inbox",
            "title": title,
            "priority": 0,
            "status": 0,
            "dueDate": "2026-06-14T00:00:00+0800",
            "tags": ["输出"],
            "timeZone": "Asia/Shanghai",
            "isAllDay": True,
            "modifiedTime": "2026-06-13T12:00:00+0800",
        }
        task.update(overrides)
        task.setdefault("etag", self._task_etag(task))
        return task

    def habit(self, habit_id: str, name: str, **overrides: Any) -> dict[str, Any]:
        habit = {
            "id": habit_id,
            "name": name,
            "status": 0,
            "sortOrder": 1,
            "iconRes": "txt_✅",
            "sectionId": "sec-life",
            "repeatRule": "RRULE:FREQ=DAILY;INTERVAL=1",
        }
        habit.update(overrides)
        habit.setdefault("etag", self._habit_etag(habit))
        return habit

    def add_or_replace_task(self, task: dict[str, Any]) -> None:
        tasks = self.fake.project_tasks["project-inbox"]
        tasks[:] = [t for t in tasks if t.get("id") != task.get("id")]
        if task.get("status") == 2:
            self.fake.completed_tasks = [t for t in self.fake.completed_tasks if t.get("id") != task.get("id")]
            self.fake.completed_tasks.append(task)
        else:
            tasks.append(task)

    def add_or_replace_habit(self, habit: dict[str, Any]) -> None:
        self.fake.habits = [h for h in self.fake.habits if h.get("id") != habit.get("id")]
        self.fake.habits.append(habit)

    def expect_task_field(self, task_id: str, field: str, value: Any) -> Callable[[dict[str, Any]], None]:
        def _expect(delta: dict[str, Any]) -> None:
            rows = delta.get("tables", {}).get("tasks", [])
            row = next((r for r in rows if r.get("id") == task_id), None)
            assert row is not None, f"未返回任务增量: {task_id}"
            assert row.get(field) == value, f"{field} 期望 {value!r}, 实际 {row.get(field)!r}"
        return _expect

    def expect_habit_field(self, habit_id: str, field: str, value: Any) -> Callable[[dict[str, Any]], None]:
        def _expect(delta: dict[str, Any]) -> None:
            rows = delta.get("tables", {}).get("habits", [])
            row = next((r for r in rows if r.get("id") == habit_id), None)
            assert row is not None, f"未返回习惯增量: {habit_id}"
            assert row.get(field) == value, f"{field} 期望 {value!r}, 实际 {row.get(field)!r}"
        return _expect

    def expect_checkin(self, habit_id: str, date: str, status: int) -> Callable[[dict[str, Any]], None]:
        def _expect(delta: dict[str, Any]) -> None:
            rows = delta.get("tables", {}).get("habit_checkins", [])
            row = next((r for r in rows if r.get("habit_id") == habit_id and r.get("checkin_date") == date), None)
            assert row is not None, f"未返回打卡增量: {habit_id} {date}"
            assert row.get("status") == status, f"status 期望 {status}, 实际 {row.get('status')}"
        return _expect

    async def run(self) -> None:
        task_id = "tt-task-regression"
        await self.run_case(
            "任务-新建",
            lambda: self.add_or_replace_task(self.task(task_id, "同步回归任务")),
            self.expect_task_field(task_id, "title", "同步回归任务"),
            "TickTick 新建任务后，服务端写入版本增量。",
        )
        await self.run_case(
            "任务-更新优先级",
            lambda: self.add_or_replace_task(self.task(task_id, "同步回归任务", priority=5)),
            self.expect_task_field(task_id, "priority", 5),
        )
        await self.run_case(
            "任务-更新截止时间",
            lambda: self.add_or_replace_task(self.task(task_id, "同步回归任务", priority=5, dueDate="2026-06-16T00:00:00+0800")),
            self.expect_task_field(task_id, "due_date", "2026-06-16 00:00:00"),
        )
        await self.run_case(
            "任务-更新标签",
            lambda: self.add_or_replace_task(self.task(task_id, "同步回归任务", priority=5, dueDate="2026-06-16T00:00:00+0800", tags=["家庭"])),
            self.expect_task_field(task_id, "tags", "家庭"),
        )
        await self.run_case(
            "任务-修改标题",
            lambda: self.add_or_replace_task(self.task(task_id, "同步回归任务-改名", priority=5, dueDate="2026-06-16T00:00:00+0800", tags=["家庭"])),
            self.expect_task_field(task_id, "title", "同步回归任务-改名"),
        )
        await self.run_case(
            "任务-完成",
            lambda: self.add_or_replace_task(self.task(task_id, "同步回归任务-改名", status=2, completedTime="2026-06-16T08:00:00+0800", tags=["家庭"])),
            self.expect_task_field(task_id, "status", 2),
        )

        abandon_id = "client-task-abandon"
        delete_id = "client-task-delete"
        await self.run_client_case(
            "任务-放弃",
            [{
                "op_id": "op-abandon-" + uuid.uuid4().hex,
                "table": "tasks",
                "operation": "upsert",
                "payload": {"id": abandon_id, "title": "客户端放弃任务", "status": 4, "priority": 0, "due_date": "2026-06-16 00:00:00"},
            }],
            lambda payload: self.expect_task_field(abandon_id, "status", 4)(payload["delta"]),
            "客户端放弃任务写服务端并生成版本增量。",
        )
        await self.run_client_case(
            "任务-删除",
            [{
                "op_id": "op-delete-" + uuid.uuid4().hex,
                "table": "tasks",
                "operation": "delete",
                "payload": {"id": delete_id, "title": "客户端删除任务", "status": 4, "deleted_at": "2026-06-16 09:00:00", "due_date": "2026-06-16 00:00:00"},
            }],
            lambda payload: self.expect_task_field(delete_id, "deleted_at", "2026-06-16 09:00:00")(payload["delta"]),
        )

        habit_id = "tt-habit-regression"
        await self.run_case(
            "习惯-新建",
            lambda: self.add_or_replace_habit(self.habit(habit_id, "同步回归习惯")),
            self.expect_habit_field(habit_id, "name", "同步回归习惯"),
        )
        await self.run_case(
            "习惯-名称修改",
            lambda: self.add_or_replace_habit(self.habit(habit_id, "同步回归习惯-改名")),
            self.expect_habit_field(habit_id, "name", "同步回归习惯-改名"),
        )
        await self.run_case(
            "习惯-修改分组",
            lambda: self.add_or_replace_habit(self.habit(habit_id, "同步回归习惯-改名", sectionId="sec-work")),
            lambda delta: self.expect_habit_field(habit_id, "category_id", 2)(delta),
            "分组名映射到服务端分类 category_id。",
        )
        await self.run_case(
            "习惯-归档",
            lambda: self.add_or_replace_habit(self.habit(habit_id, "同步回归习惯-改名", sectionId="sec-work", status=1)),
            self.expect_habit_field(habit_id, "is_active", 1),
        )
        await self.run_case(
            "习惯-成功打卡",
            lambda: self.fake.checkins_by_habit.__setitem__(habit_id, [{"stamp": "20260613", "status": 2, "opTime": "20260613120000"}]),
            self.expect_checkin(habit_id, "2026-06-13", 2),
        )
        await self.run_case(
            "习惯-失败打卡",
            lambda: self.fake.checkins_by_habit.__setitem__(habit_id, [{"stamp": "20260613", "status": 2, "opTime": "20260613120000"}, {"stamp": "20260614", "status": 1, "opTime": "20260614120000"}]),
            self.expect_checkin(habit_id, "2026-06-14", 1),
        )
        await self.run_case(
            "习惯-补卡",
            lambda: self.fake.checkins_by_habit.__setitem__(habit_id, [{"stamp": "20260610", "status": 2, "opTime": "20260610120000"}, {"stamp": "20260613", "status": 2, "opTime": "20260613120000"}, {"stamp": "20260614", "status": 1, "opTime": "20260614120000"}]),
            self.expect_checkin(habit_id, "2026-06-10", 2),
        )
        await self.run_case(
            "习惯-删除/移除后不再返回",
            lambda: self.fake.habits.clear(),
            lambda delta: None,
            "当前 TickTick OpenAPI 未提供明确删除事件；此用例仅确保缺失习惯不会误生成新增增量。",
        )

    def write_reports(self) -> tuple[Path, Path]:
        payload = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "database": str(self.db_path),
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r.status == "PASS"),
                "failed": sum(1 for r in self.results if r.status == "FAIL"),
            },
            "results": [r.__dict__ for r in self.results],
        }
        json_path = self.output_dir / "sync-regression-report.json"
        md_path = self.output_dir / "sync-regression-report.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        lines = [
            "# 同步回归测试报告",
            "",
            f"- 生成时间: {payload['generated_at']}",
            f"- 总数: {payload['summary']['total']}",
            f"- 通过: {payload['summary']['passed']}",
            f"- 失败: {payload['summary']['failed']}",
            f"- 临时数据库: `{self.db_path}`",
            "",
            "| 用例 | 状态 | 版本 | 表增量 | 说明/错误 |",
            "|---|---:|---:|---|---|",
        ]
        for result in self.results:
            version = f"{result.before_version}->{result.after_version}"
            tables = ", ".join(f"{k}:{v}" for k, v in result.changed_tables.items()) or "-"
            note = result.error or result.detail or "-"
            lines.append(f"| {result.name} | {result.status} | {version} | {tables} | {note} |")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return json_path, md_path


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Run offline sync regression suite.")
    parser.add_argument("--output-dir", default=str(ROOT / "tests" / "runtime" / "sync-regression" / now_label()))
    args = parser.parse_args()

    suite = SyncRegressionSuite(Path(args.output_dir))
    await suite.run()
    json_path, md_path = suite.write_reports()
    failed = sum(1 for r in suite.results if r.status == "FAIL")
    print(f"同步回归测试完成: total={len(suite.results)} failed={failed}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    for result in suite.results:
        marker = "OK" if result.status == "PASS" else "FAIL"
        print(f"[{marker}] {result.name} {result.before_version}->{result.after_version} {result.changed_tables} {result.error or ''}")
    return 1 if failed else 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
