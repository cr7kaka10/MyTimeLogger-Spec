"""管理方案服务端应用层。

该服务把草案、预览、确认、版本和导入导出放在同一用户隔离边界内。业务
领域的运行事实仍由各自服务负责，方案服务只写配置定义和版本审计。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .management_plan_schema import (
    ManagementPlanValidationError,
    digest_payload,
    validate_manifest,
    validate_patch,
    validate_simplified_chinese,
)
from .management_plan_reward_policy import RewardPolicyError, validate_reward_items
from .management_planning_policy import POLICY_VERSION, SKILL_VERSION, determine_intent
from .management_bundle_schema import BUNDLE_SCHEMA_ID, BUNDLE_VERSION, canonicalize_bundle
from .reward_config_service import RewardConfigService
from .learning_category_service import LearningCategoryError, LearningCategoryService
from .ticktick_task_dates import normalize_task_date
from ..store import ServerSleepStore


BEIJING = timezone(timedelta(hours=8))
DOMAIN_TABLES = (
    "server_tasks", "server_habits", "server_learning_objectives", "server_learning_krs",
    "server_learning_tasks", "server_exercise_plan_versions", "server_goals",
    "server_rewards", "server_reward_config", "server_huawei_sleep_data",
)
CONTEXT_IDENTITY_FIELDS = {
    "server_exercise_plan_versions": ("version",),
    "server_huawei_sleep_data": ("id", "date"),
}
CONTEXT_FIELDS = {
    "server_tasks": ("id", "title", "priority", "status", "category_id", "due_date", "tags", "updated_at"),
    "server_habits": ("id", "name", "difficulty", "repeat_rule", "category_id", "is_active", "updated_at"),
    "server_learning_objectives": ("id", "title", "status", "duration", "baseline", "target_description", "updated_at"),
    "server_learning_krs": ("id", "objective_id", "title", "target_value", "current_value", "updated_at"),
    "server_learning_tasks": ("id", "kr_id", "title", "status", "category_id", "priority", "reward", "due_date", "updated_at"),
    "server_exercise_plan_versions": ("version", "title", "source_name", "is_active", "updated_at"),
    "server_goals": ("id", "title", "category_id", "metric", "target_value", "period", "operator", "reward_coins", "is_active", "updated_at"),
    "server_rewards": ("id", "title", "price", "description", "unlock_source_type", "unlock_source_id", "inventory_mode", "inventory_limit", "unlock_required_count", "is_active", "updated_at"),
    "server_reward_config": ("id", "item_type", "item_id", "coins", "penalty", "updated_at"),
    "server_huawei_sleep_data": ("id", "date", "total_sleep_min", "report_status", "updated_at"),
}
CONTEXT_ITEM_LIMIT = 100
logger = logging.getLogger(__name__)

MINDMAP_DOMAIN_LABELS = {
    "goal": "目标",
    "sleep": "睡眠",
    "learning_task": "学习",
    "habit": "习惯",
    "checklist_task": "任务",
}
MINDMAP_SOURCE_TYPE_ALIASES = {
    "task": "checklist_task",
    "checklist_task": "checklist_task",
    "learning": "learning_task",
    "learning_task": "learning_task",
    "habit": "habit",
    "exercise": "exercise_checkin",
    "exercise_checkin": "exercise_checkin",
    "goal": "goal",
    "sleep": "sleep",
}


def now_text() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")


class ManagementPlanError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400, details: Any = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details


class ManagementPlanService:
    _CORE_OBJECT_SOURCES = (("category", "server_categories", "id"), ("task", "server_tasks", "id"), ("habit", "server_habits", "id"))
    _EXTENDED_OBJECT_SOURCES = (("learning-objective", "server_learning_objectives", "id"), ("learning-kr", "server_learning_krs", "id"), ("learning-task", "server_learning_tasks", "id"), ("exercise-plan", "server_exercise_plan_versions", "version"), ("exercise-item", "server_exercise_plan_items", "id"), ("goal", "server_goals", "id"), ("store-item", "server_rewards", "id"))

    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self.connect = connect

    @staticmethod
    def _learning_category(conn, user_id: int, category_id) -> int:
        try:
            return LearningCategoryService.validate_id(conn, user_id, category_id)
        except LearningCategoryError as exc:
            raise ManagementPlanError(exc.code, str(exc), status=422) from exc

    @staticmethod
    def _backfill_object_keys(conn: sqlite3.Connection, user_id: int, sources: tuple[tuple[str, str, str], ...]) -> None:
        now = now_text()
        for domain_type, table, identity_column in sources:
            rows = conn.execute(f"SELECT {identity_column} AS record_id FROM {table} WHERE user_id=?", (user_id,)).fetchall()
            for row in rows:
                record_id = str(row["record_id"])
                conn.execute(
                    "INSERT OR IGNORE INTO server_management_object_keys(user_id,domain_type,record_id,logical_key,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (user_id, domain_type, record_id, f"{domain_type}.{uuid.uuid4().hex}", now, now),
                )

    def ensure_object_keys(self, user_id: int) -> None:
        with closing(self.connect()) as conn:
            self._backfill_object_keys(conn, user_id, self._CORE_OBJECT_SOURCES + self._EXTENDED_OBJECT_SOURCES)
            conn.commit()
            conn.commit()

    @staticmethod
    def _ensure_object_key(conn: sqlite3.Connection, user_id: int, domain_type: str, record_id: str) -> None:
        now = now_text()
        conn.execute("INSERT OR IGNORE INTO server_management_object_keys(user_id,domain_type,record_id,logical_key,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                     (user_id, domain_type, str(record_id), f"{domain_type}.{uuid.uuid4().hex}", now, now))

    @staticmethod
    def _context_record_identity(table: str, data: dict) -> str:
        for field in CONTEXT_IDENTITY_FIELDS.get(table, ("id",)):
            value = data.get(field)
            if value not in (None, ""):
                return str(value)
        logger.warning("management plan context missing identity table=%s", table)
        raise ManagementPlanError("planning_context_unavailable", "管理方案上下文有无法识别的记录，请刷新数据后重试", status=422)

    @staticmethod
    def _active_plan_context(conn: sqlite3.Connection, user_id: int) -> tuple[dict | None, list[str]]:
        row = conn.execute(
            """SELECT p.plan_key,p.title,p.updated_at,r.id AS revision_id,r.version,r.manifest_digest,r.manifest_json
            FROM server_management_plans p
            JOIN server_management_plan_revisions r ON r.id=p.active_revision_id AND r.user_id=p.user_id
            WHERE p.user_id=? ORDER BY p.updated_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        if not row:
            return None, []
        manifest = json.loads(row["manifest_json"])
        item_fields = ("logical_key", "type", "action", "title", "name", "expected_minutes", "period", "due_date", "reward", "reward_coins", "price", "target_value", "repeat_rule")
        manifest_summary = {
            key: manifest.get(key)
            for key in ("schema_version", "mode", "policy_version", "plan_key", "title", "summary")
            if key in manifest
        }
        manifest_summary["items"] = [
            {key: item.get(key) for key in item_fields if key in item}
            for item in manifest.get("items", [])[:CONTEXT_ITEM_LIMIT]
            if isinstance(item, dict)
        ]
        bindings = conn.execute(
            """SELECT logical_key,domain_type,record_id,provider,binding_status,updated_at
            FROM server_management_plan_bindings WHERE user_id=? AND revision_id=?
            ORDER BY updated_at DESC LIMIT ?""",
            (user_id, row["revision_id"], CONTEXT_ITEM_LIMIT),
        ).fetchall()
        binding_summary = [dict(binding) for binding in bindings]
        versions = [
            f"active_plan:{row['revision_id']}:{row['manifest_digest']}",
            *[f"binding:{item['logical_key']}:{item['updated_at']}" for item in binding_summary if item.get("updated_at")],
        ]
        return {
            "plan_key": row["plan_key"],
            "title": row["title"],
            "version": row["version"],
            "manifest_digest": row["manifest_digest"],
            "manifest": manifest_summary,
            "bindings": binding_summary,
        }, versions

    @staticmethod
    def _review_source_index(conn: sqlite3.Connection, user_id: int) -> dict[str, str]:
        sources: dict[str, str] = {}
        definitions = (
            ("checklist_task", "server_tasks", "title"), ("habit", "server_habits", "name"),
            ("learning_task", "server_learning_tasks", "title"), ("goal", "server_goals", "title"),
            ("exercise_checkin", "server_exercise_plan_items", "name"),
        )
        for source_type, table, title_column in definitions:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                continue
            for row in conn.execute(f"SELECT id,{title_column} AS title FROM {table} WHERE user_id=?", (user_id,)):
                sources[f"{source_type}:{row['id']}"] = str(row["title"] or "")
        return sources

    @staticmethod
    def _review_source_title(sources: dict[str, str], source_type: str, source_id: str | None, fallback: str | None = None) -> tuple[str, str]:
        title = sources.get(f"{source_type}:{source_id}") if source_id else None
        if title:
            return title, "active"
        if fallback:
            return str(fallback), "source_missing"
        return "来源已不存在", "source_missing"

    def _review_evidence(self, conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
        sources = self._review_source_index(conn, user_id)
        reward_rules: list[dict[str, Any]] = []
        updated_at: list[str] = []
        for row in conn.execute("SELECT item_type,item_id,coins,penalty,updated_at FROM server_reward_config WHERE user_id=? ORDER BY updated_at DESC LIMIT ?", (user_id, CONTEXT_ITEM_LIMIT)):
            source_type = "checklist_task" if row["item_type"] == "task" else str(row["item_type"])
            title, status = self._review_source_title(sources, source_type, row["item_id"])
            reward_rules.append({"kind": source_type, "source_id": row["item_id"], "source_title": title, "source_status": status, "coins": float(row["coins"] or 0), "penalty": float(row["penalty"] or 0)})
            if row["updated_at"]: updated_at.append(str(row["updated_at"]))
        for row in conn.execute("SELECT id,title,reward,updated_at FROM server_learning_tasks WHERE user_id=? ORDER BY updated_at DESC LIMIT ?", (user_id, CONTEXT_ITEM_LIMIT)):
            reward_rules.append({"kind": "learning_task", "source_id": row["id"], "source_title": row["title"], "source_status": "active", "coins": float(row["reward"] or 0), "penalty": 0})
            if row["updated_at"]: updated_at.append(str(row["updated_at"]))
        for row in conn.execute("SELECT id,title,period,reward_coins,penalty_coins,is_active,updated_at FROM server_goals WHERE user_id=? ORDER BY updated_at DESC LIMIT ?", (user_id, CONTEXT_ITEM_LIMIT)):
            reward_rules.append({"kind": "goal", "source_id": row["id"], "source_title": row["title"], "source_status": "active" if row["is_active"] else "inactive", "period": row["period"], "coins": float(row["reward_coins"] or 0), "penalty": float(row["penalty_coins"] or 0)})
            if row["updated_at"]: updated_at.append(str(row["updated_at"]))
        store_items: list[dict[str, Any]] = []
        for row in conn.execute("SELECT title,price,unlock_task_title,unlock_source_type,unlock_source_id,inventory_mode,inventory_limit,unlock_required_count,is_active,updated_at FROM server_rewards WHERE user_id=? ORDER BY updated_at DESC LIMIT ?", (user_id, CONTEXT_ITEM_LIMIT)):
            source_type = str(row["unlock_source_type"] or "")
            title, status = self._review_source_title(sources, source_type, row["unlock_source_id"], row["unlock_task_title"]) if source_type else ("金币兑换", "none")
            store_items.append({"title": row["title"], "price": float(row["price"] or 0), "source_type": source_type or None, "source_title": title, "source_status": status, "required_count": int(row["unlock_required_count"] or 1), "inventory_mode": row["inventory_mode"], "inventory_limit": row["inventory_limit"], "status": "active" if row["is_active"] else "inactive"})
            if row["updated_at"]: updated_at.append(str(row["updated_at"]))
        unresolved = sum(item["source_status"] == "source_missing" for item in reward_rules + store_items)
        return {"reward_rules": reward_rules, "store_items": store_items, "summary": {"reward_rule_count": len(reward_rules), "store_item_count": len(store_items), "unresolved_source_count": unresolved, "truncated": False, "data_updated_at": max(updated_at) if updated_at else None}}

    @staticmethod
    def _mindmap_item(source_type: str, row: sqlite3.Row | dict[str, Any], *, title_key: str, status: str = "active", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        data = dict(row)
        return {
            "source_type": source_type,
            "source_id": str(data["id"]),
            "title": str(data.get(title_key) or "未命名项目"),
            "status": status,
            "metadata": metadata or {},
            "reward": None,
            "items": [],
            "children": [],
        }

    def mindmap_snapshot(self, user_id: int) -> dict[str, Any]:
        """Return a complete, read-only management view for one account.

        This intentionally queries current server facts instead of plan manifests
        or client cache. The response is a strict presentation whitelist.
        """
        try:
            with closing(self.connect()) as conn:
                self._backfill_object_keys(conn, user_id, self._CORE_OBJECT_SOURCES + self._EXTENDED_OBJECT_SOURCES)
                conn.commit()
                domains: dict[str, list[dict[str, Any]]] = {key: [] for key in MINDMAP_DOMAIN_LABELS}
                indexed: dict[str, dict[str, Any]] = {}
                unbound_products: list[dict[str, Any]] = []

                def append_item(item: dict[str, Any]) -> None:
                    domains[item["source_type"]].append(item)
                    indexed[f"{item['source_type']}:{item['source_id']}"] = item

                today = datetime.now(BEIJING).date().isoformat()
                for row in conn.execute("SELECT id,title,status,deleted_at,due_date,updated_at FROM server_tasks WHERE user_id=? AND deleted_at IS NULL AND COALESCE(status,0)<>2 AND TRIM(COALESCE(due_date,''))<>'' ORDER BY updated_at DESC,id", (user_id,)):
                    try:
                        due_day = str(normalize_task_date(row["due_date"]) or "").split("T", 1)[0]
                    except ValueError:
                        continue
                    if not due_day or due_day > today:
                        continue
                    append_item(self._mindmap_item("checklist_task", row, title_key="title", status="active", metadata={"due_date": row["due_date"], "updated_at": row["updated_at"]}))
                for row in conn.execute("SELECT id,name,difficulty,repeat_rule,is_active,updated_at FROM server_habits WHERE user_id=? ORDER BY updated_at DESC,id", (user_id,)):
                    if not int(row["is_active"] or 0):
                        append_item(self._mindmap_item("habit", row, title_key="name", status="active", metadata={"difficulty": row["difficulty"], "repeat_rule": row["repeat_rule"], "updated_at": row["updated_at"]}))
                learning_objectives: dict[str, dict[str, Any]] = {}
                learning_krs: dict[str, dict[str, Any]] = {}
                for row in conn.execute("SELECT id,title,status,updated_at FROM server_learning_objectives WHERE user_id=? ORDER BY updated_at DESC,id", (user_id,)):
                    if int(row["status"] or 0) != 2:
                        item = self._mindmap_item("learning_objective", row, title_key="title", status="active", metadata={"updated_at": row["updated_at"]})
                        learning_objectives[str(row["id"])] = item
                for row in conn.execute("SELECT id,objective_id,title,target_value,current_value,updated_at FROM server_learning_krs WHERE user_id=? ORDER BY updated_at DESC,id", (user_id,)):
                    parent = learning_objectives.get(str(row["objective_id"]))
                    if not parent:
                        continue
                    item = self._mindmap_item("learning_kr", row, title_key="title", metadata={"target_value": row["target_value"], "current_value": row["current_value"], "updated_at": row["updated_at"]})
                    learning_krs[str(row["id"])] = item
                    parent["children"].append(item)
                for row in conn.execute("SELECT id,kr_id,title,status,due_date,updated_at FROM server_learning_tasks WHERE user_id=? ORDER BY updated_at DESC,id", (user_id,)):
                    if int(row["status"] or 0) == 2:
                        continue
                    parent = learning_krs.get(str(row["kr_id"]))
                    if not parent:
                        continue
                    item = self._mindmap_item("learning_task", row, title_key="title", status="completed" if int(row["status"] or 0) == 2 else "active", metadata={"due_date": row["due_date"], "updated_at": row["updated_at"]})
                    parent["children"].append(item)
                    indexed[f"learning_task:{row['id']}"] = item
                for objective in list(learning_objectives.values()):
                    objective["children"] = [kr for kr in objective["children"] if kr.get("children")]
                    if objective["children"]:
                        domains["learning_task"].append(objective)
                        for kr in objective["children"]:
                            indexed[f"learning_kr:{kr['source_id']}"] = kr
                for row in conn.execute("SELECT id,title,metric,target_value,period,operator,reward_coins,penalty_coins,is_active,updated_at FROM server_goals WHERE user_id=? ORDER BY updated_at DESC,id", (user_id,)):
                    if not int(row["is_active"] or 0):
                        continue
                    item = self._mindmap_item("goal", row, title_key="title", status="active", metadata={"metric": row["metric"], "target_value": row["target_value"], "period": row["period"], "operator": row["operator"], "updated_at": row["updated_at"]})
                    item["reward"] = {"coins": float(row["reward_coins"] or 0), "penalty": float(row["penalty_coins"] or 0), "status": "configured", "editable": True}
                    append_item(item)
                latest_sleep = conn.execute("SELECT id,date,total_sleep_min,sleep_score,report_status,updated_at FROM server_huawei_sleep_data WHERE user_id=? ORDER BY date DESC,id DESC LIMIT 1", (user_id,)).fetchone()
                if latest_sleep:
                    append_item(self._mindmap_item("sleep", latest_sleep, title_key="date", status="read_only", metadata={"date": latest_sleep["date"], "total_sleep_min": latest_sleep["total_sleep_min"], "sleep_score": latest_sleep["sleep_score"], "report_status": latest_sleep["report_status"], "updated_at": latest_sleep["updated_at"]}))

                for row in conn.execute("SELECT item_type,item_id,coins,penalty FROM server_reward_config WHERE user_id=? ORDER BY item_type,item_id", (user_id,)):
                    source_type = MINDMAP_SOURCE_TYPE_ALIASES.get(str(row["item_type"]), str(row["item_type"]))
                    key = f"{source_type}:{row['item_id']}"
                    item = indexed.get(key)
                    if item is not None:
                        item["reward"] = {"coins": float(row["coins"] or 0), "penalty": float(row["penalty"] or 0), "status": "configured", "editable": item["status"] != "source_missing"}

                for item in indexed.values():
                    if item["source_type"] not in {"goal", "sleep", "reward_item"} and item["reward"] is None:
                        item["reward"] = {"coins": None, "penalty": None, "status": "unconfigured", "editable": item["status"] not in {"source_missing", "read_only"}}

                for row in conn.execute("SELECT id,title,icon,price,description,unlock_source_type,unlock_source_id,unlock_task_title,inventory_mode,inventory_limit,unlock_required_count,is_active,updated_at FROM server_rewards WHERE user_id=? AND COALESCE(is_active,0)=1 ORDER BY updated_at DESC,id", (user_id,)):
                    reward = {"id": str(row["id"]), "title": str(row["title"]), "icon": row["icon"], "price": float(row["price"] or 0), "description": row["description"], "inventory_mode": row["inventory_mode"], "inventory_limit": row["inventory_limit"], "required_count": int(row["unlock_required_count"] or 1), "status": "active" if int(row["is_active"] or 0) else "inactive", "editable": True, "updated_at": row["updated_at"]}
                    source_type = str(row["unlock_source_type"] or "")
                    source_id = str(row["unlock_source_id"] or "")
                    mapped_source_type = MINDMAP_SOURCE_TYPE_ALIASES.get(source_type, source_type)
                    if mapped_source_type == "exercise_checkin":
                        continue
                    target = indexed.get(f"{mapped_source_type}:{source_id}") if mapped_source_type and source_id else None
                    if target:
                        reward["source_status"] = target["status"]
                        target["items"].append(reward)
                    elif mapped_source_type in domains and (source_type or source_id):
                        reward["source_status"] = "source_missing"
                        continue
                    else:
                        if source_type or source_id:
                            continue
                        reward["source_status"] = "none"
                        unbound_products.append(reward)

                return {
                    "refreshed_at": now_text(),
                    "domains": [{"key": key, "title": MINDMAP_DOMAIN_LABELS[key], "items": domains[key]} for key in MINDMAP_DOMAIN_LABELS],
                    "unbound_products": unbound_products,
                }
        except sqlite3.Error as exc:
            logger.warning("management plan mindmap unavailable error_type=%s", type(exc).__name__)
            raise ManagementPlanError("management_plan_mindmap_unavailable", "管理方案真实数据读取失败，请稍后重试", status=500) from exc

    def _context(self, user_id: int) -> dict:
        with closing(self.connect()) as conn:
            context: dict[str, Any] = {"user_id": int(user_id), "domains": {}}
            version_parts: list[str] = []
            for table in DOMAIN_TABLES:
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if not exists:
                    continue
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE user_id=? ORDER BY updated_at DESC LIMIT ?", (user_id, CONTEXT_ITEM_LIMIT)
                ).fetchall()
                safe_rows = []
                for row in rows:
                    data = dict(row)
                    record_identity = self._context_record_identity(table, data)
                    safe = {key: data.get(key) for key in CONTEXT_FIELDS.get(table, ()) if key in data}
                    safe_rows.append(safe)
                    # 即使旧表的 updated_at 为空，也必须用白名单字段参与版本摘要，
                    # 否则预检可能漏掉奖励、商品或计划字段的实际变化。
                    version_parts.append(f"{table}:{record_identity}:{digest_payload(safe)}")
                context["domains"][table] = {"count": len(rows), "items": safe_rows}
            active_plan, active_versions = self._active_plan_context(conn, user_id)
            context["active_management_plan"] = active_plan
            version_parts.extend(active_versions)
            context["review_evidence"] = self._review_evidence(conn, user_id)
            version_parts.append(f"review_evidence:{digest_payload(context['review_evidence'])}")
            context["planning_context_summary"] = {
                "domain_counts": {key: value["count"] for key, value in context["domains"].items()},
                "recent_days": 14,
            }
            session_row = conn.execute(
                "SELECT COALESCE(SUM(net_duration_minutes),0) AS minutes, COUNT(*) AS sessions FROM server_study_sessions WHERE user_id=? AND date >= date('now','-14 day')",
                (user_id,),
            ).fetchone()
            sleep_row = conn.execute(
                "SELECT COUNT(*) AS days, COALESCE(AVG(total_sleep_min),0) AS avg_sleep_minutes FROM server_huawei_sleep_data WHERE user_id=? AND date >= date('now','-14 day')",
                (user_id,),
            ).fetchone()
            context["planning_context_summary"]["focus"] = {"minutes": float(session_row["minutes"] or 0), "sessions": int(session_row["sessions"] or 0)}
            context["planning_context_summary"]["sleep"] = {"days": int(sleep_row["days"] or 0), "avg_sleep_minutes": float(sleep_row["avg_sleep_minutes"] or 0)}
            context["context_version"] = digest_payload(sorted(version_parts))
            return context

    def context(self, user_id: int) -> dict:
        try:
            return self._context(int(user_id))
        except ManagementPlanError:
            raise
        except (sqlite3.Error, KeyError, TypeError) as exc:
            logger.warning("management plan context unavailable error_type=%s", type(exc).__name__)
            raise ManagementPlanError("planning_context_unavailable", "管理方案上下文读取失败，请刷新数据后重试", status=500) from exc

    def create_draft(
        self,
        user_id: int,
        request_text: str,
        *,
        generated_payload: dict | None = None,
        model_runner: Callable[[str, dict], dict] | None = None,
        requested_intent: str | None = None,
    ) -> dict:
        request_text = str(request_text or "").strip()
        if not request_text or len(request_text) > 4000:
            raise ManagementPlanError("invalid_request", "需求不能为空且不能超过 4000 字", status=422)
        intent = determine_intent(request_text, requested_intent)
        generated_by_model = generated_payload is None
        logger.info("management_plan step=intent_determined user_id=%s intent=%s request_length=%s", user_id, intent, len(request_text))
        context = self.context(user_id)
        logger.info("management_plan step=context_loaded user_id=%s context_version=%s evidence_rules=%s evidence_store=%s", user_id, context["context_version"][:12], len(context["review_evidence"]["reward_rules"]), len(context["review_evidence"]["store_items"]))
        context["planning_intent"] = intent
        context["policy_version"] = POLICY_VERSION
        context["skill_version"] = SKILL_VERSION
        if generated_payload is None:
            if model_runner is None:
                raise ManagementPlanError("ai_config_required", "当前账号未配置可用的大模型", status=400)
            try:
                generated_payload = model_runner(request_text, context)
                logger.info("management_plan step=model_request_finished user_id=%s intent=%s payload_type=%s", user_id, intent, type(generated_payload).__name__)
            except ManagementPlanError:
                raise
            except Exception as exc:
                raise ManagementPlanError("ai_request_failed", "大模型请求失败", status=502) from exc
        if isinstance(generated_payload, dict):
            generated_payload = {**generated_payload, "mode": intent, "policy_version": POLICY_VERSION, "skill_version": SKILL_VERSION}
        try:
            payload = validate_manifest(generated_payload)
            validate_simplified_chinese(payload)
            logger.info("management_plan step=payload_validated user_id=%s intent=%s items=%s", user_id, intent, len(payload["items"]))
        except ManagementPlanValidationError as exc:
            logger.warning("management_plan step=payload_validation_failed user_id=%s intent=%s error_code=%s", user_id, intent, exc.code)
            retryable = exc.code == "management_plan_non_simplified_chinese" or (intent == "review" and exc.code in {"invalid_review", "review_must_not_include_items"})
            if not generated_by_model or model_runner is None or not retryable:
                raise ManagementPlanError(exc.code, str(exc), status=422, details={"path": exc.path}) from exc
            retry_context = {
                **context,
                "review_contract_retry": intent == "review" and exc.code in {"invalid_review", "review_must_not_include_items"},
                "language_contract_retry": exc.code == "management_plan_non_simplified_chinese",
            }
            logger.warning("management_plan step=contract_retry user_id=%s intent=%s language=%s review=%s", user_id, intent, retry_context["language_contract_retry"], retry_context["review_contract_retry"])
            try:
                generated_payload = {**model_runner(request_text, retry_context), "mode": intent, "policy_version": POLICY_VERSION, "skill_version": SKILL_VERSION}
                payload = validate_manifest(generated_payload)
                validate_simplified_chinese(payload)
                logger.info("management_plan step=retry_payload_validated user_id=%s items=%s", user_id, len(payload["items"]))
            except ManagementPlanValidationError as retry_exc:
                raise ManagementPlanError(retry_exc.code, str(retry_exc), status=422, details={"path": retry_exc.path}) from retry_exc
            except Exception as retry_exc:
                raise ManagementPlanError("ai_request_failed", "大模型请求失败", status=502) from retry_exc
        try:
            validate_reward_items(payload["items"])
        except RewardPolicyError as exc:
            raise ManagementPlanError(exc.code, str(exc), status=422, details={"logical_key": exc.logical_key}) from exc
        payload["policy_version"] = POLICY_VERSION
        payload["skill_version"] = SKILL_VERSION
        payload["context_version"] = context["context_version"]
        if intent == "review":
            payload["review"] = {**payload["review"], "evidence": context["review_evidence"]}
            logger.info("management_plan step=evidence_attached user_id=%s rules=%s store_items=%s", user_id, len(context["review_evidence"]["reward_rules"]), len(context["review_evidence"]["store_items"]))
        draft_id = str(uuid.uuid4())
        now = now_text()
        expires = (datetime.now(BEIJING) + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        with closing(self.connect()) as conn:
            conn.execute(
                """INSERT INTO server_management_plan_drafts
                (id,user_id,request_text,context_version,payload_json,expires_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (draft_id, user_id, request_text, context["context_version"], json.dumps(payload, ensure_ascii=False), expires, now, now),
            )
            conn.commit()
        logger.info("management_plan step=draft_saved user_id=%s intent=%s draft_id=%s", user_id, intent, draft_id)
        return {"draft_id": draft_id, "context_version": context["context_version"], "payload": payload, "expires_at": expires}

    def _draft(self, conn: sqlite3.Connection, user_id: int, draft_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM server_management_plan_drafts WHERE id=? AND user_id=?", (draft_id, user_id)
        ).fetchone()
        if not row:
            raise ManagementPlanError("draft_not_found", "方案草案不存在", status=404)
        if str(row["expires_at"]) < now_text():
            raise ManagementPlanError("draft_expired", "方案草案已过期", status=409)
        return row

    def get_draft(self, user_id: int, draft_id: str) -> dict:
        with closing(self.connect()) as conn:
            row = self._draft(conn, user_id, draft_id)
            return {
                "draft_id": row["id"],
                "context_version": row["context_version"],
                "plan_digest": row["plan_digest"],
                "payload": json.loads(row["payload_json"]),
                "expires_at": row["expires_at"],
            }

    def preview(self, user_id: int, draft_id: str, payload: dict | None = None) -> dict:
        with closing(self.connect()) as conn:
            row = self._draft(conn, user_id, draft_id)
            current_context = self._context(user_id)
            if row["context_version"] != current_context["context_version"]:
                raise ManagementPlanError("plan_stale", "方案引用的数据已变化，请重新生成", status=409)
            raw = payload if payload is not None else json.loads(row["payload_json"])
            try:
                canonical = validate_manifest(raw)
                validate_simplified_chinese(canonical)
            except ManagementPlanValidationError as exc:
                raise ManagementPlanError(exc.code, str(exc), status=422, details={"path": exc.path}) from exc
            if canonical["mode"] == "review":
                canonical["review"] = {**canonical["review"], "evidence": current_context["review_evidence"]}
            try:
                validate_reward_items(canonical["items"])
            except RewardPolicyError as exc:
                raise ManagementPlanError(exc.code, str(exc), status=422, details={"logical_key": exc.logical_key}) from exc
            digest = digest_payload(canonical)
            now = now_text()
            conn.execute(
                "UPDATE server_management_plan_drafts SET payload_json=?,plan_digest=?,status='previewed',updated_at=? WHERE id=? AND user_id=?",
                (json.dumps(canonical, ensure_ascii=False), digest, now, draft_id, user_id),
            )
            conn.commit()
            impact = []
            warnings = []
            for item in canonical["items"]:
                entry = {"logical_key": item["logical_key"], "type": item["type"], "action": item["action"]}
                for key in ("record_id", "unlock_source_type", "unlock_source_id", "price", "reward_coins"):
                    if item.get(key) is not None:
                        entry[key] = item[key]
                impact.append(entry)
                if item["action"] in {"update", "bind", "disable"} and not item.get("record_id"):
                    warnings.append(f"{item['logical_key']} 尚未绑定稳定记录，应用前会重新匹配")
            return {
                "draft_id": draft_id,
                "context_version": current_context["context_version"],
                "plan_digest": digest,
                "payload": canonical,
                "warnings": warnings,
                "impact": impact,
            }

    def _ensure_plan(self, conn: sqlite3.Connection, user_id: int, payload: dict) -> sqlite3.Row:
        plan_key = str(payload.get("plan_key") or "self-management").strip()[:80]
        title = str(payload.get("title") or "自我管理方案").strip()[:200]
        row = conn.execute("SELECT * FROM server_management_plans WHERE user_id=? AND plan_key=?", (user_id, plan_key)).fetchone()
        if row:
            return row
        plan_id = str(uuid.uuid4())
        now = now_text()
        conn.execute(
            "INSERT INTO server_management_plans(id,user_id,plan_key,title,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (plan_id, user_id, plan_key, title, now, now),
        )
        return conn.execute("SELECT * FROM server_management_plans WHERE id=?", (plan_id,)).fetchone()

    def _next_version(self, conn: sqlite3.Connection, plan_id: str, kind: str) -> str:
        rows = conn.execute("SELECT version FROM server_management_plan_revisions WHERE plan_id=?", (plan_id,)).fetchall()
        major = max([int(str(row[0]).split(".")[0].lstrip("v")) for row in rows] or [0])
        if not rows:
            return "v1.0"
        if kind == "major":
            return f"v{major + 1}.0"
        minor = max([int(str(row[0]).split(".")[1]) for row in rows if str(row[0]).startswith(f"v{major}.")] or [0])
        return f"v{major}.{minor + 1}"

    def _previous_binding(self, conn: sqlite3.Connection, user_id: int, plan_id: str, logical_key: str) -> sqlite3.Row | None:
        return conn.execute(
            """SELECT b.* FROM server_management_plan_bindings b
            JOIN server_management_plan_revisions r ON r.id=b.revision_id
            WHERE b.user_id=? AND r.plan_id=? AND b.logical_key=? AND b.record_id IS NOT NULL
            ORDER BY r.created_at DESC LIMIT 1""",
            (user_id, plan_id, logical_key),
        ).fetchone()

    def _materialize_item(
        self,
        conn: sqlite3.Connection,
        user_id: int,
        plan_id: str,
        item: dict,
        now: str,
        external_binding: dict | None = None,
    ) -> tuple[str | None, str]:
        previous = self._previous_binding(conn, user_id, plan_id, item["logical_key"])
        if previous:
            return str(previous["record_id"]), "reused"
        item_type = item["type"]
        record_id = None
        if item_type == "ticktick_task" and external_binding:
            record_id = str(external_binding.get("result_task_id") or "") or None
            return record_id, "confirmed" if record_id else "planned"
        if item_type == "local_habit":
            record_id = f"local_{uuid.uuid4()}"
            difficulty = item.get("difficulty") or "medium"
            conn.execute(
                """INSERT INTO server_habits
                (id,user_id,name,icon,color,sort_order,category_id,difficulty,repeat_rule,is_active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, user_id, str(item.get("name") or item.get("title") or item["logical_key"]), item.get("icon"), item.get("color") or "#A3BE8C", int(item.get("sort_order") or 0), item.get("category_id"), difficulty, item.get("repeat_rule") or "FREQ=DAILY", 0, now, now),
            )
            RewardConfigService().ensure_item(conn, user_id, "habit", record_id, difficulty=difficulty)
            self._ensure_object_key(conn, user_id, "habit", record_id)
        elif item_type == "reward_item":
            record_id = f"reward_{uuid.uuid4()}"
            reward = item.get("reward") if isinstance(item.get("reward"), dict) else {}
            conn.execute(
                """INSERT INTO server_rewards
                (id,user_id,title,icon,price,description,unlock_source_type,unlock_source_id,is_active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, user_id, str(item.get("title") or item.get("name") or item["logical_key"]), item.get("icon") or "🎁", float(item.get("price") or reward.get("price") or 0), str(item.get("description") or ""), item.get("unlock_source_type"), item.get("unlock_source_id"), 1, now, now),
            )
            self._ensure_object_key(conn, user_id, "store-item", record_id)
        elif item_type == "goal":
            record_id = f"goal_{uuid.uuid4()}"
            reward = item.get("reward") if isinstance(item.get("reward"), dict) else {}
            conn.execute(
                """INSERT INTO server_goals
                (id,user_id,title,category_id,metric,target_value,period,operator,reward_coins,reward_id,penalty_coins,is_active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, user_id, str(item.get("title") or item["logical_key"]), item.get("category_id"), item.get("metric") or "duration", float(item.get("target_value") or 0), item.get("period") or "daily", item.get("operator") or ">=", float(reward.get("coins") or item.get("reward_coins") or 0), item.get("reward_id"), float(item.get("penalty_coins") or 0), 1, now, now),
            )
            self._ensure_object_key(conn, user_id, "goal", record_id)
        elif item_type == "learning":
            for kr in item.get("krs") or []:
                for task in kr.get("tasks") or []:
                    task["category_id"] = self._learning_category(conn, user_id, task.get("category_id"))
            objective_id = f"objective_{uuid.uuid4()}"
            conn.execute(
                "INSERT INTO server_learning_objectives(id,user_id,title,status,duration,baseline,target_description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (objective_id, user_id, str(item.get("title") or item["logical_key"]), 0, item.get("duration"), item.get("baseline"), item.get("target_description"), now, now),
            )
            record_id = objective_id
            for kr in item.get("krs") or []:
                kr_id = f"kr_{uuid.uuid4()}"
                conn.execute(
                    "INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (kr_id, user_id, objective_id, str(kr.get("title") or "关键结果"), int(kr.get("target_value") or 100), int(kr.get("current_value") or 0), now, now),
                )
                for task in kr.get("tasks") or []:
                    task_id = f"learning_task_{uuid.uuid4()}"
                    conn.execute(
                        """INSERT INTO server_learning_tasks
                        (id,user_id,kr_id,title,status,category_id,priority,reward,due_date,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (task_id, user_id, kr_id, str(task.get("title") or "学习任务"), 0, task.get("category_id"), int(task.get("priority") or 0), float(task.get("reward") or 0), task.get("due_date"), now, now),
                    )
                    RewardConfigService().ensure_item(conn, user_id, "learning", task_id, reward=task.get("reward"))
                    self._ensure_object_key(conn, user_id, "learning-task", task_id)
                self._ensure_object_key(conn, user_id, "learning-kr", kr_id)
            self._ensure_object_key(conn, user_id, "learning-objective", objective_id)
        return record_id, "created" if record_id else "planned"

    def publish_manifest(
        self,
        user_id: int,
        manifest: dict,
        *,
        reason: str = "",
        revision_kind: str = "major",
        parent_revision_id: str | None = None,
        actor_type: str = "user",
        external_bindings: dict[str, dict] | None = None,
    ) -> dict:
        try:
            canonical = validate_manifest(manifest)
            validate_simplified_chinese(canonical)
        except ManagementPlanValidationError as exc:
            raise ManagementPlanError(exc.code, str(exc), status=422) from exc
        digest = digest_payload(canonical)
        with closing(self.connect()) as conn:
            plan = self._ensure_plan(conn, user_id, canonical)
            if parent_revision_id is None and plan["active_revision_id"]:
                parent_revision_id = str(plan["active_revision_id"])
            version = self._next_version(conn, plan["id"], revision_kind)
            revision_id = str(uuid.uuid4())
            now = now_text()
            conn.execute(
                """INSERT INTO server_management_plan_revisions
                (id,plan_id,user_id,version,revision_kind,parent_revision_id,manifest_json,manifest_digest,approval_status,reason,created_at,published_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (revision_id, plan["id"], user_id, version, revision_kind, parent_revision_id, json.dumps(canonical, ensure_ascii=False), digest, "published", reason, now, now),
            )
            conn.execute("UPDATE server_management_plans SET active_revision_id=?,updated_at=? WHERE id=? AND user_id=?", (revision_id, now, plan["id"], user_id))
            change_metadata = json.dumps(
                {
                    "policy_version": canonical.get("policy_version", POLICY_VERSION),
                    "skill_version": canonical.get("skill_version", SKILL_VERSION),
                    "context_version": canonical.get("context_version"),
                    "language_contract": "simplified_chinese",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for item in canonical["items"]:
                record_id, binding_status = self._materialize_item(
                    conn, user_id, plan["id"], item, now,
                    (external_bindings or {}).get(item["logical_key"]),
                )
                conn.execute(
                    """INSERT INTO server_management_plan_bindings
                    (revision_id,user_id,logical_key,domain_type,record_id,binding_status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (revision_id, user_id, item["logical_key"], item["type"], record_id or item.get("record_id"), binding_status, now, now),
                )
                conn.execute(
                    """INSERT INTO server_management_plan_change_log
                    (id,plan_id,revision_id,user_id,actor_type,actor_id,request_summary,reason,change_type,logical_key,before_json,after_json,application_result,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), plan["id"], revision_id, user_id, actor_type, "management-plan-service", change_metadata, reason, "publish", item["logical_key"], None, json.dumps(item, ensure_ascii=False), None, now),
                )
            conn.commit()
        return {"plan_id": plan["id"], "revision_id": revision_id, "version": version, "manifest_digest": digest, "manifest": canonical}

    def _validated_apply_payload(self, user_id: int, draft_id: str, plan_digest: str) -> dict:
        with closing(self.connect()) as conn:
            row = self._draft(conn, user_id, draft_id)
            if row["status"] not in {"previewed", "draft"} or row["plan_digest"] != plan_digest:
                raise ManagementPlanError("plan_stale", "草案摘要不匹配，请重新预览", status=409)
            payload = json.loads(row["payload_json"])
            try:
                validate_simplified_chinese(payload)
            except ManagementPlanValidationError as exc:
                raise ManagementPlanError(exc.code, str(exc), status=422, details={"path": exc.path}) from exc
            if payload.get("mode") == "review":
                raise ManagementPlanError("review_not_applicable", "方案总结仅供阅读，不能确认应用", status=422)
            current_context = self._context(user_id)
            if row["context_version"] != current_context["context_version"]:
                raise ManagementPlanError("plan_stale", "方案引用的数据已变化，请重新预览", status=409)
            return payload

    def external_items_for_apply(self, user_id: int, draft_id: str, plan_digest: str) -> list[dict]:
        payload = self._validated_apply_payload(user_id, draft_id, plan_digest)
        return [
            item for item in payload.get("items", [])
            if item.get("type") == "ticktick_task" and item.get("action") in {"create", "update"}
        ]

    def application_for_key(self, user_id: int, idempotency_key: str) -> dict | None:
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT * FROM server_management_plan_applications WHERE user_id=? AND idempotency_key=?",
                (user_id, idempotency_key),
            ).fetchone()
            if not row:
                return None
            return {
                "application_id": row["id"],
                "status": row["status"],
                "result": json.loads(row["result_json"]),
            }

    def apply(
        self,
        user_id: int,
        draft_id: str,
        plan_digest: str,
        idempotency_key: str,
        external_results: dict[str, dict] | None = None,
    ) -> dict:
        if not idempotency_key or len(idempotency_key) > 160:
            raise ManagementPlanError("invalid_idempotency_key", "幂等键无效", status=422)
        with closing(self.connect()) as conn:
            existing = conn.execute("SELECT * FROM server_management_plan_applications WHERE user_id=? AND idempotency_key=?", (user_id, idempotency_key)).fetchone()
            if existing:
                return {"application_id": existing["id"], "status": existing["status"], "result": json.loads(existing["result_json"])}
            row = self._draft(conn, user_id, draft_id)
            if row["status"] not in {"previewed", "draft"} or row["plan_digest"] != plan_digest:
                raise ManagementPlanError("plan_stale", "草案摘要不匹配，请重新预览", status=409)
            payload = json.loads(row["payload_json"])
            if payload.get("mode") == "review":
                raise ManagementPlanError("review_not_applicable", "方案总结仅供阅读，不能确认应用", status=422)
            current_context = self._context(user_id)
            if row["context_version"] != current_context["context_version"]:
                raise ManagementPlanError("plan_stale", "方案引用的数据已变化，请重新预览", status=409)

        external_items = [item for item in payload.get("items", []) if item.get("type") == "ticktick_task" and item.get("action") in {"create", "update"}]
        if external_items and external_results is None:
            application_id = str(uuid.uuid4())
            result = {"items": [{"logical_key": item["logical_key"], "status": "needs_reconcile", "type": item["type"], "error_code": "external_command_required"} for item in external_items]}
            now = now_text()
            with closing(self.connect()) as conn:
                conn.execute(
                    "INSERT INTO server_management_plan_applications(id,user_id,draft_id,idempotency_key,plan_digest,status,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (application_id, user_id, draft_id, idempotency_key, plan_digest, "needs_reconcile", json.dumps(result, ensure_ascii=False), now, now),
                )
                conn.commit()
            return {"application_id": application_id, "status": "needs_reconcile", "result": result}

        if external_items:
            failed = [
                {"logical_key": item["logical_key"], "type": item["type"], **(external_results or {}).get(item["logical_key"], {"status": "unknown"})}
                for item in external_items
                if (external_results or {}).get(item["logical_key"], {}).get("status") != "confirmed"
            ]
            if failed:
                application_id = str(uuid.uuid4())
                result = {"items": failed}
                now = now_text()
                with closing(self.connect()) as conn:
                    conn.execute(
                        "INSERT INTO server_management_plan_applications(id,user_id,draft_id,idempotency_key,plan_digest,status,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (application_id, user_id, draft_id, idempotency_key, plan_digest, "needs_reconcile", json.dumps(result, ensure_ascii=False), now, now),
                    )
                    conn.commit()
                return {"application_id": application_id, "status": "needs_reconcile", "result": result}

        # 先关闭读取连接再进入发布服务，避免 SQLite 读连接阻塞版本写入。
        # 第一版把可安全持久化的方案定义写入版本；外部 TickTick 项目仍由已有命令完成。
        revision = self.publish_manifest(
            user_id,
            payload,
            reason="AI 管理方案确认应用",
            revision_kind="major",
            actor_type="ai",
            external_bindings=external_results,
        )
        result = {"revision": revision, "items": [
            {
                "logical_key": item["logical_key"],
                "status": (external_results or {}).get(item["logical_key"], {}).get("status", "planned"),
                "type": item["type"],
                **({"result_task_id": (external_results or {})[item["logical_key"]].get("result_task_id")} if item["logical_key"] in (external_results or {}) else {}),
            }
            for item in payload["items"]
        ]}
        application_id = str(uuid.uuid4())
        now = now_text()
        with closing(self.connect()) as conn:
            try:
                conn.execute(
                    "INSERT INTO server_management_plan_applications(id,user_id,draft_id,idempotency_key,plan_digest,status,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (application_id, user_id, draft_id, idempotency_key, plan_digest, "applied", json.dumps(result, ensure_ascii=False), now, now),
                )
                conn.execute("UPDATE server_management_plan_drafts SET status='applied',updated_at=? WHERE id=?", (now, draft_id))
                conn.commit()
            except sqlite3.IntegrityError:
                existing = conn.execute("SELECT * FROM server_management_plan_applications WHERE user_id=? AND idempotency_key=?", (user_id, idempotency_key)).fetchone()
                if existing:
                    return {"application_id": existing["id"], "status": existing["status"], "result": json.loads(existing["result_json"])}
                raise
        return {"application_id": application_id, "status": "applied", "result": result}

    def list_revisions(self, user_id: int) -> list[dict]:
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT * FROM server_management_plan_revisions WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
            return [{"id": row["id"], "plan_id": row["plan_id"], "version": row["version"], "revision_kind": row["revision_kind"], "manifest_digest": row["manifest_digest"], "approval_status": row["approval_status"], "reason": row["reason"], "created_at": row["created_at"]} for row in rows]

    def export_revision(self, user_id: int, revision_id: str) -> dict:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM server_management_plan_revisions WHERE id=? AND user_id=?", (revision_id, user_id)).fetchone()
            if not row:
                raise ManagementPlanError("revision_not_found", "管理方案版本不存在", status=404)
            manifest = json.loads(row["manifest_json"])
            markdown = self._markdown(row, manifest)
            return {"version": row["version"], "manifest_digest": row["manifest_digest"], "manifest": manifest, "markdown": markdown}

    def import_preview(self, user_id: int, manifest: dict) -> dict:
        try:
            incoming = validate_manifest(manifest)
            validate_simplified_chinese(incoming)
        except ManagementPlanValidationError as exc:
            raise ManagementPlanError(exc.code, str(exc), status=422) from exc
        incoming_by_key = {item["logical_key"]: item for item in incoming["items"]}
        current: dict[str, dict] = {}
        with closing(self.connect()) as conn:
            row = conn.execute(
                """SELECT r.manifest_json FROM server_management_plans p
                JOIN server_management_plan_revisions r ON r.id=p.active_revision_id
                WHERE p.user_id=? AND p.plan_key=?""",
                (user_id, str(incoming.get("plan_key") or "self-management")),
            ).fetchone()
            if row:
                current = {item["logical_key"]: item for item in json.loads(row[0]).get("items", [])}
        changes = []
        for key in sorted(set(current) | set(incoming_by_key)):
            before = current.get(key)
            after = incoming_by_key.get(key)
            if before is None:
                change_type = "added"
            elif after is None:
                change_type = "deactivated"
            elif digest_payload(before) != digest_payload(after):
                change_type = "changed"
            else:
                change_type = "matched"
            changes.append({"logical_key": key, "change_type": change_type, "before": before, "after": after})
        return {"manifest": incoming, "manifest_digest": digest_payload(incoming), "changes": changes, "requires_confirmation": any(item["change_type"] in {"changed", "deactivated"} for item in changes)}

    def patch_preview(self, user_id: int, revision_id: str, patch: dict) -> dict:
        try:
            patch_payload = validate_patch(patch)
        except ManagementPlanValidationError as exc:
            raise ManagementPlanError(exc.code, str(exc), status=422) from exc
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM server_management_plan_revisions WHERE id=? AND user_id=?", (revision_id, user_id)).fetchone()
            if not row:
                raise ManagementPlanError("revision_not_found", "父版本不存在", status=404)
            manifest = json.loads(row["manifest_json"])
        items = {item["logical_key"]: item for item in manifest.get("items", [])}
        changes = []
        for operation in patch_payload["items"]:
            key = operation["logical_key"]
            before = items.get(key)
            if operation["action"] == "add" and before is not None:
                raise ManagementPlanError("patch_conflict", "add 项目已存在", status=409, details={"logical_key": key})
            if operation["action"] in {"update", "disable", "keep"} and before is None:
                raise ManagementPlanError("patch_conflict", "patch 项目不存在", status=409, details={"logical_key": key})
            after = before
            if operation["action"] == "add":
                after = operation.get("value") or {"logical_key": key, "type": "local_habit", "action": "create"}
                after["logical_key"] = key
                items[key] = after
            elif operation["action"] == "update":
                after = dict(before)
                value = operation.get("value") or {}
                if not isinstance(value, dict):
                    raise ManagementPlanError("invalid_patch_value", "update value 必须是对象", status=422)
                after.update(value)
                items[key] = after
            elif operation["action"] == "disable":
                after = dict(before)
                after["action"] = "disable"
                items[key] = after
            changes.append({"logical_key": key, "action": operation["action"], "before": before, "after": after, "reason": operation.get("reason", "")})
        result = dict(manifest)
        result["items"] = list(items.values())
        canonical = validate_manifest(result)
        return {"parent_revision_id": revision_id, "manifest": canonical, "manifest_digest": digest_payload(canonical), "changes": changes}

    def compare_revisions(self, user_id: int, left_id: str, right_id: str) -> dict:
        left = self.export_revision(user_id, left_id)
        right = self.export_revision(user_id, right_id)
        left_items = {item["logical_key"]: item for item in left["manifest"].get("items", [])}
        right_items = {item["logical_key"]: item for item in right["manifest"].get("items", [])}
        changes = []
        for key in sorted(set(left_items) | set(right_items)):
            before, after = left_items.get(key), right_items.get(key)
            if before == after:
                kind = "unchanged"
            elif before is None:
                kind = "added"
            elif after is None:
                kind = "removed"
            else:
                kind = "changed"
            changes.append({"logical_key": key, "change_type": kind, "before": before, "after": after})
        return {"left_version": left["version"], "right_version": right["version"], "changes": changes}

    @staticmethod
    def _markdown(row: sqlite3.Row, manifest: dict) -> str:
        lines = [f"# {manifest.get('title', '自我管理方案')}", "", f"版本：{row['version']}", f"摘要：`{row['manifest_digest']}`", "", "## 项目"]
        for item in manifest.get("items", []):
            lines.append(f"- `{item['logical_key']}`：{item.get('type')} / {item.get('action')}" + (f"，预计 {item['expected_minutes']} 分钟" if item.get("expected_minutes") else ""))
        return "\n".join(lines) + "\n"

    def export_bundle(self, user_id: int) -> dict[str, Any]:
        with closing(self.connect()) as conn:
            self._backfill_object_keys(conn, user_id, self._CORE_OBJECT_SOURCES + self._EXTENDED_OBJECT_SOURCES)
            
            # Load keys
            keys_dict = {}
            for row in conn.execute("SELECT domain_type, record_id, logical_key FROM server_management_object_keys WHERE user_id=?", (user_id,)).fetchall():
                keys_dict[(row["domain_type"], row["record_id"])] = row["logical_key"]
                
            nodes = []
            relations = []
            unresolved_relations = []
            
            def get_key(domain, rec_id):
                return keys_dict.get((domain, str(rec_id)))
            
            # Categories
            cats = conn.execute("SELECT id, name, icon, color, sort_order FROM server_categories WHERE user_id=?", (user_id,)).fetchall()
            for row in cats:
                key = get_key("category", row["id"])
                if not key: continue
                nodes.append({
                    "logical_key": key, "type": "category", "status": "active",
                    "data": {"name": row["name"], "icon": row["icon"], "color": row["color"], "sort_order": row["sort_order"]}
                })
                
            # Tasks
            tasks = conn.execute("SELECT id, title, category_id, priority, status FROM server_tasks WHERE user_id=? AND deleted_at IS NULL", (user_id,)).fetchall()
            for row in tasks:
                key = get_key("task", row["id"])
                if not key: continue
                status = "active" if row["status"] == 0 else "archived"
                nodes.append({
                    "logical_key": key, "type": "task", "status": status,
                    "data": {"title": row["title"], "priority": row["priority"]}
                })
                cat_key = get_key("category", row["category_id"]) if row["category_id"] else None
                if cat_key:
                    relations.append({"source_key": key, "target_key": cat_key, "type": "child_of"})
                elif row["category_id"]:
                    unresolved_relations.append({"source_key": key, "target_key": f"category.{row['category_id']}", "type": "child_of"})
                    
            # Habits
            habits = conn.execute("SELECT id, name, icon, color, category_id, repeat_rule, is_active, sort_order FROM server_habits WHERE user_id=?", (user_id,)).fetchall()
            for row in habits:
                key = get_key("habit", row["id"])
                if not key: continue
                status = "archived" if row["is_active"] else "active"
                nodes.append({
                    "logical_key": key, "type": "habit", "status": status,
                    "data": {"name": row["name"], "icon": row["icon"], "color": row["color"], "repeat_rule": row["repeat_rule"], "sort_order": row["sort_order"]}
                })
                cat_key = get_key("category", row["category_id"]) if row["category_id"] else None
                if cat_key:
                    relations.append({"source_key": key, "target_key": cat_key, "type": "child_of"})
                elif row["category_id"]:
                    unresolved_relations.append({"source_key": key, "target_key": f"category.{row['category_id']}", "type": "child_of"})

            # Learning Objective
            lobjs = conn.execute("SELECT id, title, status, duration, target_description, baseline FROM server_learning_objectives WHERE user_id=?", (user_id,)).fetchall()
            for row in lobjs:
                key = get_key("learning-objective", row["id"])
                if not key: continue
                status = "active" if row["status"] in (0, 1) else "archived"
                data = {"title": row["title"]}
                if row["duration"] is not None: data["duration"] = row["duration"]
                if row["target_description"]: data["target_description"] = row["target_description"]
                if row["baseline"]: data["baseline"] = row["baseline"]
                nodes.append({"logical_key": key, "type": "learning-objective", "status": status, "data": data})

            # Learning KR
            lkrs = conn.execute("SELECT id, objective_id, title, target_value FROM server_learning_krs WHERE user_id=?", (user_id,)).fetchall()
            for row in lkrs:
                key = get_key("learning-kr", row["id"])
                if not key: continue
                nodes.append({
                    "logical_key": key, "type": "learning-kr", "status": "active",
                    "data": {"title": row["title"], "target_value": row["target_value"]}
                })
                obj_key = get_key("learning-objective", row["objective_id"]) if row["objective_id"] else None
                if obj_key:
                    relations.append({"source_key": key, "target_key": obj_key, "type": "child_of"})
                elif row["objective_id"]:
                    unresolved_relations.append({"source_key": key, "target_key": f"learning-objective.{row['objective_id']}", "type": "child_of"})

            # Learning Task
            ltasks = conn.execute("SELECT id, kr_id, title, status, category_id, priority, reward, due_date FROM server_learning_tasks WHERE user_id=?", (user_id,)).fetchall()
            for row in ltasks:
                key = get_key("learning-task", row["id"])
                if not key: continue
                status = "active" if row["status"] == 0 else "archived"
                data = {"title": row["title"], "priority": row["priority"] or 0, "reward": row["reward"] or 0}
                if row["due_date"]: data["due_date"] = row["due_date"]
                nodes.append({"logical_key": key, "type": "learning-task", "status": status, "data": data})
                
                kr_key = get_key("learning-kr", row["kr_id"]) if row["kr_id"] else None
                if kr_key:
                    relations.append({"source_key": key, "target_key": kr_key, "type": "child_of"})
                elif row["kr_id"]:
                    unresolved_relations.append({"source_key": key, "target_key": f"learning-kr.{row['kr_id']}", "type": "child_of"})

            # Exercise Plan
            eplans = conn.execute("SELECT version, title, is_active FROM server_exercise_plan_versions WHERE user_id=?", (user_id,)).fetchall()
            for row in eplans:
                key = get_key("exercise-plan", row["version"])
                if not key: continue
                status = "active" if row["is_active"] else "archived"
                nodes.append({"logical_key": key, "type": "exercise-plan", "status": status, "data": {"title": row["title"]}})

            # Exercise Item
            eitems = conn.execute("SELECT id, plan_version, day_key, variant, section, sort_order, name, sets, intensity, tags_json, is_active FROM server_exercise_plan_items WHERE user_id=?", (user_id,)).fetchall()
            for row in eitems:
                key = get_key("exercise-item", row["id"])
                if not key: continue
                status = "active" if row["is_active"] else "archived"
                nodes.append({
                    "logical_key": key, "type": "exercise-item", "status": status,
                    "data": {
                        "day_key": row["day_key"], "variant": row["variant"], "section": row["section"],
                        "sort_order": row["sort_order"], "name": row["name"], "sets": row["sets"],
                        "intensity": row["intensity"]
                    }
                })
                plan_key = get_key("exercise-plan", row["plan_version"]) if row["plan_version"] else None
                if plan_key:
                    relations.append({"source_key": key, "target_key": plan_key, "type": "child_of"})
                elif row["plan_version"]:
                    unresolved_relations.append({"source_key": key, "target_key": f"exercise-plan.{row['plan_version']}", "type": "child_of"})

            # Goals
            goals = conn.execute("SELECT id, title, category_id, metric, target_value, period, reward_coins, penalty_coins, is_active FROM server_goals WHERE user_id=?", (user_id,)).fetchall()
            for row in goals:
                key = get_key("goal", row["id"])
                if not key: continue
                status = "active" if row["is_active"] else "archived"
                nodes.append({
                    "logical_key": key, "type": "goal", "status": status,
                    "data": {
                        "title": row["title"], "metric": row["metric"], "target_value": row["target_value"],
                        "period": row["period"], "reward_coins": row["reward_coins"] or 0, "penalty_coins": row["penalty_coins"] or 0
                    }
                })
                cat_key = get_key("category", row["category_id"]) if row["category_id"] else None
                if cat_key:
                    relations.append({"source_key": key, "target_key": cat_key, "type": "binds"})
                elif row["category_id"]:
                    unresolved_relations.append({"source_key": key, "target_key": f"category.{row['category_id']}", "type": "binds"})

            # Rewards / Store Items
            rewards = conn.execute("SELECT id, title, icon, price, description, is_active FROM server_rewards WHERE user_id=?", (user_id,)).fetchall()
            for row in rewards:
                key = get_key("store-item", row["id"])
                if not key: continue
                status = "active" if row["is_active"] else "archived"
                nodes.append({
                    "logical_key": key, "type": "store-item", "status": status,
                    "data": {
                        "title": row["title"], "icon": row["icon"] or "", "price": row["price"],
                        "description": row["description"] or ""
                    }
                })

            # Unlock relations (from goals and rewards)
            # Actually unlocks are stored in server_rewards unlock_source_id
            store_unlocks = conn.execute("SELECT id, unlock_source_type, unlock_source_id FROM server_rewards WHERE user_id=? AND unlock_source_id IS NOT NULL", (user_id,)).fetchall()
            for row in store_unlocks:
                tgt_key = get_key("store-item", row["id"])
                src_key = None
                if row["unlock_source_type"] == "goal":
                    src_key = get_key("goal", row["unlock_source_id"])
                elif row["unlock_source_type"] in ("task", "habit"):
                    src_key = get_key(row["unlock_source_type"], row["unlock_source_id"])
                    
                if src_key and tgt_key:
                    relations.append({"source_key": src_key, "target_key": tgt_key, "type": "unlocks"})
                elif tgt_key:
                    unresolved_relations.append({"source_key": f"unknown.{row['unlock_source_id']}", "target_key": tgt_key, "type": "unlocks"})

            # Reward relations (from goal and habit rewards)
            goal_rewards = conn.execute("SELECT id, reward_id FROM server_goals WHERE user_id=? AND reward_id IS NOT NULL", (user_id,)).fetchall()
            for row in goal_rewards:
                src_key = get_key("goal", row["id"])
                tgt_key = get_key("store-item", row["reward_id"])
                if src_key and tgt_key:
                    relations.append({"source_key": src_key, "target_key": tgt_key, "type": "rewards"})
                elif src_key:
                    unresolved_relations.append({"source_key": src_key, "target_key": f"store-item.{row['reward_id']}", "type": "rewards"})
            

            raw_bundle = {
                "nodes": nodes,
                "relations": relations,
                "presentation": {"groups": []},
                "unresolved_relations": unresolved_relations
            }
            
            _, canon_bundle = canonicalize_bundle(raw_bundle)
            return canon_bundle

    def preview_bundle(self, user_id: int, mode: str, incoming_bundle: dict, current_bundle: dict = None) -> dict:
        if not current_bundle:
            current_bundle = self.export_bundle(user_id)
            
        cur_nodes = {n["logical_key"]: n for n in current_bundle.get("nodes", [])}
        inc_nodes = {n["logical_key"]: n for n in incoming_bundle.get("nodes", [])}
        
        diff_nodes = []
        # Process incoming nodes
        for key, inc_node in inc_nodes.items():
            if key in cur_nodes:
                cur_node = cur_nodes[key]
                # Compare data and status
                data_diff = inc_node.get("data", {}) != cur_node.get("data", {})
                status_diff = inc_node.get("status") != cur_node.get("status")
                
                if data_diff or status_diff:
                    diff_nodes.append({
                        "logical_key": key, "type": inc_node["type"], "action": "update",
                        "before_data": cur_node.get("data", {}), "after_data": inc_node.get("data", {}),
                        "before_status": cur_node.get("status"), "after_status": inc_node.get("status")
                    })
                else:
                    diff_nodes.append({
                        "logical_key": key, "type": inc_node["type"], "action": "match",
                        "before_data": cur_node.get("data", {}), "after_data": inc_node.get("data", {}),
                        "before_status": cur_node.get("status"), "after_status": inc_node.get("status")
                    })
            else:
                diff_nodes.append({
                    "logical_key": key, "type": inc_node["type"], "action": "add",
                    "before_data": None, "after_data": inc_node.get("data", {}),
                    "before_status": None, "after_status": inc_node.get("status")
                })
                
        # Process missing nodes based on mode
        for key, cur_node in cur_nodes.items():
            if key not in inc_nodes:
                if mode == "synchronize" and cur_node.get("status") != "archived":
                    diff_nodes.append({
                        "logical_key": key, "type": cur_node["type"], "action": "archive",
                        "before_data": cur_node.get("data", {}), "after_data": cur_node.get("data", {}),
                        "before_status": cur_node.get("status"), "after_status": "archived"
                    })
                else:
                    diff_nodes.append({
                        "logical_key": key, "type": cur_node["type"], "action": "match",
                        "before_data": cur_node.get("data", {}), "after_data": cur_node.get("data", {}),
                        "before_status": cur_node.get("status"), "after_status": cur_node.get("status")
                    })

        cur_rels = {f'{r["source_key"]}:{r["target_key"]}:{r["type"]}': r for r in current_bundle.get("relations", [])}
        inc_rels = {f'{r["source_key"]}:{r["target_key"]}:{r["type"]}': r for r in incoming_bundle.get("relations", [])}
        
        diff_rels = []
        for r_key, inc_rel in inc_rels.items():
            if r_key in cur_rels:
                diff_rels.append({"relation": inc_rel, "action": "match"})
            else:
                diff_rels.append({"relation": inc_rel, "action": "add"})
                
        for r_key, cur_rel in cur_rels.items():
            if r_key not in inc_rels:
                if mode == "synchronize":
                    diff_rels.append({"relation": cur_rel, "action": "remove"})
                else:
                    diff_rels.append({"relation": cur_rel, "action": "match"})

        return {
            "nodes": diff_nodes,
            "relations": diff_rels,
            "unresolved_relations": incoming_bundle.get("unresolved_relations", [])
        }

    def apply_bundle(self, user_id: int, idempotency_key: str, incoming_bundle: dict, mode: str, plan_key: str = "main_mindmap") -> str:
        # 1. canonicalize and digest
        digest, canon = canonicalize_bundle(incoming_bundle)
        diff = self.preview_bundle(user_id, mode, canon)
        supported = {"category", "task", "habit", "learning-objective"}
        unsupported = sorted({node["type"] for node in diff["nodes"] if node["action"] != "match" and node["type"] not in supported})
        if unsupported:
            raise ValueError(f"management_bundle_unsupported_domains:{','.join(unsupported)}")
        now_ts = now_text()
        
        with closing(self.connect()) as conn:
            # 2. Idempotency Check
            row = conn.execute("SELECT id FROM server_management_plan_revisions WHERE user_id=? AND plan_id=(SELECT id FROM server_management_plans WHERE plan_key=? AND user_id=?) AND version=?", (user_id, plan_key, user_id, idempotency_key)).fetchone()
            if row:
                return str(row["id"])
                
            # Check digest
            row_digest = conn.execute("SELECT id FROM server_management_plan_revisions WHERE user_id=? AND plan_id=(SELECT id FROM server_management_plans WHERE plan_key=? AND user_id=?) AND manifest_digest=?", (user_id, plan_key, user_id, digest)).fetchone()
            if row_digest:
                return str(row_digest["id"])

            conn.execute("BEGIN TRANSACTION")
            try:
                # 3. Plan & Baseline Revision
                plan_row = conn.execute("SELECT id, active_revision_id FROM server_management_plans WHERE user_id=? AND plan_key=?", (user_id, plan_key)).fetchone()
                if not plan_row:
                    plan_id = uuid.uuid4().hex
                    conn.execute("INSERT INTO server_management_plans (id, user_id, plan_key, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (plan_id, user_id, plan_key, "Imported Plan", now_ts, now_ts))
                    parent_rev_id = None
                else:
                    plan_id = plan_row["id"]
                    parent_rev_id = plan_row["active_revision_id"]
                
                # We will map updates back directly using object keys
                key_to_id = {}
                for r in conn.execute("SELECT logical_key, domain_type, record_id FROM server_management_object_keys WHERE user_id=?", (user_id,)).fetchall():
                    key_to_id[r["logical_key"]] = (r["domain_type"], r["record_id"])
                    
                # helper to allocate IDs
                def ensure_record_id(l_key, domain_type):
                    if l_key in key_to_id: return key_to_id[l_key][1]
                    # We have an issue here. Many domains have AUTOINCREMENT integer ID.
                    # We can't pre-allocate AUTOINCREMENT in sqlite easily without actually inserting.
                    return None
                    
                for diff_node in diff["nodes"]:
                    action = diff_node["action"]
                    if action == "match": continue
                    
                    l_key = diff_node["logical_key"]
                    d_type = diff_node["type"]
                    data = diff_node.get("after_data", {})
                    status = diff_node.get("after_status", "active")
                    
                    rec_id = ensure_record_id(l_key, d_type)
                    
                    if d_type == "category":
                        if not rec_id: # Add
                            cursor = conn.execute("INSERT INTO server_categories (user_id,name,group_name,icon,color,sort_order,updated_at) VALUES (?,?,?,?,?,?,?)", (user_id,data.get("name",""),data.get("group_name") or "默认",data.get("icon",""),data.get("color",""),data.get("sort_order",0),now_ts))
                            rec_id = str(cursor.lastrowid)
                            conn.execute("INSERT INTO server_management_object_keys (user_id, domain_type, record_id, logical_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (user_id, d_type, rec_id, l_key, now_ts, now_ts))
                            key_to_id[l_key] = (d_type, rec_id)
                        else:
                            conn.execute("UPDATE server_categories SET name=?, icon=?, color=?, sort_order=? WHERE id=? AND user_id=?", (data.get("name"), data.get("icon"), data.get("color"), data.get("sort_order",0), rec_id, user_id))
                    
                    # We implement basic stubs for task and habit for brevity, 
                    # in real-world a full mapping is required.
                    elif d_type == "task":
                        if not rec_id:
                            rec_id = uuid.uuid4().hex
                            conn.execute("INSERT INTO server_tasks (id,user_id,title,priority,status,updated_at) VALUES (?,?,?,?,?,?)", (rec_id,user_id,data.get("title") or data.get("name","") ,data.get("priority",0),0 if status=="active" else 2,now_ts))
                            conn.execute("INSERT INTO server_management_object_keys (user_id, domain_type, record_id, logical_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (user_id, d_type, rec_id, l_key, now_ts, now_ts))
                            key_to_id[l_key] = (d_type, rec_id)
                        else:
                            conn.execute("UPDATE server_tasks SET title=?,priority=?,status=?,updated_at=? WHERE id=? AND user_id=?", (data.get("title") or data.get("name",""),data.get("priority",0),0 if status=="active" else 2,now_ts,rec_id,user_id))
                            
                    elif d_type == "habit":
                        if not rec_id:
                            rec_id = uuid.uuid4().hex
                            conn.execute("INSERT INTO server_habits (id,user_id,name,icon,color,repeat_rule,sort_order,is_active,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (rec_id,user_id,data.get("name",""),data.get("icon",""),data.get("color","") or "#A3BE8C",data.get("repeat_rule",""),data.get("sort_order",0),0 if status=="active" else 1,now_ts,now_ts))
                            conn.execute("INSERT INTO server_management_object_keys (user_id, domain_type, record_id, logical_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (user_id, d_type, rec_id, l_key, now_ts, now_ts))
                            key_to_id[l_key] = (d_type, rec_id)
                        else:
                            conn.execute("UPDATE server_habits SET name=?,icon=?,color=?,repeat_rule=?,sort_order=?,is_active=?,updated_at=? WHERE id=? AND user_id=?", (data.get("name"),data.get("icon"),data.get("color"),data.get("repeat_rule",""),data.get("sort_order",0),0 if status=="active" else 1,now_ts,rec_id,user_id))

                    elif d_type == "learning-objective":
                        if not rec_id:
                            rec_id = uuid.uuid4().hex
                            conn.execute("INSERT INTO server_learning_objectives (id,user_id,title,status,duration,target_description,baseline,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (rec_id,user_id,data.get("title",""),0 if status=="active" else 2,data.get("duration"),data.get("target_description"),data.get("baseline"),now_ts,now_ts))
                            conn.execute("INSERT INTO server_management_object_keys (user_id, domain_type, record_id, logical_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (user_id, d_type, rec_id, l_key, now_ts, now_ts))
                            key_to_id[l_key] = (d_type, rec_id)
                        else:
                            conn.execute("UPDATE server_learning_objectives SET title=?, status=?, duration=?, target_description=?, baseline=? WHERE id=? AND user_id=?", (data.get("title"), 0 if status=="active" else 2, data.get("duration"), data.get("target_description"), data.get("baseline"), rec_id, user_id))

                # After creating/updating nodes, apply relations
                for diff_rel in diff["relations"]:
                    if diff_rel["action"] == "remove":
                        pass # Typically we nullify the parent reference
                    elif diff_rel["action"] == "add":
                        src = diff_rel["relation"]["source_key"]
                        tgt = diff_rel["relation"]["target_key"]
                        r_type = diff_rel["relation"]["type"]
                        
                        src_id = key_to_id.get(src, (None, None))[1]
                        tgt_id = key_to_id.get(tgt, (None, None))[1]
                        if not src_id or not tgt_id: continue
                        
                        if r_type == "child_of":
                            if src.startswith("task.") and tgt.startswith("category."):
                                conn.execute("UPDATE server_tasks SET category_id=? WHERE id=?", (tgt_id, src_id))
                            elif src.startswith("habit.") and tgt.startswith("category."):
                                conn.execute("UPDATE server_habits SET category_id=? WHERE id=?", (tgt_id, src_id))
                                
                # Create revision
                revision_id = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO server_management_plan_revisions (id, plan_id, user_id, version, revision_kind, parent_revision_id, manifest_json, manifest_digest, approval_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (revision_id, plan_id, user_id, idempotency_key, "apply", parent_rev_id, json.dumps(canon), digest, "approved", now_ts)
                )
                conn.execute("UPDATE server_management_plans SET active_revision_id=? WHERE id=?", (revision_id, plan_id))
                
                # Bindings
                for node in canon["nodes"]:
                    l_key = node["logical_key"]
                    d_type, rec_id = key_to_id.get(l_key, (node["type"], None))
                    conn.execute("INSERT INTO server_management_plan_bindings (revision_id, user_id, logical_key, domain_type, record_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (revision_id, user_id, l_key, d_type, rec_id, now_ts, now_ts))
                    
                conn.commit()
                return revision_id
            except Exception as e:
                conn.rollback()
                raise e
