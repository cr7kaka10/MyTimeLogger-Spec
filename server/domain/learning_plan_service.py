"""学习 Objective/KR/Task 的服务端事务命令。"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from typing import Callable

from .management_plan_service import ManagementPlanError, ManagementPlanService, now_text
from .learning_category_service import LearningCategoryError, LearningCategoryService
from .reward_config_service import RewardConfigService


class LearningPlanService:
    def __init__(self, connect: Callable[[], sqlite3.Connection], record_change: Callable | None = None):
        self.connect = connect
        self.record_change = record_change
        self.reward_configs = RewardConfigService()

    def _change(self, conn, user_id: int, table: str, record_id: str, operation: str, fields: dict | None = None):
        if self.record_change:
            self.record_change(conn, user_id, table, record_id, operation, fields or {"id": record_id})

    @staticmethod
    def _category(conn, user_id: int, category_id) -> int:
        try:
            return LearningCategoryService.validate_id(conn, user_id, category_id)
        except LearningCategoryError as exc:
            raise ManagementPlanError(exc.code, str(exc), status=422) from exc

    @staticmethod
    def _ensure_learning_keys(conn, user_id: int) -> None:
        sources = tuple(source for source in ManagementPlanService._EXTENDED_OBJECT_SOURCES if source[0].startswith("learning-"))
        ManagementPlanService._backfill_object_keys(conn, user_id, sources)

    def apply_tree(self, user_id: int, payload: dict) -> dict:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ManagementPlanError("invalid_learning_objective", "学习目标标题不能为空", status=422)
        krs = payload.get("krs") or []
        if not isinstance(krs, list):
            raise ManagementPlanError("invalid_learning_krs", "关键结果必须是数组", status=422)
        now = now_text()
        objective_id = str(payload.get("id") or uuid.uuid4())
        with closing(self.connect()) as conn:
            try:
                conn.execute(
                    """INSERT INTO server_learning_objectives
                    (id,user_id,title,status,duration,baseline,target_description,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (objective_id, user_id, title, int(payload.get("status") or 0), payload.get("duration"), payload.get("baseline"), payload.get("target_description"), now, now),
                )
                self._change(conn, user_id, "server_learning_objectives", objective_id, "upsert", {"id": objective_id})
                created_krs = []
                for kr in krs:
                    kr_title = str(kr.get("title") or "").strip()
                    if not kr_title:
                        raise ManagementPlanError("invalid_learning_kr", "关键结果标题不能为空", status=422)
                    kr_id = str(kr.get("id") or uuid.uuid4())
                    conn.execute(
                        "INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (kr_id, user_id, objective_id, kr_title, int(kr.get("target_value") or 100), int(kr.get("current_value") or 0), now, now),
                    )
                    self._change(conn, user_id, "server_learning_krs", kr_id, "upsert", {"id": kr_id})
                    task_ids = []
                    for task in kr.get("tasks") or []:
                        task_title = str(task.get("title") or "").strip()
                        if not task_title:
                            raise ManagementPlanError("invalid_learning_task", "学习任务标题不能为空", status=422)
                        task_id = str(task.get("id") or uuid.uuid4())
                        conn.execute(
                            """INSERT INTO server_learning_tasks
                            (id,user_id,kr_id,title,status,category_id,priority,reward,due_date,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                            (task_id, user_id, kr_id, task_title, int(task.get("status") or 0), self._category(conn, user_id, task.get("category_id")), int(task.get("priority") or 0), float(task.get("reward") or 0), task.get("due_date"), now, now),
                        )
                        self.reward_configs.ensure_item(conn, user_id, "learning", task_id, reward=task.get("reward"))
                        self._change(conn, user_id, "server_learning_tasks", task_id, "upsert", {"id": task_id})
                        task_ids.append(task_id)
                    created_krs.append({"id": kr_id, "task_ids": task_ids})
                self._ensure_learning_keys(conn, user_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"objective_id": objective_id, "krs": created_krs}

    def command(self, user_id: int, payload: dict) -> dict:
        """Execute one authenticated learning-domain command atomically."""
        action = str(payload.get("action") or "apply_tree").strip()
        if action in {"apply_tree", "import_full"}:
            return self.apply_tree(user_id, payload)
        now = now_text()
        with closing(self.connect()) as conn:
            try:
                if action == "create_objective":
                    title = str(payload.get("title") or "").strip()
                    if not title:
                        raise ManagementPlanError("invalid_learning_objective", "学习目标标题不能为空", status=422)
                    record_id = str(payload.get("id") or uuid.uuid4())
                    conn.execute(
                        "INSERT INTO server_learning_objectives(id,user_id,title,status,duration,baseline,target_description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (record_id, user_id, title, int(payload.get("status") or 0), payload.get("duration"), payload.get("baseline"), payload.get("target_description"), now, now),
                    )
                    self._change(conn, user_id, "server_learning_objectives", record_id, "upsert", {"id": record_id})
                    result = {"objective_id": record_id}
                elif action == "update_objective":
                    record_id = str(payload.get("id") or "")
                    if not conn.execute("SELECT 1 FROM server_learning_objectives WHERE id=? AND user_id=?", (record_id, user_id)).fetchone():
                        raise ManagementPlanError("learning_objective_not_found", "学习目标不存在", status=404)
                    allowed = {key: payload[key] for key in ("title", "duration", "baseline", "target_description", "status") if key in payload}
                    if "title" in allowed and not str(allowed["title"] or "").strip():
                        raise ManagementPlanError("invalid_learning_objective", "学习目标标题不能为空", status=422)
                    if not allowed:
                        return {"objective_id": record_id, "status": "unchanged"}
                    assignments = ", ".join(f"{key}=?" for key in allowed)
                    conn.execute(f"UPDATE server_learning_objectives SET {assignments}, updated_at=? WHERE id=? AND user_id=?", (*allowed.values(), now, record_id, user_id))
                    self._change(conn, user_id, "server_learning_objectives", record_id, "upsert", {"id": record_id, **allowed})
                    result = {"objective_id": record_id}
                elif action == "delete_objective":
                    record_id = str(payload.get("id") or "")
                    if not conn.execute("SELECT 1 FROM server_learning_objectives WHERE id=? AND user_id=?", (record_id, user_id)).fetchone():
                        raise ManagementPlanError("learning_objective_not_found", "学习目标不存在", status=404)
                    krs = conn.execute("SELECT id FROM server_learning_krs WHERE objective_id=? AND user_id=?", (record_id, user_id)).fetchall()
                    for kr in krs:
                        tasks = conn.execute("SELECT id FROM server_learning_tasks WHERE kr_id=? AND user_id=?", (kr[0], user_id)).fetchall()
                        for task in tasks:
                            conn.execute("DELETE FROM server_learning_tasks WHERE id=? AND user_id=?", (task[0], user_id))
                            self._change(conn, user_id, "server_learning_tasks", str(task[0]), "delete", {"id": task[0]})
                        conn.execute("DELETE FROM server_learning_krs WHERE id=? AND user_id=?", (kr[0], user_id))
                        self._change(conn, user_id, "server_learning_krs", str(kr[0]), "delete", {"id": kr[0]})
                    conn.execute("DELETE FROM server_learning_objectives WHERE id=? AND user_id=?", (record_id, user_id))
                    self._change(conn, user_id, "server_learning_objectives", record_id, "delete", {"id": record_id})
                    result = {"objective_id": record_id}
                elif action == "create_kr":
                    title = str(payload.get("title") or "").strip()
                    objective_id = str(payload.get("objective_id") or "")
                    if not title:
                        raise ManagementPlanError("invalid_learning_kr", "关键结果标题不能为空", status=422)
                    if not conn.execute("SELECT 1 FROM server_learning_objectives WHERE id=? AND user_id=?", (objective_id, user_id)).fetchone():
                        raise ManagementPlanError("learning_objective_not_found", "学习目标不存在", status=404)
                    record_id = str(payload.get("id") or uuid.uuid4())
                    conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (record_id, user_id, objective_id, title, int(payload.get("target_value") or 0), int(payload.get("current_value") or 0), now, now))
                    self._change(conn, user_id, "server_learning_krs", record_id, "upsert", {"id": record_id})
                    result = {"kr_id": record_id, "objective_id": objective_id}
                elif action == "create_task":
                    title = str(payload.get("title") or "").strip()
                    kr_id = str(payload.get("kr_id") or "")
                    if not title:
                        raise ManagementPlanError("invalid_learning_task", "学习任务标题不能为空", status=422)
                    if not conn.execute("SELECT 1 FROM server_learning_krs WHERE id=? AND user_id=?", (kr_id, user_id)).fetchone():
                        raise ManagementPlanError("learning_kr_not_found", "关键结果不存在", status=404)
                    record_id = str(payload.get("id") or uuid.uuid4())
                    category_id = self._category(conn, user_id, payload.get("category_id"))
                    conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,category_id,priority,reward,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (record_id, user_id, kr_id, title, int(payload.get("status") or 0), category_id, int(payload.get("priority") or 0), float(payload.get("reward") or 0), payload.get("due_date"), now, now))
                    self.reward_configs.ensure_item(conn, user_id, "learning", record_id, reward=payload.get("reward"))
                    conn.execute("UPDATE server_learning_krs SET target_value=target_value+1,updated_at=? WHERE id=? AND user_id=?", (now, kr_id, user_id))
                    self._change(conn, user_id, "server_learning_tasks", record_id, "upsert", {"id": record_id})
                    self._change(conn, user_id, "server_learning_krs", kr_id, "upsert", {"id": kr_id})
                    result = {"task_id": record_id, "kr_id": kr_id}
                elif action in {"toggle_task", "set_task_status", "delete_task"}:
                    task_id = str(payload.get("id") or "")
                    task = conn.execute("SELECT * FROM server_learning_tasks WHERE id=? AND user_id=?", (task_id, user_id)).fetchone()
                    if not task:
                        raise ManagementPlanError("learning_task_not_found", "学习任务不存在", status=404)
                    kr_id = str(task["kr_id"])
                    if action in {"toggle_task", "set_task_status"}:
                        current_status = int(task["status"] or 0)
                        if action == "set_task_status":
                            try:
                                next_status = int(payload.get("status"))
                            except (TypeError, ValueError):
                                next_status = -1
                            if next_status not in {0, 2}:
                                raise ManagementPlanError("invalid_learning_task_status", "学习任务状态无效", status=422)
                        else:
                            next_status = 0 if current_status == 2 else 2
                        if next_status != current_status:
                            delta = 1 if next_status == 2 else -1
                            conn.execute("UPDATE server_learning_tasks SET status=?,updated_at=? WHERE id=? AND user_id=?", (next_status, now, task_id, user_id))
                            conn.execute("UPDATE server_learning_krs SET current_value=MAX(current_value+?,0),updated_at=? WHERE id=? AND user_id=?", (delta, now, kr_id, user_id))
                            self._change(conn, user_id, "server_learning_tasks", task_id, "upsert", {"id": task_id, "status": next_status})
                            self._change(conn, user_id, "server_learning_krs", kr_id, "upsert", {"id": kr_id})
                        result = {"task_id": task_id, "status": next_status}
                    else:
                        conn.execute("DELETE FROM server_learning_tasks WHERE id=? AND user_id=?", (task_id, user_id))
                        delta = -1 if int(task["status"] or 0) == 2 else 0
                        conn.execute("UPDATE server_learning_krs SET target_value=MAX(target_value-1,0),current_value=MAX(current_value+?,0),updated_at=? WHERE id=? AND user_id=?", (delta, now, kr_id, user_id))
                        self._change(conn, user_id, "server_learning_tasks", task_id, "delete", {"id": task_id})
                        self._change(conn, user_id, "server_learning_krs", kr_id, "upsert", {"id": kr_id})
                        result = {"task_id": task_id, "kr_id": kr_id}
                elif action == "import_krs":
                    objective_id = str(payload.get("objective_id") or "")
                    if not conn.execute("SELECT 1 FROM server_learning_objectives WHERE id=? AND user_id=?", (objective_id, user_id)).fetchone():
                        raise ManagementPlanError("learning_objective_not_found", "学习目标不存在", status=404)
                    created = []
                    for kr in payload.get("krs") or []:
                        title = str(kr.get("title") or "").strip()
                        if not title:
                            raise ManagementPlanError("invalid_learning_kr", "关键结果标题不能为空", status=422)
                        kr_id = str(kr.get("id") or uuid.uuid4())
                        conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (kr_id, user_id, objective_id, title, int(kr.get("target_value") or len(kr.get("tasks") or [])), int(kr.get("current_value") or 0), now, now))
                        self._change(conn, user_id, "server_learning_krs", kr_id, "upsert", {"id": kr_id})
                        task_ids = []
                        for task in kr.get("tasks") or []:
                            title = str(task.get("title") or "").strip()
                            if not title:
                                raise ManagementPlanError("invalid_learning_task", "学习任务标题不能为空", status=422)
                            task_id = str(task.get("id") or uuid.uuid4())
                            category_id = self._category(conn, user_id, task.get("category_id"))
                            conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,category_id,priority,reward,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (task_id, user_id, kr_id, title, 0, category_id, int(task.get("priority") or 0), float(task.get("reward") or 0), task.get("due_date"), now, now))
                            self.reward_configs.ensure_item(conn, user_id, "learning", task_id, reward=task.get("reward"))
                            self._change(conn, user_id, "server_learning_tasks", task_id, "upsert", {"id": task_id})
                            task_ids.append(task_id)
                        created.append({"id": kr_id, "task_ids": task_ids})
                    result = {"objective_id": objective_id, "krs": created}
                else:
                    raise ManagementPlanError("unsupported_learning_command", "学习命令不受支持", status=422)
                self._ensure_learning_keys(conn, user_id)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
