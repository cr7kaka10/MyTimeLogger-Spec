# -*- coding: utf-8 -*-
"""
服务端四端同步引擎 (sync_hub.py)
===============================
职责：
  - 接收客户端 Push → 按表分流 → LWW 仲裁 → 即时/定时同步滴答清单
  - 响应客户端 Pull → 返回 since 以来增量
  - 5 分钟兜底轮询滴答清单
  - SSE 订阅推送（客户端实时感知变更）
  - 金币结算（幂等）
  - 一致性校验（推 TickTick 后回读确认）

已重构为支持多用户，所有业务数据直接写入/拉取 mtl_server.db (即前缀为 server_ 且含 user_id 的业务表)
"""

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time as _time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

try:
    from .provider_delta_filter import MissingProviderFingerprintError, classify_provider_records
    from .sync_constants import PULL_LIMIT_DEFAULT, PULL_LIMIT_MAX, TICKTICK_POLL_INTERVAL_SEC
    from .sync_sql_allowlist import SYNC_TABLES, SYNC_TABLE_SET, is_server_owned, primary_key_for, server_table_for
    from .ticktick_config import load_ticktick_settings
    from .statistics_start_date import get_user_statistics_start_date
    from .time_utils import normalize_date, normalize_task_record_for_db, normalize_ticktick_task_times, now_bj
    from .domain.reward_rule_service import RewardRuleService
    from .domain.reward_config_service import RewardConfigService
    from .domain.reward_settlement_service import RewardSettlementService
    from .domain.reward_wallet_service import RewardWalletService
    from .domain.sleep_reward_service import SleepRewardService
    from .domain.atimelogger_backup_store import ATimeLoggerBackupStore
    from .domain.session_business_date import session_business_date
    from .domain.sample_data_initialization_service import SampleDataInitializationService
    from .domain.flash_card_service import FlashCardService
    from .domain.learning_category_service import LearningCategoryError, LearningCategoryService
    from .domain.reward_rebuild_diagnostics import log_event, sanitize
    from .logging_config import traced
except (ImportError, ValueError):
    from provider_delta_filter import MissingProviderFingerprintError, classify_provider_records
    from sync_constants import PULL_LIMIT_DEFAULT, PULL_LIMIT_MAX, TICKTICK_POLL_INTERVAL_SEC
    from sync_sql_allowlist import SYNC_TABLES, SYNC_TABLE_SET, is_server_owned, primary_key_for, server_table_for
    from ticktick_config import load_ticktick_settings
    from statistics_start_date import get_user_statistics_start_date
    from time_utils import normalize_date, normalize_task_record_for_db, normalize_ticktick_task_times, now_bj
    from domain.reward_rule_service import RewardRuleService
    from domain.reward_config_service import RewardConfigService
    from domain.reward_settlement_service import RewardSettlementService
    from domain.atimelogger_backup_store import ATimeLoggerBackupStore
    from domain.sample_data_initialization_service import SampleDataInitializationService
    from domain.reward_wallet_service import RewardWalletService
    from domain.sleep_reward_service import SleepRewardService
    from domain.session_business_date import session_business_date
    from domain.flash_card_service import FlashCardService
    from domain.learning_category_service import LearningCategoryError, LearningCategoryService
    from domain.reward_rebuild_diagnostics import log_event, sanitize
    from logging_config import traced

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))


class ProviderPullError(RuntimeError):
    def __init__(self, code: str, diagnostics: dict):
        super().__init__(code)
        self.code = code
        self.diagnostics = sanitize(diagnostics)


def _attach_pull_diagnostics(error: Exception, code: str, diagnostics: dict) -> Exception:
    try:
        error.pull_code = code
        error.diagnostics = sanitize(diagnostics)
        return error
    except Exception:
        return ProviderPullError(code, diagnostics)


def _get_ticktick_client_class():
    try:
        from .ticktick_client import TickTickClient
    except (ImportError, ValueError):
        from ticktick_client import TickTickClient
    return TickTickClient

# 涉及滴答清单的表 → 即时推送 + 回读确认
TICKTICK_TABLES = {"tasks", "habits", "habit_checkins"}
# 保留名称以兼容旧诊断/测试导入；当前任务同步不再静默跳过官方项目。
SKIPPED_TICKTICK_PROJECT_IDS = frozenset()
TICKTICK_PULL_REQUEST_BUDGET = 20
TICKTICK_DEGRADED_COOLDOWN_SECONDS = 5 * 60
SYNC_DIRECTION_CONTRACTS = (
    ("client", "client_to_server"),
    ("client", "server_to_client"),
    ("ticktick", "server_to_ticktick"),
    ("ticktick", "ticktick_to_server"),
)
BLOCKED_SYNC_CONFIG_KEYS = {
    "account_identity_key", "auth_token", "ticktick_config", "atimelogger_config", "ai_model_config", "s3_backup_config",
}
ENVIRONMENT_VERIFIED_USER_KEYS = {
    "env_development_verified_user_id", "env_testing_verified_user_id", "env_production_verified_user_id",
}


def _is_blocked_sync_config(key: object) -> bool:
    value = str(key or "")
    return value in BLOCKED_SYNC_CONFIG_KEYS or value in ENVIRONMENT_VERIFIED_USER_KEYS or value in {
        "env_development_auth_token", "env_testing_auth_token", "env_production_auth_token",
    }


def _now() -> str:
    return now_bj()


def _cst_today() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def _ticktick_local_habit_id(user_id: int, provider_habit_id: str) -> str:
    raw = str(provider_habit_id or "")
    return raw if raw.startswith("local_") else f"ticktick:{user_id}:{raw}"


def _ticktick_provider_habit_id(user_id: int, local_habit_id: str) -> str:
    raw = str(local_habit_id or "")
    prefix = f"ticktick:{user_id}:"
    return raw[len(prefix):] if raw.startswith(prefix) else raw


def _task_raw_json(record: dict) -> dict:
    raw = record.get("raw_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _task_project_id(record: dict) -> str:
    raw = _task_raw_json(record)
    return str(
        record.get("project_id")
        or record.get("projectId")
        or raw.get("project_id")
        or raw.get("projectId")
        or raw.get("projectID")
        or ""
    )


def _parse_ts(val) -> float:
    if not val:
        return 0.0
    try:
        if isinstance(val, (int, float)):
            return float(val)
        return datetime.fromisoformat(str(val).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _ticktick_checkin_time(value) -> str | None:
    """将 TickTick 打卡操作时间规范化为北京时间；不可解析时不伪造同步时刻。"""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.replace(".", "", 1).isdigit():
            timestamp = float(raw)
            if timestamp > 100_000_000_000:
                timestamp /= 1000
            parsed = datetime.fromtimestamp(timestamp, CST)
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            parsed = parsed.replace(tzinfo=CST) if parsed.tzinfo is None else parsed.astimezone(CST)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, ValueError):
        return None


class SyncHub:
    """轻量级四端同步引擎（1~2 用户，支持 mtl_server.db 统一业务库及 user_id 路由）"""

    def __init__(self, db: "ServerDBWrapper", goal_store=None):
        self.db = db
        self._goal_store = goal_store
        self._ticktick_task: asyncio.Task | None = None
        # SSE 订阅者
        self._subscribers: list[tuple[asyncio.Queue, int | None]] = []
        self._pull_lock = asyncio.Lock()
        self._pull_running = False
        self._pull_requested = False
        self._provider_reconcile_lock = asyncio.Lock()
        self._provider_reconcile_tasks: dict[int, asyncio.Task] = {}
        self._reward_wallet = RewardWalletService(self._conn, self._transact, _now, self._update_wallet_in_txn)
        self._reward_settlement = RewardSettlementService(self._transact, _now, self._reward_wallet, self._record_fragment_change_in_txn)
        self._sleep_rewards = SleepRewardService(self._transact, _now, self._reward_wallet, self._record_server_change_in_txn)
        item_reward_fn = getattr(self.db, "get_item_reward", None)
        self._reward_rules = RewardRuleService(lambda: datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"), item_reward_fn)

    def run_startup_sync_migrations(self) -> int:
        """补齐一次性历史版本，绝不在客户端 Pull 请求中运行。"""
        conn = self._conn()
        try:
            user_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM users")]
        finally:
            conn.close()
        completed = 0
        for user_id in user_ids:
            with self._transact() as conn:
                done = conn.execute("SELECT 1 FROM server_sync_migrations WHERE user_id=? AND migration_key='core-version-backfill-v1'", (user_id,)).fetchone()
            if done:
                continue
            self._backfill_unversioned_atm_changes(user_id)
            self._backfill_unversioned_huawei_sleep_changes(user_id)
            with self._transact() as conn:
                conn.execute("INSERT OR IGNORE INTO server_sync_migrations(user_id,migration_key,completed_at) VALUES (?, 'core-version-backfill-v1', ?)", (user_id, _now()))
            completed += 1
        return completed

    # ======================== 通用 DB ========================

    def _db_path(self) -> str:
        return self.db.log_path

    def _conn(self):
        c = sqlite3.connect(self._db_path(), timeout=30.0)
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def _transact(self):
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _update_wallet_in_txn(self, conn, user_id, amount_change, ledger_uuid=None, amount_already_in_ledger=True):
        RewardWalletService.rebuild_wallet_snapshot_in_txn(conn, user_id, _now)

    def _record_fragment_change_in_txn(self, conn, user_id, table_name, record_id, operation, changed_fields):
        self.db.write_server_change(
            user_id, "reward_fragments", str(record_id), operation, changed_fields,
            table_name="server_reward_fragments", conn=conn,
        )

    def _record_server_change_in_txn(self, conn, user_id, table_name, record_id, operation, changed_fields):
        self.db.write_server_change(
            user_id, table_name.removeprefix("server_"), str(record_id), operation, changed_fields,
            table_name=table_name, conn=conn,
        )

    def _expire_reward_fragments_for_user(self, user_id: int) -> int:
        with self._transact() as conn:
            return len(self._reward_settlement.expire_fragments_for_user_in_txn(conn, user_id))

    def get_record(self, table: str, record_id: int | str, user_id: int) -> dict | None:
        try:
            conn = self._conn()
            pk = self._pk_for_table(table)
            server_table = server_table_for(table)
            row = conn.execute(
                f"SELECT * FROM {server_table} WHERE user_id = ? AND {pk} = ?", (user_id, record_id)
            ).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception:
            return None

    def get_records(self, table: str, record_ids: set[str], user_id: int) -> dict[str, dict]:
        if not record_ids:
            return {}
        conn = self._conn()
        try:
            pk = self._pk_for_table(table)
            placeholders = ",".join("?" for _ in record_ids)
            rows = conn.execute(
                f"SELECT * FROM {server_table_for(table)} WHERE user_id=? AND {pk} IN ({placeholders})",
                (user_id, *record_ids),
            ).fetchall()
            return {str(row[pk]): dict(row) for row in rows}
        finally:
            conn.close()

    @staticmethod
    def _category_record_by_name(conn: sqlite3.Connection, user_id: int, name: object) -> dict | None:
        """分类在账号内以名称作为跨端稳定标识，不能依赖各端自增 ID。"""
        normalized = str(name or "").strip()
        if not normalized:
            return None
        row = conn.execute(
            "SELECT * FROM server_categories WHERE user_id=? AND LOWER(TRIM(name))=LOWER(?)",
            (user_id, normalized),
        ).fetchone()
        return dict(row) if row else None

    def _management_plan_snapshot(self, user_id: int) -> dict:
        """Return only published management-plan metadata for one account.

        Plan drafts and preview records deliberately stay out of the sync
        protocol.  The manifest is already canonicalized and schema-filtered
        by ManagementPlanService, so it is safe to expose as configuration.
        """
        conn = self._conn()
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='server_management_plan_revisions'"
            ).fetchone()
            if not exists:
                return {"plans": [], "revisions": [], "bindings": [], "change_log": []}
            revisions = conn.execute(
                """SELECT r.id, r.plan_id, p.plan_key, p.title, r.version,
                          r.revision_kind, r.parent_revision_id,
                          r.manifest_json, r.manifest_digest, r.approval_status,
                          r.reason, r.created_at, r.published_at
                   FROM server_management_plan_revisions r
                   JOIN server_management_plans p ON p.id=r.plan_id AND p.user_id=r.user_id
                  WHERE r.user_id=? AND r.approval_status='published'
                  ORDER BY r.created_at ASC""",
                (user_id,),
            ).fetchall()
            revision_ids = [str(row["id"]) for row in revisions]
            revision_set = set(revision_ids)
            revisions_payload = []
            for row in revisions:
                try:
                    manifest = json.loads(row["manifest_json"] or "{}")
                except (TypeError, ValueError):
                    manifest = {}
                revisions_payload.append({
                    "id": row["id"],
                    "plan_id": row["plan_id"],
                    "plan_key": row["plan_key"],
                    "title": row["title"],
                    "version": row["version"],
                    "revision_kind": row["revision_kind"],
                    "parent_revision_id": row["parent_revision_id"],
                    "manifest": manifest,
                    "manifest_digest": row["manifest_digest"],
                    "approval_status": row["approval_status"],
                    "reason": row["reason"],
                    "created_at": row["created_at"],
                    "published_at": row["published_at"],
                })
            bindings = []
            if revision_ids:
                placeholders = ",".join("?" for _ in revision_ids)
                bindings = [dict(row) for row in conn.execute(
                    f"""SELECT id, revision_id, logical_key, domain_type,
                               record_id, binding_status, created_at, updated_at
                          FROM server_management_plan_bindings
                         WHERE user_id=? AND revision_id IN ({placeholders})
                         ORDER BY revision_id, logical_key""",
                    (user_id, *revision_ids),
                ).fetchall()]
            change_log = []
            if revision_ids:
                placeholders = ",".join("?" for _ in revision_ids)
                change_log = [dict(row) for row in conn.execute(
                    f"""SELECT id, plan_id, revision_id, actor_type, change_type,
                               logical_key, before_json, after_json, reason,
                               created_at
                          FROM server_management_plan_change_log
                         WHERE user_id=? AND revision_id IN ({placeholders})
                         ORDER BY created_at, id""",
                    (user_id, *revision_ids),
                ).fetchall()]
            plans = [dict(row) for row in conn.execute(
                """SELECT id, plan_key, title, active_revision_id, created_at, updated_at
                     FROM server_management_plans
                    WHERE user_id=? AND active_revision_id IS NOT NULL""",
                (user_id,),
            ).fetchall()]
            return {
                "plans": plans,
                "revisions": revisions_payload,
                "bindings": bindings,
                "change_log": change_log,
            }
        finally:
            conn.close()

    def _include_habit_parents_for_checkins(
        self,
        tables: dict[str, list[dict]],
        user_id: int,
        request_id: str | None = None,
    ) -> int:
        """Ensure version pull can be applied by clients with local FK checks enabled."""
        checkins = tables.get("habit_checkins") or []
        if not checkins:
            return 0
        habit_ids = {
            str(row.get("habit_id"))
            for row in checkins
            if isinstance(row, dict) and row.get("habit_id")
        }
        if not habit_ids:
            return 0
        included = {
            str(row.get("id"))
            for row in tables.get("habits", [])
            if isinstance(row, dict) and row.get("id")
        }
        missing = sorted(habit_ids - included)
        if not missing:
            return 0

        conn = self._conn()
        try:
            placeholders = ",".join(["?"] * len(missing))
            rows = conn.execute(
                f"SELECT * FROM server_habits WHERE user_id = ? AND id IN ({placeholders})",
                (user_id, *missing),
            ).fetchall()
        finally:
            conn.close()

        parents = [dict(row) for row in rows]
        if parents:
            tables.setdefault("habits", []).extend(parents)
            logger.info(
                "[SyncHub] version pull dependency backfill request_id=%s user_id=%s child_table=habit_checkins parent_table=habits requested=%s returned=%s",
                request_id,
                user_id,
                len(missing),
                len(parents),
            )
        return len(parents)

    def _canonical_record_id_for_change(
        self,
        table: str,
        record: dict,
        user_id: int,
        fallback: int | str,
        conn: sqlite3.Connection | None = None,
    ) -> str:
        if table == "categories" and record.get("name"):
            owns_conn = conn is None
            conn = conn or self._conn()
            try:
                row = self._category_record_by_name(conn, user_id, record.get("name"))
                return str(row["id"]) if row else str(fallback)
            finally:
                if owns_conn:
                    conn.close()
        if table == "exercise_daily_logs" and record.get("date"):
            owns_conn = conn is None
            conn = conn or self._conn()
            try:
                row = conn.execute(
                    """SELECT id FROM server_exercise_daily_logs
                       WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'""",
                    (user_id, record.get("date"), record.get("plan_version") or "v0"),
                ).fetchone()
                return str(row["id"]) if row else str(fallback)
            finally:
                if owns_conn:
                    conn.close()
        if table == "exercise_checkins" and record.get("date") and record.get("item_key"):
            owns_conn = conn is None
            conn = conn or self._conn()
            try:
                row = conn.execute(
                    "SELECT id FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=? AND item_key=?",
                    (user_id, record.get("date"), record.get("plan_version") or "v0", record.get("item_key")),
                ).fetchone()
                return str(row["id"]) if row else str(fallback)
            finally:
                if owns_conn:
                    conn.close()
        if table == "exercise_diet_checkins" and record.get("date") and record.get("rule_key"):
            owns_conn = conn is None
            conn = conn or self._conn()
            try:
                row = conn.execute(
                    "SELECT id FROM server_exercise_diet_checkins WHERE user_id=? AND date=? AND plan_version=? AND rule_key=?",
                    (user_id, record.get("date"), record.get("plan_version") or "v4", record.get("rule_key")),
                ).fetchone()
                return str(row["id"]) if row else str(fallback)
            finally:
                if owns_conn:
                    conn.close()
        if table != "huawei_sleep_data" or not record.get("date"):
            return str(fallback)
        owns_conn = conn is None
        if conn is None:
            conn = self._conn()
        try:
            row = conn.execute(
                "SELECT id FROM server_huawei_sleep_data WHERE user_id = ? AND date = ?",
                (user_id, record.get("date")),
            ).fetchone()
            return str(row["id"]) if row else str(fallback)
        finally:
            if owns_conn:
                conn.close()

    def get_changes_since(self, table: str, since: str | None, user_id: int) -> list[dict]:
        if table in {"management_plans", "management_plan_revisions",
                     "management_plan_bindings", "management_plan_change_log"}:
            return []
        try:
            conn = self._conn()
            if since:
                rows = conn.execute(
                    f"SELECT * FROM {server_table_for(table)} WHERE user_id = ? AND updated_at > ? ORDER BY updated_at",
                    (user_id, since),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM {server_table_for(table)} WHERE user_id = ? ORDER BY updated_at",
                    (user_id,)
                ).fetchall()
            conn.close()

            # 兼容：客户端期望的是去掉 user_id 列，且表名为 habits 等（不需要 server_ 前缀）
            results = []
            for r in rows:
                d = dict(r)
                if table != "user_wallets":
                    d.pop("user_id", None)
                if table == "tasks" and "tags" in d:
                    tags_val = d["tags"]
                    if tags_val:
                        # 兼容处理：如果是逗号分隔的纯文本，拆分后以 JSON 字符串数组格式返回
                        tags_list = [t.strip() for t in str(tags_val).split(",") if t.strip()]
                    else:
                        tags_list = []
                    d["tags"] = json.dumps(tags_list, ensure_ascii=False)
                results.append(d)
            return results
        except Exception as e:
            logger.error(f"get_changes_since {table} (user={user_id}): {e}")
            return []

    def _running_reward_snapshot(self, user_id: int) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT snapshot_json FROM server_reward_rebuild_snapshots snapshot
                   JOIN server_reward_rebuild_jobs job ON job.id=snapshot.job_id AND job.user_id=snapshot.user_id
                   WHERE job.user_id=? AND job.status IN ('queued','running')
                   ORDER BY job.created_at DESC LIMIT 1""", (user_id,),
            ).fetchone()
            return json.loads(row["snapshot_json"]) if row else None
        finally:
            conn.close()

    def get_reward_ledger_snapshot(self, user_id: int) -> dict:
        """Return the complete server-owned ledger with a deterministic integrity summary."""
        running = self._running_reward_snapshot(user_id)
        conn = self._conn()
        try:
            rows = running["tables"]["server_reward_ledger"] if running else [dict(row) for row in conn.execute(
                "SELECT * FROM server_reward_ledger WHERE user_id=? ORDER BY id", (user_id,)).fetchall()]
            fragments = running["tables"]["server_reward_fragments"] if running else [dict(row) for row in conn.execute(
                "SELECT * FROM server_reward_fragments WHERE user_id=? ORDER BY id", (user_id,)).fetchall()]
            epoch_row = conn.execute(
                "SELECT active_epoch FROM server_reward_rebuild_epochs WHERE user_id=?", (user_id,),
            ).fetchone()
        finally:
            conn.close()
        rows = sorted((dict(row) for row in rows), key=lambda row: str(row.get("id") or ""))
        fragments = sorted((dict(row) for row in fragments), key=lambda row: str(row.get("id") or ""))
        summary = {
            "balance": sum(float(row["amount"]) for row in rows),
            "income": sum(max(float(row["amount"]), 0) for row in rows),
            "expense": sum(max(-float(row["amount"]), 0) for row in rows),
        }
        for row in rows:
            row.pop("user_id", None)
        for row in fragments:
            row.pop("user_id", None)
        payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {
            "rows": rows,
            "summary": {key: float(value or 0) for key, value in summary.items()},
            "integrity": {"count": len(rows), "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()},
            "epoch": int(epoch_row["active_epoch"]) if epoch_row else 0,
            "reward_fragments": fragments,
        }


    def _pk_for_table(self, table: str) -> str:
        return primary_key_for(table)

    def _server_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({server_table_for(table)})").fetchall()}

    def _record_sync_state(
        self,
        user_id: int,
        system: str,
        direction: str,
        status: str = "success",
        error: str | None = None,
        merged_count: int = 0,
        diagnostics: dict | None = None,
    ) -> str:
        now = _now()
        last_synced_at = now if status == "success" else None
        diagnostics_json = json.dumps(diagnostics or {}, ensure_ascii=False, default=str)
        try:
            with self._transact() as conn:
                conn.execute(
                    """
                    INSERT INTO server_sync_state (
                        user_id, system, direction, last_synced_at, last_attempted_at,
                        last_status, last_error, last_merged_count, diagnostics_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, system, direction) DO UPDATE SET
                        last_synced_at = COALESCE(excluded.last_synced_at, server_sync_state.last_synced_at),
                        last_attempted_at = excluded.last_attempted_at,
                        last_status = excluded.last_status,
                        last_error = excluded.last_error,
                        last_merged_count = excluded.last_merged_count,
                        diagnostics_json = excluded.diagnostics_json,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, system, direction, last_synced_at, now, status, error, merged_count, diagnostics_json, now, now),
                )
        except Exception as e:
            logger.warning("记录同步水位失败 user=%s system=%s direction=%s: %s", user_id, system, direction, e)
        return now

    def _ticktick_cooldown_retry_at(self, user_id: int) -> str | None:
        """Return a still-active degraded retry time from the per-user direction state."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT last_status, diagnostics_json FROM server_sync_state WHERE user_id=? AND system='ticktick' AND direction='ticktick_to_server'",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row or row["last_status"] != "degraded":
            return None
        try:
            retry_at = json.loads(row["diagnostics_json"] or "{}").get("retry_at")
            retry_time = datetime.fromisoformat(str(retry_at))
            if retry_time.tzinfo is None:
                retry_time = retry_time.replace(tzinfo=CST)
            return str(retry_at) if retry_time > datetime.now(CST) else None
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def _get_sync_state_map(self, user_id: int) -> dict:
        try:
            conn = self._conn()
            rows = conn.execute(
                "SELECT direction, last_synced_at FROM server_sync_state WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            conn.close()
            return {f"{row['direction']}_synced_at": row["last_synced_at"] for row in rows if row["last_synced_at"]}
        except Exception:
            return {}

    def _filter_sync_record(self, conn: sqlite3.Connection, table: str, data: dict, user_id: int) -> tuple[dict, list[dict]]:
        """调用链路：handle_push -> _filter_sync_record -> upsert -> SQLite。
        按同步表白名单和服务端实际字段过滤，禁止客户端写 user_id（服务端从 JWT 注入）。
        user_id 和未知字段均静默丢弃，不进 rejected 数组，避免产生误导性 WARNING 日志。
        """
        columns = self._server_columns(conn, table)
        filtered: dict = {}
        for key, value in data.items():
            if key == "user_id":
                # 服务端字段，由 JWT token 注入，客户端传来的静默丢弃
                continue
            if key not in columns:
                # 客户端字段版本差异导致的多余字段，静默丢弃（非错误）
                logger.debug("[sync_filter] unknown field table=%s field=%s, ignored", table, key)
                continue
            filtered[key] = value
        if table == "flash_cards":
            for key in ("polished_text", "diary_mood", "diary_content", "task_recommendations_json",
                        "analysis_error_code", "analysis_draft_id", "analysis_status"):
                filtered.pop(key, None)
            card_id = filtered.get("id")
            existing = card_id and conn.execute(
                "SELECT analysis_status FROM server_flash_cards WHERE user_id=? AND id=?", (user_id, card_id)
            ).fetchone()
            if not existing:
                filtered["analysis_status"] = "pending"
        if table == "exercise_checkins":
            # 截止锁只能由服务器调度写入；客户端回推不得覆盖它。
            filtered.pop("locked_at", None)
            filtered.pop("lock_reason", None)
        if table == "exercise_diet_checkins":
            filtered.pop("failure_reason", None)
            filtered.pop("penalty_source_id", None)
        filtered["user_id"] = user_id
        if "created_at" in columns and not filtered.get("created_at"):
            filtered["created_at"] = _now()
        if "updated_at" in columns:
            filtered["updated_at"] = _now()
        return filtered, []

    def _rebuild_wallet_snapshot_in_txn(self, conn: sqlite3.Connection, user_id: int):
        """调用链路：SyncHub.upsert(reward_ledger) -> 本函数 -> SUM(ledger) -> UPSERT(wallet)。

        同步路径是事实表追加式写入，钱包快照只允许由 server_reward_ledger 重建，避免客户端推送覆盖余额。
        SQL：SELECT SUM(amount) FROM server_reward_ledger；UPSERT server_user_wallets。
        返回：无；调用方事务提交后 wallet 与 ledger 保持一致。
        """
        RewardWalletService.rebuild_wallet_snapshot_in_txn(conn, user_id, _now)

    def _prepare_exercise_record(self, conn: sqlite3.Connection, table: str, record: dict, user_id: int) -> dict:
        if table == "exercise_diet_checkins":
            target_date = str(record.get("date") or _cst_today())[:10]
            plan_version, rule_key = str(record.get("plan_version") or "v4"), str(record.get("rule_key") or "")
            # Deadline is a server-owned Beijing-time fact.  Populate it even
            # for an older client that only sends the natural key and status.
            record["deadline_at"] = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
            existing = conn.execute("""SELECT id FROM server_exercise_diet_checkins
                WHERE user_id=? AND date=? AND plan_version=? AND rule_key=?""",
                (user_id, target_date, plan_version, rule_key)).fetchone()
            record["id"] = existing["id"] if existing else f"diet:{user_id}:{target_date}:{plan_version}:{rule_key}"
            return record
        if table == "exercise_daily_logs":
            # 客户端每日汇总表没有 exercise_type；day_name 是星期，不是记录类型。
            record["exercise_type"] = "daily"
            if record.get("body_fat_rate") is None:
                record.pop("body_fat_rate", None)
            elif not 3 <= float(record["body_fat_rate"]) <= 75:
                raise ValueError("body_fat_rate_out_of_range")
            canonical = conn.execute(
                """SELECT id FROM server_exercise_daily_logs
                   WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'""",
                (user_id, record.get("date"), record.get("plan_version") or "v0"),
            ).fetchone()
            if canonical:
                record["id"] = canonical["id"]
            return record
        if table != "exercise_checkins" or record.get("log_id"):
            return record

        target_date = str(record.get("date") or _cst_today())[:10]
        plan_version = str(record.get("plan_version") or "v0")
        existing = conn.execute(
            "SELECT id FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=? AND item_key=?",
            (user_id, target_date, plan_version, record.get("item_key")),
        ).fetchone()
        if existing:
            record["id"] = existing["id"]
        exercise_type = str(record.get("item_key") or record.get("item_name") or "daily")
        log_id = f"auto-{user_id}-{target_date}-{plan_version}-{exercise_type}"
        now = _now()
        conn.execute(
            """
            INSERT INTO server_exercise_daily_logs
                (id, user_id, date, plan_version, exercise_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date, plan_version, exercise_type)
            DO UPDATE SET updated_at = excluded.updated_at
            """,
            (log_id, user_id, target_date, plan_version, exercise_type, now, now),
        )
        row = conn.execute(
            """
            SELECT id FROM server_exercise_daily_logs
            WHERE user_id = ? AND date = ? AND plan_version = ? AND exercise_type = ?
            """,
            (user_id, target_date, plan_version, exercise_type),
        ).fetchone()
        record["log_id"] = row["id"] if row else log_id
        return record

    @staticmethod
    def _body_metric_item_key(conn: sqlite3.Connection, user_id: int, target_date: str, plan_version: str) -> str | None:
        weekday = ("周一", "周二", "周三", "周四", "周五")[datetime.fromisoformat(target_date).weekday()] if datetime.fromisoformat(target_date).weekday() < 5 else None
        schedule_type = "weekday" if weekday else "rest"
        removed = {"到达图书馆", "离开图书馆", "到达体育公园", "达到体育公园", "离开体育公园", "结束户外锻炼"}
        rows = conn.execute("""SELECT item FROM server_exercise_plan_schedule_items WHERE user_id=? AND plan_version=? AND schedule_type=? ORDER BY sort_order""", (user_id, plan_version, schedule_type)).fetchall()
        visible = [str(row["item"] or "") for row in rows if str(row["item"] or "").strip().split(None, 1)[-1] not in removed]
        return next((f"sc-{target_date}-{index}" for index, name in enumerate(visible) if "体重" in name and "体脂" in name), None)

    def upsert(self, table: str, data: dict, user_id: int, conn: sqlite3.Connection | None = None) -> tuple[bool, list[dict]]:
        owns_conn = conn is None
        try:
            if conn is None:
                conn = self._conn()
            if table == "learning_tasks":
                try:
                    LearningCategoryService.validate_id(conn, user_id, data.get("category_id"))
                except LearningCategoryError as exc:
                    if owns_conn:
                        conn.close()
                    return False, [{"table": table, "record_id": data.get("id"), "reason": exc.code}]
            server_table = server_table_for(table)
            data_copy, rejected = self._filter_sync_record(conn, table, data, user_id)
            body_metric_locked = False
            if table == "exercise_daily_logs" and (
                data_copy.get("weight") is not None or data_copy.get("body_fat_rate") is not None
            ):
                target_date = str(data_copy.get("date") or _cst_today())[:10]
                if target_date != _cst_today():
                    raise ValueError("body_metrics_recording_requires_today")
                locked = conn.execute(
                    "SELECT 1 FROM server_exercise_checkins WHERE user_id=? AND date=? AND locked_at IS NOT NULL LIMIT 1",
                    (user_id, target_date),
                ).fetchone()
                body_metric_locked = bool(locked)
            if table == "exercise_checkins":
                target_date = str(data_copy.get("date") or _cst_today())[:10]
                plan_version = str(data_copy.get("plan_version") or "v0")
                locked = conn.execute(
                    "SELECT 1 FROM server_exercise_checkins WHERE user_id=? AND date=? AND locked_at IS NOT NULL LIMIT 1",
                    (user_id, target_date),
                ).fetchone()
                target_key = self._body_metric_item_key(conn, user_id, target_date, plan_version)
                if locked and target_key and str(data_copy.get("item_key") or "") == target_key:
                    raise ValueError("body_metrics_deadline_locked")
            if table == "exercise_diet_checkins":
                target_date = str(data_copy.get("date") or _cst_today())[:10]
                if str(data_copy.get("plan_version") or "") != "v4":
                    raise ValueError("diet_checkin_requires_v4")
                if str(data_copy.get("status") or "pending") not in {"pending", "completed", "failed"}:
                    raise ValueError("invalid_diet_status")
            data_copy = self._prepare_exercise_record(conn, table, data_copy, user_id)
            if table == "exercise_daily_logs" and body_metric_locked:
                # 09:00 后允许补录原始身体数据，但绝不能覆盖守时评分或其他每日事实。
                allowed = {"id", "user_id", "date", "plan_version", "exercise_type", "weight", "body_fat_rate", "created_at", "updated_at"}
                data_copy = {key: value for key, value in data_copy.items() if key in allowed}

            if table == "tasks":
                data_copy = normalize_task_record_for_db(data_copy)
            elif table == "study_sessions" and data_copy.get("start_time"):
                date_text = session_business_date(
                    data_copy["start_time"], data_copy.get("end_time"), str(data_copy.get("date") or ""),
                )
                if date_text:
                    data_copy["date"] = date_text
                    data_copy["day_of_week"] = "星期" + "一二三四五六日"[datetime.fromisoformat(date_text).weekday()]
            if table == "study_sessions" and data_copy.get("category_id") is not None:
                category_id = data_copy["category_id"]
                valid = conn.execute(
                    "SELECT 1 FROM server_categories WHERE user_id=? AND id=?", (user_id, category_id)
                ).fetchone()
                if not valid:
                    existing = conn.execute(
                        "SELECT category_id FROM server_study_sessions WHERE user_id=? AND id=?",
                        (user_id, data_copy.get("id")),
                    ).fetchone()
                    existing_id = existing["category_id"] if existing else None
                    canonical = existing_id is not None and conn.execute(
                        "SELECT 1 FROM server_categories WHERE user_id=? AND id=?", (user_id, existing_id)
                    ).fetchone()
                    if not canonical:
                        return False, [{"table": table, "record_id": data_copy.get("id"), "reason": "invalid_category_reference"}]
                    data_copy["category_id"] = existing_id

            pk = self._pk_for_table(table)
            pk_value = data_copy.get(pk)
            is_inserted = False

            if table == "categories":
                existing_category = self._category_record_by_name(conn, user_id, data_copy.get("name"))
                if existing_category:
                    # 本地与服务端的自增 ID 可能来自不同设备；同名分类必须更新同一条服务端记录。
                    data_copy[pk] = existing_category["id"]
                    pk_value = existing_category["id"]
                else:
                    # 让服务端分配全局主键，随后把权威 ID 返回客户端完成本地对齐。
                    data_copy.pop(pk, None)
                    pk_value = None

            if table in {"sleep_command_receipts", "sleep_notification_receipts"}:
                event_key = "command_id" if table == "sleep_command_receipts" else "notification_id"
                existing = conn.execute(
                    f"SELECT id FROM {server_table} WHERE user_id=? AND device_id=? AND {event_key}=?",
                    (user_id, data_copy.get("device_id"), data_copy.get(event_key)),
                ).fetchone()
                if existing:
                    data_copy[pk] = existing["id"]
                    pk_value = existing["id"]

            if table == "huawei_sleep_data" and data_copy.get("date"):
                existing = conn.execute(
                    "SELECT id,morning_diary,evening_diary FROM server_huawei_sleep_data WHERE user_id = ? AND date = ?",
                    (user_id, data_copy["date"]),
                ).fetchone()
                diary_saved_at = _now()
                for diary_type in ("morning", "evening"):
                    field = f"{diary_type}_diary"
                    written_at = f"{field}_written_at"
                    if field not in data_copy:
                        continue
                    changed = not existing or data_copy[field] != existing[field]
                    if changed:
                        data_copy[written_at] = diary_saved_at if str(data_copy[field] or "").strip() else None
                    else:
                        data_copy.pop(written_at, None)
                if existing:
                    update_keys = [
                        k for k, v in data_copy.items()
                        if k not in ("id", "user_id", "date") and (v is not None or k.endswith("_diary_written_at"))
                    ]
                    if update_keys:
                        sets = ",".join([f"{k}=?" for k in update_keys])
                        vals = [data_copy[k] for k in update_keys] + [user_id, data_copy["date"]]
                        conn.execute(
                            f"UPDATE server_huawei_sleep_data SET {sets} WHERE user_id = ? AND date = ?",
                            vals,
                        )
                    if "morning_diary" in data_copy or "evening_diary" in data_copy:
                        self._sleep_rewards.reconcile_diary_completion_in_txn(conn, user_id, data_copy["date"])
                    if owns_conn:
                        conn.commit()
                        conn.close()
                    return True, rejected
                data_copy.pop("id", None)

            if pk_value is None:
                data_copy.pop(pk, None)
                keys = list(data_copy.keys())
                vals = [data_copy[k] for k in keys]
                placeholders = ",".join(["?"] * len(keys))
                cur = conn.execute(
                    f"INSERT INTO {server_table} ({','.join(keys)}) VALUES ({placeholders})",
                    vals,
                )
                if cur.rowcount > 0:
                    is_inserted = True
            else:
                existing = conn.execute(
                    f"SELECT 1 FROM {server_table} WHERE user_id = ? AND {pk} = ?",
                    (user_id, pk_value),
                ).fetchone()

                if table == "reward_ledger" and existing:
                    logger.info(
                        "sync append-only idempotency hit user_id=%s table=%s record_id=%s reason=%s",
                        user_id, table, pk_value, "reward_ledger_existing",
                    )
                    if owns_conn:
                        conn.commit()
                        conn.close()
                    return True, rejected

                if existing:
                    update_keys = [k for k in data_copy.keys() if k not in (pk, "user_id")]
                    if update_keys:
                        sets = ",".join([f"{k}=?" for k in update_keys])
                        vals = [data_copy[k] for k in update_keys] + [user_id, pk_value]
                        conn.execute(
                            f"UPDATE {server_table} SET {sets} WHERE user_id = ? AND {pk} = ?",
                            vals,
                        )
                else:
                    keys = list(data_copy.keys())
                    vals = [data_copy[k] for k in keys]
                    placeholders = ",".join(["?"] * len(keys))
                    cur = conn.execute(
                        f"INSERT INTO {server_table} ({','.join(keys)}) VALUES ({placeholders})",
                        vals,
                    )
                    if cur.rowcount > 0:
                        is_inserted = True

            if table in {"tasks", "habits"} and data_copy.get("source") == "local":
                RewardConfigService().ensure_item(
                    conn,
                    user_id,
                    "task" if table == "tasks" else "habit",
                    str(data_copy.get("id")),
                    difficulty=data_copy.get("difficulty"),
                )

            self._settle_synced_behavior_in_txn(conn, table, data_copy, user_id)
            if table == "huawei_sleep_data" and ("morning_diary" in data_copy or "evening_diary" in data_copy):
                self._sleep_rewards.reconcile_diary_completion_in_txn(conn, user_id, data_copy["date"])
            if table == "study_sessions" and pk_value is not None:
                ATimeLoggerBackupStore.enqueue_in_tx(conn, user_id, str(pk_value), _now())

            if table == "reward_ledger" and is_inserted:
                self._rebuild_wallet_snapshot_in_txn(conn, user_id)

            if owns_conn:
                conn.commit()

            if owns_conn:
                conn.close()
            return True, rejected
        except Exception as e:
            if conn is not None and owns_conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
            elif conn is not None:
                raise
            logger.error(f"upsert server_{table} (user={user_id}): {e}")
            return False, [{"table": table, "record_id": data.get("id") or data.get("ext_id") or data.get("key"), "reason": str(e)}]

    def _settle_synced_behavior_in_txn(self, conn: sqlite3.Connection, table: str, record: dict, user_id: int):
        if table == "exercise_daily_logs":
            if str(record.get("plan_version") or "") == "v4":
                try:
                    from .server import _beijing_now, _exercise_v4
                except (ImportError, ValueError):
                    from server import _beijing_now, _exercise_v4
                _exercise_v4().settle(conn, user_id, str(record.get("date") or _cst_today())[:10], _beijing_now())
            return

        if table == "exercise_diet_checkins":
            try:
                from .server import _beijing_now, _exercise_v4
            except (ImportError, ValueError):
                from server import _beijing_now, _exercise_v4
            _exercise_v4().set_diet(conn, user_id, str(record.get("date") or _cst_today())[:10],
                str(record.get("rule_key") or ""), str(record.get("status") or "pending"),
                record.get("occurred_at"), _beijing_now())
            return
        if table == "exercise_checkins":
            # 客户端通常通过通用 outbox 推送打卡，而不是调用 exercise/checkin API；
            # 两条路径必须都生成同一份服务端权威单项评分事实。
            try:
                from .server import _exercise_day_key, _exercise_plan_definition, _exercise_score, _persist_exercise_item_scores
            except (ImportError, ValueError):
                from server import _exercise_day_key, _exercise_plan_definition, _exercise_score, _persist_exercise_item_scores
            target_date = str(record.get("date") or _cst_today())[:10]
            plan_version = str(record.get("plan_version") or "v0")
            if plan_version == "v4":
                try:
                    from .server import _beijing_now, _exercise_v4
                except (ImportError, ValueError):
                    from server import _beijing_now, _exercise_v4
                _exercise_v4().settle(conn, user_id, target_date, _beijing_now())
                return
            day_key = _exercise_day_key(target_date)
            items = [dict(row) for row in conn.execute(
                "SELECT id,day_key,variant,section,sort_order,name,sets,intensity,color,tags_json FROM server_exercise_plan_items WHERE user_id=? AND plan_version=? AND day_key=? AND is_active=1 ORDER BY variant,sort_order",
                (user_id, plan_version, day_key),
            ).fetchall()]
            checkins = [dict(row) for row in conn.execute(
                "SELECT * FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=?",
                (user_id, target_date, plan_version),
            ).fetchall()]
            score = _exercise_score(items, checkins, _exercise_plan_definition(conn, user_id, plan_version), day_key, target_date)
            _persist_exercise_item_scores(conn, user_id, target_date, plan_version, score, _now())
            return

        if table == "learning_tasks":
            status = int(record.get("status") or 0)
            target_date = str(record.get("due_date") or record.get("updated_at") or _cst_today())[:10]
            event_key = self._reward_settlement.completion_event_key(
                "learning_task", record.get("id"), target_date, record.get("updated_at")
            )
            if status != 2:
                deleted = self._reward_settlement.remove_state_ledgers_in_txn(
                    conn, user_id, record.get("id"), ("learning_checkin",), target_date
                )
                deleted.extend(self._reward_settlement.remove_task_unlocks_in_txn(
                    conn, user_id, "learning_task", record.get("id"), event_key
                ))
                self._publish_reward_changes_in_txn(conn, user_id, deleted, None)
                return
            title = record.get("title") or record.get("id") or "学习任务"
            reward = self._reward_rules.calculate_learning_success(user_id, record.get("id"), title)
            ledger_id = self._reward_settlement.settle_learning_success_in_txn(
                conn, user_id, record.get("id"), reward.title, reward.amount, target_date
            )
            self._reward_settlement.grant_task_unlocks_in_txn(
                conn, user_id, "learning_task", record.get("id"), event_key, title, target_date
            )
            self._publish_reward_changes_in_txn(conn, user_id, [], ledger_id)
            return

        if table == "tasks":
            status = int(record.get("status") or 0)
            target_date = str(record.get("updated_at") or record.get("due_date") or _cst_today())[:10]
            event_key = self._reward_settlement.completion_event_key(
                "checklist_task", record.get("id"), target_date, record.get("updated_at")
            )
            if status != 2:
                deleted = self._reward_settlement.remove_state_ledgers_in_txn(
                    conn, user_id, record.get("id"), ("task_complete",)
                )
                deleted.extend(self._reward_settlement.remove_task_unlocks_in_txn(
                    conn, user_id, "checklist_task", record.get("id"), event_key
                ))
                self._publish_reward_changes_in_txn(conn, user_id, deleted, None)
                return
            title = record.get("title") or record.get("id") or "清单"
            reward = self._reward_rules.calculate_task_success(user_id, record.get("id"), title)
            ledger_id = self._reward_settlement.settle_task_success_in_txn(
                conn, user_id, record.get("id"), reward.title, reward.amount, target_date
            )
            unlock_ledger_ids = self._reward_settlement.grant_task_unlocks_in_txn(
                conn, user_id, "checklist_task", record.get("id"), event_key, title, target_date
            )
            self._publish_reward_changes_in_txn(conn, user_id, [], ledger_id)
            for unlock_ledger_id in unlock_ledger_ids:
                self._publish_reward_changes_in_txn(conn, user_id, [], unlock_ledger_id)
            return

        if table == "habit_checkins":
            habit_id = record.get("habit_id")
            if not habit_id:
                return
            habit = conn.execute(
                "SELECT name, difficulty FROM server_habits WHERE user_id = ? AND id = ?",
                (user_id, habit_id),
            ).fetchone()
            title = record.get("habit_name") or (habit["name"] if habit else None) or habit_id
            difficulty = (habit["difficulty"] if habit else None) or "easy"
            target_date = str(record.get("checkin_date") or record.get("date") or _cst_today())[:10]
            self._replace_habit_reward_in_txn(
                conn, user_id, habit_id, title, difficulty, target_date, int(record.get("status") or 0), record.get("checkin_time")
            )

    # ======================== 冲突仲裁 ========================

    def _resolve(self, local: dict | None, remote: dict) -> str:
        if not local:
            return "pull"
        lt = _parse_ts(local.get("updated_at"))
        rt = _parse_ts(remote.get("updated_at"))
        return "pull" if rt > lt else "push" if lt > rt else "skip"

    # ======================== SSE 订阅 ========================

    def subscribe(self, queue: asyncio.Queue, user_id: int | None = None):
        self._subscribers.append((queue, user_id))

    def unsubscribe(self, queue: asyncio.Queue):
        try:
            self._subscribers = [item for item in self._subscribers if item[0] is not queue]
        except ValueError:
            pass

    def _notify_clients(self, tables: list[str], user_id: int | None = None):
        server_version = None
        if user_id is not None:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT current_version FROM server_version_counters WHERE user_id=?", (user_id,)
                ).fetchone()
                server_version = int(row["current_version"]) if row else 0
            finally:
                conn.close()
        msg = {"event": "changed", "data": json.dumps({"tables": tables, "server_version": server_version})}
        for q, subscriber_user_id in self._subscribers[:]:
            if user_id is not None and subscriber_user_id not in (None, user_id):
                continue
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def notify_timer_state(self, user_id: int, revision: int):
        msg = {"event": "timer-state-changed", "data": json.dumps({"revision": revision})}
        for q, subscriber_user_id in self._subscribers[:]:
            if subscriber_user_id != user_id:
                continue
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def get_duplicate_version_diagnostics(self, user_id: int, limit: int = 20) -> dict:
        """只读定位同一来源重复写入的候选 no-op 版本，绝不清理日志。"""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT table_name,record_id,COALESCE(device_id,'server') AS source,
                          COUNT(*) AS write_count,
                          COUNT(*) - COUNT(DISTINCT changed_fields_json) AS no_op_count
                   FROM server_change_log WHERE user_id=?
                   GROUP BY table_name,record_id,COALESCE(device_id,'server')
                   HAVING no_op_count>0 ORDER BY no_op_count DESC,write_count DESC LIMIT ?""",
                (user_id, max(1, min(int(limit), 100))),
            ).fetchall()
            entities = [dict(row) for row in rows]
            return {"user_id": user_id, "entities": entities, "no_op_count": sum(row["no_op_count"] for row in rows)}
        finally:
            conn.close()

    def notify_completed_session(self, user_id: int):
        """通知同一用户拉取已提交的权威时间记录，不传递记录正文。"""
        msg = {"event": "changed", "data": json.dumps({"tables": ["study_sessions"]})}
        for q, subscriber_user_id in self._subscribers[:]:
            if subscriber_user_id != user_id:
                continue
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    notify_timer_lease = notify_timer_state

    def _has_change_id(self, user_id: int, change_id: str | None) -> bool:
        if not change_id:
            return False
        try:
            conn = self._conn()
            row = conn.execute(
                "SELECT 1 FROM server_change_log WHERE user_id = ? AND change_id = ?",
                (user_id, change_id),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def _record_change_id(
        self,
        user_id: int,
        change_id: str | None,
        device_id: str | None,
        table: str,
        record_id: str,
        operation: str,
        status: str = "applied",
        error: str | None = None,
        conn: sqlite3.Connection | None = None,
    ):
        if not change_id:
            return
        if conn is not None:
            entity_type = table[:-1] if table.endswith("s") else table
            if hasattr(self.db, "write_server_change"):
                self.db.write_server_change(
                    user_id, entity_type, str(record_id), operation, {},
                    change_id=change_id, device_id=device_id, table_name=server_table_for(table),
                    status=status, error=error, conn=conn,
                )
                return
            now = _now()
            conn.execute(
                "INSERT INTO server_version_counters (user_id, current_version, updated_at) VALUES (?, 0, ?) "
                "ON CONFLICT(user_id) DO NOTHING",
                (user_id, now),
            )
            conn.execute(
                "UPDATE server_version_counters SET current_version = current_version + 1, updated_at = ? WHERE user_id = ?",
                (now, user_id),
            )
            version = conn.execute(
                "SELECT current_version FROM server_version_counters WHERE user_id = ?", (user_id,)
            ).fetchone()["current_version"]
            conn.execute(
                """INSERT INTO server_change_log (
                    user_id, server_version, change_id, device_id, table_name, record_id,
                    entity_type, entity_id, operation, changed_fields_json, status, error, changed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, version, change_id, device_id, server_table_for(table), str(record_id), entity_type,
                 str(record_id), operation, "{}", status, error, now, now),
            )
            return
        try:
            with self._transact() as conn:
                server_version = self.db.allocate_server_version(user_id, conn)
                entity_type = table[:-1] if table.endswith("s") else table
                now = _now()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO server_change_log (
                        user_id, server_version, change_id, device_id, table_name, record_id,
                        entity_type, entity_id, operation, changed_fields_json,
                        status, error, changed_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        server_version,
                        change_id,
                        device_id,
                        table,
                        str(record_id),
                        entity_type,
                        str(record_id),
                        operation,
                        "{}",
                        status,
                        error,
                        now,
                        now,
                    ),
                )
        except Exception as e:
            logger.warning("记录 change_id 失败 user=%s change_id=%s: %s", user_id, change_id, e)

    def _record_conflict(
        self,
        user_id: int,
        device_id: str | None,
        table: str,
        record_id: str,
        field_name: str | None,
        client_value,
        server_value,
        strategy: str,
        result: str,
        conn: sqlite3.Connection | None = None,
    ):
        try:
            if conn is not None:
                conn.execute(
                    """
                    INSERT INTO server_sync_conflicts (
                        user_id, device_id, table_name, record_id, field_name,
                        client_value, server_value, strategy, result, resolution, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        device_id,
                        table,
                        str(record_id),
                        field_name,
                        json.dumps(client_value, ensure_ascii=False, default=str),
                        json.dumps(server_value, ensure_ascii=False, default=str),
                        strategy,
                        result,
                        f"{strategy}:{result}",
                        _now(),
                    ),
                )
                return
            with self._transact() as txn:
                txn.execute(
                    """
                    INSERT INTO server_sync_conflicts (
                        user_id, device_id, table_name, record_id, field_name,
                        client_value, server_value, strategy, result, resolution, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, device_id, table, str(record_id), field_name,
                        json.dumps(client_value, ensure_ascii=False, default=str),
                        json.dumps(server_value, ensure_ascii=False, default=str),
                        strategy, result, f"{strategy}:{result}", _now(),
                    ),
                )
        except Exception as e:
            logger.warning("记录同步冲突失败 user=%s table=%s record=%s: %s", user_id, table, record_id, e)

    def _prepare_habit_checkin_idempotent(self, record: dict, user_id: int) -> dict:
        if not record.get("habit_id") or not record.get("checkin_date"):
            return record
        conn = self._conn()
        try:
            existing = conn.execute(
                """
                SELECT id FROM server_habit_checkins
                WHERE user_id = ? AND habit_id = ? AND checkin_date = ?
                """,
                (user_id, record.get("habit_id"), record.get("checkin_date")),
            ).fetchone()
            if existing:
                prepared = dict(record)
                prepared["id"] = existing["id"]
                return prepared
            return record
        finally:
            conn.close()

    def _apply_task_field_policy(
        self, local: dict | None, record: dict, device_id: str | None, user_id: int, conn: sqlite3.Connection | None = None
    ) -> tuple[dict, list[dict]]:
        if not local:
            return record, []
        if local.get("deleted_at") and not record.get("restore"):
            self._record_conflict(
                user_id,
                device_id,
                "tasks",
                str(record.get("id")),
                "deleted_at",
                record,
                {"deleted_at": local.get("deleted_at")},
                "tombstone_wins",
                "rejected_stale_update", conn,
            )
            return record, [{"table": "tasks", "record_id": record.get("id"), "reason": "tombstone_protected"}]

        merged = dict(local)
        changed_fields = []
        for field in ("title", "status", "priority", "due_date", "tags", "raw_json", "category_id"):
            if field in record and record.get(field) != local.get(field):
                merged[field] = record.get(field)
                changed_fields.append(field)
        if changed_fields and _parse_ts(local.get("updated_at")) > _parse_ts(record.get("updated_at")):
            for field in changed_fields:
                self._record_conflict(
                    user_id,
                    device_id,
                    "tasks",
                    str(record.get("id")),
                    field,
                    record.get(field),
                    local.get(field),
                    "field_merge",
                    "client_field_applied_over_newer_server_row", conn,
                )
        merged["id"] = record.get("id")
        merged["updated_at"] = record.get("updated_at") or _now()
        return merged, []

    def _apply_tombstone(
        self,
        table: str,
        record: dict,
        user_id: int,
        conn: sqlite3.Connection | None = None,
    ) -> tuple[bool, list[dict]]:
        if table in {"learning_objectives", "learning_krs", "learning_tasks"}:
            pk = self._pk_for_table(table)
            pk_value = record.get(pk)
            if pk_value is None:
                return False, [{"table": table, "record_id": None, "reason": "missing_primary_key"}]
            try:
                if conn is None:
                    with self._transact() as txn:
                        return self._apply_tombstone(table, record, user_id, txn)
                else:
                    if table == "learning_objectives":
                        kr_rows = conn.execute(
                            "SELECT id FROM server_learning_krs WHERE user_id = ? AND objective_id = ?",
                            (user_id, pk_value),
                        ).fetchall()
                        for kr_row in kr_rows:
                            conn.execute(
                                "DELETE FROM server_learning_tasks WHERE user_id = ? AND kr_id = ?",
                                (user_id, kr_row["id"]),
                            )
                        conn.execute(
                            "DELETE FROM server_learning_krs WHERE user_id = ? AND objective_id = ?",
                            (user_id, pk_value),
                        )
                    elif table == "learning_krs":
                        conn.execute(
                            "DELETE FROM server_learning_tasks WHERE user_id = ? AND kr_id = ?",
                            (user_id, pk_value),
                        )
                    conn.execute(f"DELETE FROM {server_table_for(table)} WHERE user_id = ? AND {pk} = ?", (user_id, pk_value))
                return True, []
            except Exception as e:
                return False, [{"table": table, "record_id": pk_value, "reason": str(e)}]
        if table != "tasks":
            return self.upsert(table, record, user_id, conn=conn)
        now = record.get("deleted_at") or record.get("updated_at") or _now()
        tombstone = dict(record)
        tombstone["deleted_at"] = now
        tombstone["updated_at"] = now
        tombstone["status"] = tombstone.get("status", 0)
        return self.upsert(table, tombstone, user_id, conn=conn)

    def _select_push_delta(self, table: str, record: dict, action: str = "push") -> tuple[dict | None, dict | None]:
        record_id = str(record.get("id") or "").strip()
        if not record_id:
            logger.warning(
                "TickTick push 增量缺少记录ID table=%s action=%s record_keys=%s",
                table, action, sorted(record.keys()),
            )
            return None, {"table": table, "record_id": None, "reason": "missing_id", "action": action}
        return {"table": table, "record_id": record_id, "record": record, "action": action}, None

    # ======================== 客户端 Push ========================

    @traced("sync.handle_push")
    async def handle_push(self, operations: list, user_id: int, sync_scope: str = "core") -> dict:
        """
        接收客户端推送 → 按表分流 → 即时同步滴答清单 → SSE 广播。
        清单&习惯类：即时推送+回读滴答清单
        其他类：仅落库+广播
        """
        accepted = 0
        ticktick_items: list[dict] = []
        changed_tables: set[str] = set()
        rejected: list[dict] = []
        operation_results: list[dict] = []
        analysis_claims: list[str] = []
        scope = "checklist" if sync_scope == "checklist" else "core"
        provider_blocked = 0

        # 明确客户端 outbox 操作已经携带业务意图；不在 push 前做全量 provider 对账。
        explicit_client_ops = all(op.get("change_id") or op.get("op_id") for op in operations)
        tables_in_push = {
            op.get("table") for op in operations if op.get("table") and not (
                op.get("table") in {"tasks", "habits"}
                and str((op.get("record") or op.get("payload") or op.get("data") or {}).get("source") or "") == "local"
            )
        }
        if scope == "checklist" and not explicit_client_ops and tables_in_push.intersection(TICKTICK_TABLES):
            settings = self._get_ticktick_settings(user_id)
            if settings.enabled and settings.access_token:
                logger.info("[sync_push] Pre-pull from TickTick before arbitration user_id=%s tables=%s", user_id, tables_in_push)
                try:
                    TickTickClient = _get_ticktick_client_class()
                    async with TickTickClient(
                        settings.access_token,
                        settings.host,
                        verify_tls=settings.verify_tls,
                        timeout_seconds=settings.timeout_seconds,
                    ) as client:
                        if "tasks" in tables_in_push:
                            await self._pull_tasks(client, user_id)
                        if tables_in_push.intersection({"habits", "habit_checkins"}):
                            await self._pull_habits(client, user_id)
                except Exception as e:
                    logger.warning("[sync_push] Pre-pull from TickTick failed user_id=%s: %s", user_id, e)
        for op in operations:
            table = op.get("table", "")
            change_id = op.get("change_id") or op.get("op_id")
            device_id = op.get("device_id")
            operation = op.get("operation", "upsert")
            
            # 只接受 payload 格式，不兼容 records 数组
            single_record = op.get("record") or op.get("payload")
            if not single_record or not isinstance(single_record, dict):
                rejected.append({"table": table, "reason": "missing_payload"})
                operation_results.append({"change_id": change_id, "status": "rejected", "reason": "missing_payload"})
                continue
            records = [single_record]

            provider_bound = table in {"tasks", "habits"} and str(single_record.get("source") or "ticktick") != "local"
            if provider_bound and scope != "checklist":
                provider_blocked += 1
                rejected.append({"table": table, "record_id": single_record.get("id"), "reason": "checklist_scope_required"})
                operation_results.append({"change_id": change_id, "status": "rejected", "record_id": single_record.get("id"), "reason": "checklist_scope_required"})
                continue

            if table == "system_config" and single_record.get("key") == "atimelogger_config":
                rejected.append({"table": table, "record_id": "atimelogger_config", "reason": "server_owned_atimelogger_config"})
                operation_results.append({
                    "change_id": change_id,
                    "status": "rejected",
                    "record_id": "atimelogger_config",
                    "reason": "server_owned_atimelogger_config",
                })
                continue
            if table == "system_config" and _is_blocked_sync_config(single_record.get("key")):
                key = str(single_record.get("key") or "")
                rejected.append({"table": table, "record_id": key, "reason": "account_scoped_config"})
                operation_results.append({
                    "change_id": change_id, "status": "rejected", "record_id": key,
                    "reason": "account_scoped_config",
                })
                continue
            
            management_owned = {"management_plans", "management_plan_revisions",
                                "management_plan_bindings", "management_plan_change_log"}
            if table in {"goals", "rewards", "reward_fragments", "reward_source_bindings", "external_rewards", "user_wallets", "wallet", "wallets", "flash_task_recommendations"} | management_owned:
                for record in records:
                    reason = "server_owned_wallet" if table in {"user_wallets", "wallet", "wallets"} else f"server_owned_{table}"
                    rejected.append({"table": table, "record_id": record.get("id"), "reason": reason})
                    operation_results.append({"change_id": change_id, "status": "rejected", "reason": reason})
                continue
            if table not in SYNC_TABLE_SET:
                for record in records:
                    rejected.append({"table": table, "record_id": record.get("id"), "reason": "unknown_table"})
                    operation_results.append({"change_id": change_id, "status": "rejected", "reason": "unknown_table"})
                continue
            if is_server_owned(table):
                for record in records:
                    reason = f"server_owned_{table}"
                    rejected.append({"table": table, "record_id": record.get("id"), "reason": reason})
                    operation_results.append({"change_id": change_id, "status": "rejected", "record_id": record.get("id"), "reason": reason})
                continue
            if table == "reward_ledger":
                for record in records:
                    rejected.append({"table": table, "record_id": record.get("id"), "reason": "server_owned_reward_ledger"})
                    operation_results.append({"change_id": change_id, "status": "rejected", "reason": "server_owned_reward_ledger"})
                continue
            if table == "habit_checkins":
                for record in records:
                    rejected.append({
                        "table": table,
                        "record_id": record.get("id"),
                        "reason": "server_authoritative_habit_checkin_command_required",
                    })
                    operation_results.append({
                        "change_id": change_id,
                        "status": "rejected",
                        "record_id": record.get("id"),
                        "reason": "server_authoritative_habit_checkin_command_required",
                    })
                continue
            for record in records:
                if table in {"sleep_command_receipts", "sleep_notification_receipts"}:
                    record["device_id"] = str(device_id or "")
                if table == "habit_checkins":
                    record = self._prepare_habit_checkin_idempotent(record, user_id)
                rid = record.get("id")
                pk_val = record.get("ext_id") if table == "external_rewards" else record.get("key") if table == "system_config" else rid
                if pk_val is None:
                    rejected.append({"table": table, "record_id": None, "reason": "missing_primary_key"})
                    operation_results.append({"change_id": change_id, "status": "rejected", "reason": "missing_primary_key"})
                    continue
                if self._has_change_id(user_id, change_id):
                    accepted += 1
                    operation_results.append({"change_id": change_id, "status": "duplicate", "record_id": str(pk_val)})
                    continue
                if table == "categories":
                    with self._conn() as lookup_conn:
                        local = self._category_record_by_name(lookup_conn, user_id, record.get("name"))
                else:
                    local = self.get_record(table, pk_val, user_id)
                if table == "tasks" and operation == "upsert" and local and local.get("deleted_at"):
                    rejected.append({"table": table, "record_id": pk_val, "reason": "tombstone_protected"})
                    self._record_conflict(
                        user_id,
                        device_id,
                        table,
                        str(pk_val),
                        "deleted_at",
                        record,
                        {"deleted_at": local.get("deleted_at")},
                        "tombstone_wins",
                        "rejected_stale_update",
                    )
                    self._record_change_id(user_id, change_id, device_id, table, str(pk_val), operation, "ignored")
                    operation_results.append({"change_id": change_id, "status": "rejected", "record_id": str(pk_val), "reason": "tombstone_protected"})
                    continue
                outbox_task = bool(op.get("op_id")) and not op.get("change_id") and operation == "upsert"
                if table == "tasks" and str(record.get("source") or "") != "local" and not outbox_task and (
                    operation in ("delete", "archive")
                    or not local
                    or str(record.get("title", "")) != str(local.get("title", ""))
                ):
                    rejected.append({"table": table, "record_id": pk_val, "reason": "task_structure_requires_command"})
                    operation_results.append({"change_id": change_id, "status": "rejected", "record_id": str(pk_val), "reason": "task_structure_requires_command"})
                    continue
                action = "push" if change_id or operation in ("delete", "archive") else self._resolve(local, record)
                if action in ("pull", "push"):
                    try:
                        with self._transact() as txn:
                            if operation in ("delete", "archive"):
                                ok, record_rejections = self._apply_tombstone(table, record, user_id, conn=txn)
                            else:
                                if table == "tasks":
                                    record, policy_rejections = self._apply_task_field_policy(
                                        local, record, device_id, user_id, conn=txn
                                    )
                                    if policy_rejections:
                                        rejected.extend(policy_rejections)
                                        operation_results.append({
                                            "change_id": change_id,
                                            "status": "rejected",
                                            "record_id": str(pk_val),
                                            "reason": policy_rejections[-1].get("reason"),
                                        })
                                        continue
                                ok, record_rejections = self.upsert(table, record, user_id, conn=txn)
                            if not ok:
                                raise RuntimeError(record_rejections[-1].get("reason", "upsert_failed"))
                            if table == "flash_cards" and operation == "upsert" and FlashCardService.claim_analysis(txn, user_id, str(pk_val)):
                                analysis_claims.append(str(pk_val))
                            if table == "flash_cards" and record.get("deleted_at"):
                                txn.execute("UPDATE server_flash_processing_logs SET deleted_at=?,input_text='',prompt_snapshot='',raw_output=NULL,normalized_output=NULL WHERE user_id=? AND flash_card_id=?",
                                            (_now(), user_id, str(pk_val)))
                            canonical_record_id = self._canonical_record_id_for_change(
                                table, record, user_id, pk_val, conn=txn
                            )
                            self._record_change_id(
                                user_id, change_id, device_id, table, canonical_record_id, operation, conn=txn
                            )
                    except Exception as exc:
                        ok = False
                        record_rejections = [{"table": table, "record_id": pk_val, "reason": str(exc)}]

                    rejected.extend(record_rejections)
                    if ok:
                        if table == "study_sessions" and self._goal_store:
                            affected_dates = {
                                str(value)[:10] for value in (
                                    (local or {}).get("date"), record.get("date"), session_business_date(
                                        record.get("start_time"), record.get("end_time"), "",
                                    )
                                ) if value
                            }
                            if self._goal_store.recalculate_goal_periods(user_id, affected_dates):
                                changed_tables.update({"external_rewards", "reward_ledger", "user_wallets"})
                        accepted += 1
                        changed_tables.add(table)
                        operation_results.append({"change_id": change_id, "status": "accepted", "record_id": canonical_record_id})
                        if table in {"exercise_daily_logs", "exercise_checkins", "learning_tasks", "habit_checkins"}:
                            changed_tables.add("reward_ledger")
                        if table in {"exercise_daily_logs", "exercise_checkins", "learning_tasks", "habit_checkins"}:
                            changed_tables.add("user_wallets")
                        if table == "exercise_checkins":
                            changed_tables.add("exercise_item_scores")
                        if table in {"exercise_checkins", "exercise_diet_checkins", "exercise_daily_logs"}:
                            changed_tables.update({"exercise_item_scores", "exercise_settlements", "reward_ledger", "user_wallets"})
                        # Task-1 FIX: 落库成功即入队转发 TickTick，与仲裁结果（action）解耦。
                        # 原 Bug：action=="push" 门控错误——_resolve 返回的 "pull"/"push" 是时间戳
                        # 仲裁语义（谁的数据更新），不是"是否转发 TickTick"的标志。客户端完成
                        # 任务时 updated_at 更新，rt>lt 故 action="pull"，门控永不满足，
                        # ticktick_items 始终为空，TickTick 从未被调用。
                        task_status_changed = table == "tasks" and int(record.get("status") or 0) != int((local or {}).get("status") or 0)
                        if str(record.get("source") or "") != "local" and ((table in TICKTICK_TABLES and table != "tasks" and operation not in ("delete", "archive")) or task_status_changed):
                            logger.info(
                                "[sync_push] TickTick enqueue table=%s record_id=%s action=%s",
                                table, pk_val, action,
                            )
                            delta, delta_error = self._select_push_delta(table, record, action)
                            if delta_error:
                                logger.warning(
                                    "[sync_push] TickTick delta build failed table=%s record_id=%s error=%s",
                                    table, pk_val, delta_error,
                                )
                                rejected.append(delta_error)
                            else:
                                delta["change_id"] = change_id
                                ticktick_items.append(delta)
                    else:
                        reason = record_rejections[-1].get("reason") if record_rejections else "upsert_failed"
                        logger.warning(
                            "[sync_push] upsert failed table=%s record_id=%s reason=%s",
                            table, pk_val, reason,
                        )
                        operation_results.append({"change_id": change_id, "status": "rejected", "record_id": str(pk_val), "reason": reason})
                elif action == "skip":
                    logger.info("[sync_push] skipped table=%s record_id=%s reason=resolve_skip", table, pk_val)
                    operation_results.append({"change_id": change_id, "status": "skipped", "record_id": str(pk_val)})

        # 清单&习惯类 → 即时推送 TickTick；明确任务变更不再等待全量 provider 回读。
        provider_push = None
        if scope == "checklist" and ticktick_items:
            provider_push = await self._push_and_sync_ticktick(ticktick_items, list(changed_tables), user_id)
            for push_result in provider_push.get("results", []):
                if push_result.get("ok"):
                    continue
                change_id = push_result.get("change_id")
                reason = push_result.get("error") or "provider_push_failed"
                rejected.append({
                    "table": push_result.get("table"),
                    "record_id": push_result.get("record_id"),
                    "reason": reason,
                })
                for op_result in operation_results:
                    if op_result.get("change_id") == change_id:
                        op_result["status"] = "rejected"
                        op_result["reason"] = reason
                        break
        # 其他类 → 仅 SSE 广播
        else:
            non_tt = [t for t in changed_tables if t not in TICKTICK_TABLES]
            if non_tt:
                self._notify_clients(non_tt, user_id)

        self._record_sync_state(user_id, "client", "client_to_server", "success", merged_count=accepted)

        logger.info(
            "[sync_push] summary user_id=%s accepted=%s ticktick_forwarded=%s rejected_ops=%s",
            user_id, accepted, len(ticktick_items), len(rejected),
        )
        if rejected:
            logger.warning("[sync_push] rejected details: %s", rejected)

        return {
            "accepted": accepted,
            "server_time": _now(),
            "changed_tables": list(changed_tables),
            "rejected": rejected,
            "operation_results": operation_results,
            "provider_push": provider_push,
            "provider_requested": bool(tables_in_push.intersection(TICKTICK_TABLES)),
            "provider_executed": provider_push is not None,
            "provider_blocked": provider_blocked,
            "analysis_claims": analysis_claims,
        }

    async def _push_and_sync_ticktick(self, items: list[dict], changed_tables: list[str], user_id: int):
        """推送 TickTick；任务类走快速路径，不等待全量 provider 回读。"""
        settings = self._get_ticktick_settings(user_id)
        if not settings.enabled:
            logger.info("TickTick sync skipped: missing access_token user_id=%s", user_id)
            self._notify_clients(changed_tables)
            self._record_sync_state(
                user_id,
                "ticktick",
                "server_to_ticktick",
                "error",
                "ticktick_not_configured",
                diagnostics={"provider_push": {"ok": False, "error": "ticktick_not_configured"}},
            )
            return {"ok": False, "error": "ticktick_not_configured", "requests": 0, "results": []}
        try:
            TickTickClient = _get_ticktick_client_class()
            push_results = []

            async with TickTickClient(
                settings.access_token,
                settings.host,
                verify_tls=settings.verify_tls,
                timeout_seconds=settings.timeout_seconds,
            ) as client:
                logger.info(
                    "[sync_push] Forwarding %s item(s) to TickTick user_id=%s tables=%s",
                    len(items), user_id, list({i["table"] for i in items}),
                )
                # 1. 逐条推送。任务类以本地 outbox 为权威，不额外拉 completed 列表确认。
                for item in items:
                    push_result = await self._push_one_ticktick(client, item["table"], item["record"], user_id)
                    push_result["change_id"] = item.get("change_id")
                    if not push_result.get("ok"):
                        push_results.append(push_result)
                        logger.warning(
                            "[sync_push] TickTick push failed user=%s table=%s record_id=%s error=%s",
                            user_id, item["table"], item["record"].get("id"), push_result.get("error"),
                        )
                        continue
                    verified = True if item["table"] == "tasks" else await self._verify_ticktick(client, item["table"], item["record"], user_id)
                    push_result["verified"] = verified
                    push_results.append(push_result)
                    if verified:
                        logger.info(
                            "[sync_push] TickTick push+verify ok user=%s table=%s record_id=%s action=%s",
                            user_id, item["table"], item["record"].get("id"), push_result.get("action"),
                        )
                    else:
                        logger.warning(
                            "[sync_push] TickTick push ok but verify failed user=%s table=%s record_id=%s",
                            user_id, item["table"], item["record"].get("id"),
                        )

                # 2. 任务变更不触发全量 provider 回读；习惯只回读习惯范围。
                successful_tables = {item["table"] for item, result in zip(items, push_results) if result.get("ok")}
                if any(table != "tasks" for table in successful_tables):
                    await self._trigger_ticktick_pull(client, list(successful_tables), user_id)
                else:
                    self._notify_clients(changed_tables)
                provider_push_ok = all(result.get("ok") for result in push_results)
                self._record_sync_state(
                    user_id,
                    "ticktick",
                    "server_to_ticktick",
                    "success" if provider_push_ok else "error",
                    None if provider_push_ok else "provider_push_failed",
                    merged_count=len(items),
                    diagnostics={"provider_push": {"ok": provider_push_ok, "requests": len(items), "results": push_results}},
                )
                return {"ok": provider_push_ok, "requests": len(items), "results": push_results}

        except Exception as e:
            logger.error(f"_push_and_sync_ticktick 异常 (user={user_id}): {e}")
            self._record_sync_state(
                user_id,
                "ticktick",
                "server_to_ticktick",
                "error",
                str(e),
                diagnostics={"provider_push": {"ok": False, "error": str(e)}},
            )
            self._notify_clients(changed_tables)
            return {"ok": False, "error": str(e), "requests": len(items), "results": []}

    async def _trigger_ticktick_pull(self, client, changed_tables: list[str], user_id: int):
        """状态机合并去重拉取，防止多客户端并发推送导致 TickTick 漏同步"""
        async with self._pull_lock:
            if self._pull_running:
                self._pull_requested = True
                return
            self._pull_running = True

        try:
            while True:
                self._pull_requested = False
                await asyncio.sleep(0.5)  # 聚合 0.5s 内的推送
                requested_tables = set(changed_tables or [])
                pull_tasks = bool(requested_tables & {"tasks"})
                pull_habits = bool(requested_tables & {"habits", "habit_checkins"})
                if not pull_tasks and not pull_habits:
                    pull_tasks = True
                    pull_habits = True
                task_stats = await self._pull_tasks(client, user_id) if pull_tasks else {}
                habit_stats = await self._pull_habits(client, user_id) if pull_habits else {}
                merged_count = 0
                for stats in (task_stats, habit_stats):
                    if isinstance(stats, dict):
                        merged_count += sum(
                            v for key, v in stats.items()
                            if isinstance(v, int) and key.endswith("_changes")
                        )
                self._record_sync_state(
                    user_id,
                    "ticktick",
                    "ticktick_to_server",
                    "success",
                    merged_count=merged_count,
                    diagnostics={"tasks": task_stats, "habits": habit_stats},
                )

                # SSE 广播
                provider_tables = []
                if pull_tasks:
                    provider_tables.append("tasks")
                    provider_tables.append("reward_ledger")
                if pull_habits:
                    provider_tables.extend(["habits", "habit_checkins", "reward_ledger", "user_wallets"])
                all_tables = list(set(changed_tables + provider_tables))
                self._notify_clients(all_tables)

                async with self._pull_lock:
                    if not self._pull_requested:
                        self._pull_running = False
                        break
        except Exception as e:
            logger.error(f"合并拉取 TickTick 异常 (user={user_id}): {e}")
            self._record_sync_state(user_id, "ticktick", "ticktick_to_server", "error", str(e))
            async with self._pull_lock:
                self._pull_running = False

    async def _push_one_ticktick(self, client: "TickTickClient", table: str, rec: dict, user_id: int) -> dict:
        """单条推送到滴答清单，入口/出口均打日志，失败时输出完整上下文"""
        try:
            if table == "tasks":
                tid = str(rec.get("id", ""))
                raw_project_id = rec.get("project_id") or rec.get("projectId")
                
                # 1. 优先从 rec.raw_json 恢复
                if not raw_project_id and rec.get("raw_json"):
                    try:
                        import json
                        raw_data = json.loads(rec["raw_json"])
                        raw_project_id = raw_data.get("projectId") or raw_data.get("project_id")
                    except Exception:
                        pass
                
                # 2. 如果还没有，从数据库查询恢复
                if not raw_project_id:
                    with self._conn() as conn:
                        row = conn.execute("SELECT project_id, raw_json FROM tasks WHERE id = ? AND user_id = ?", (tid, user_id)).fetchone()
                        if row:
                            raw_project_id = row[0]
                            if not raw_project_id and row[1]:
                                try:
                                    import json
                                    raw_data = json.loads(row[1])
                                    raw_project_id = raw_data.get("projectId") or raw_data.get("project_id")
                                except Exception:
                                    pass

                if not raw_project_id:
                    logger.warning(
                        "[push_one] tasks 缺少 project_id 且无法从 db/raw_json 恢复，拒绝推送 user=%s task_id=%s record_keys=%s",
                        user_id, tid, sorted(rec.keys()),
                    )
                    return {"table": table, "record_id": tid, "ok": False, "error": "missing_project_id"}
                
                project_id = str(raw_project_id)
                if not tid:
                    logger.warning(
                        "[push_one] tasks 缺少 task_id user=%s status=%s record_keys=%s",
                        user_id, rec.get("status"), sorted(rec.keys()),
                    )
                    return {"table": table, "record_id": None, "ok": False, "error": "missing_id"}
                status = rec.get("status")
                logger.info(
                    "[push_one] tasks start user=%s task_id=%s project_id=%s status=%s",
                    user_id, tid, project_id, status,
                )
                if status == 2:
                    await client.complete_task(project_id, tid)
                    logger.info("[push_one] tasks ok action=complete_task user=%s task_id=%s", user_id, tid)
                    return {"table": table, "record_id": tid, "ok": True, "action": "complete_task"}
                if status == 0:
                    await client.update_task(project_id, tid, {"status": 0})
                    logger.info("[push_one] tasks ok action=update_task user=%s task_id=%s", user_id, tid)
                    return {"table": table, "record_id": tid, "ok": True, "action": "update_task"}
                logger.warning(
                    "[push_one] tasks 非法 status user=%s task_id=%s status=%s",
                    user_id, tid, status,
                )
                return {"table": table, "record_id": tid, "ok": False, "error": "invalid_task_status"}
            elif table == "habit_checkins":
                hid = _ticktick_provider_habit_id(user_id, rec.get("habit_id"))
                checkin_date = str(rec.get("checkin_date", ""))
                stamp = checkin_date.replace("-", "") if checkin_date else ""
                status = rec.get("status", 0)
                logger.info(
                    "[push_one] habit_checkins start user=%s habit_id=%s stamp=%s status=%s",
                    user_id, hid, stamp, status,
                )
                if hid and stamp and not str(hid).startswith("local_"):
                    value = 1.0 if status == 2 else 0.0
                    await client.checkin_habit(hid, stamp, status, value)
                    logger.info("[push_one] habit_checkins ok user=%s habit_id=%s stamp=%s", user_id, hid, stamp)
                    return {"table": table, "record_id": rec.get("id"), "ok": True, "action": "checkin_habit"}
                logger.warning(
                    "[push_one] habit_checkins 跳过 user=%s habit_id=%s stamp=%s hid_is_local=%s",
                    user_id, hid, stamp, str(hid or "").startswith("local_"),
                )
            logger.warning(
                "[push_one] 缺少必要字段 user=%s table=%s record_id=%s record_keys=%s",
                user_id, table, rec.get("id"), sorted(rec.keys()),
            )
            return {"table": table, "record_id": rec.get("id"), "ok": False, "error": "missing_required_fields"}
        except Exception as e:
            logger.warning("[push_one] 异常 user=%s table=%s record_id=%s error=%s", user_id, table, rec.get("id"), e)
            return {"table": table, "record_id": rec.get("id"), "ok": False, "error": str(e)}

    async def _verify_ticktick(self, client: "TickTickClient", table: str, rec: dict, user_id: int) -> bool:
        """回读 TickTick 确认数据一致（指数退避重试 3 次：1s→2s→4s）"""
        try:
            if table == "tasks":
                tid = str(rec.get("id", ""))
                if not tid:
                    return False
                if rec.get("status") != 2:
                    return True  # 不涉及状态变更，无需校验

                for attempt in range(3):
                    delay = 2 ** attempt  # 1s, 2s, 4s
                    logger.info(
                        "[verify_ticktick] tasks attempt=%s/3 delay=%ss task_id=%s user=%s",
                        attempt + 1, delay, tid, user_id,
                    )
                    await asyncio.sleep(delay)
                    completed = await client.get_completed_tasks(
                        datetime.now(CST).replace(hour=0, minute=0, second=0)
                        .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
                    )
                    completed_records, _ = self._completed_task_page_parts(completed)
                    if any(t.get("id") == tid and t.get("status") == 2 for t in completed_records):
                        logger.info("[verify_ticktick] tasks confirmed task_id=%s attempt=%s user=%s", tid, attempt + 1, user_id)
                        return True
                logger.warning("[verify_ticktick] tasks not confirmed after 3 attempts task_id=%s user=%s", tid, user_id)
                return False

            elif table == "habit_checkins":
                return True  # 习惯打卡 TickTick 同步后暂不回读（轻量处理）

            return True
        except Exception as e:
            logger.warning(f"回读确认失败 [{table}] (user={user_id}): {e}")
            return False

    @staticmethod
    def _completed_task_page_parts(page: dict | list) -> tuple[list[dict], dict | None]:
        """Accept the normalized client contract while preserving legacy one-page test clients."""
        if isinstance(page, list):
            return page, None
        if not isinstance(page, dict) or not isinstance(page.get("records"), list):
            raise ValueError("completed_page_invalid_contract")
        continuation = page.get("next_page")
        if continuation is not None and (not isinstance(continuation, dict) or not continuation):
            raise ValueError("completed_page_invalid_continuation")
        return page["records"], continuation

    # ======================== 客户端 Pull ========================

    @traced("sync.handle_pull")
    async def handle_pull(self, since: str | None, user_id: int, request_id: str | None = None) -> dict:
        started = _time.perf_counter()
        running_reward_snapshot = self._running_reward_snapshot(user_id)
        if running_reward_snapshot:
            old_wallets = running_reward_snapshot["tables"].get("server_user_wallets") or []
            balance = float(old_wallets[0]["balance"]) if old_wallets else 0.0
            return {
                "tables": {}, "management_plans": self._management_plan_snapshot(user_id),
                "wallet": {"balance": balance}, "server_time": since or "1970-01-01 00:00:00",
                "diagnostics": {"request_id": request_id, "reward_rebuild_in_progress": True},
                "sync_state": self._get_sync_state_map(user_id),
            }
        self._expire_reward_fragments_for_user(user_id)
        logger.info(
            "[SyncHub] legacy pull start request_id=%s user_id=%s since=%s",
            request_id,
            user_id,
            since,
        )
        tables = {}
        merged_count = 0
        for t in SYNC_TABLES:
            rows = self.get_changes_since(t, since, user_id)
            if rows:
                tables[t] = rows
                merged_count += len(rows)

        # 获取用户最新的钱包资产余额快照，放入响应数据包中一同下发对齐
        try:
            from .store import ServerSleepStore
        except ImportError:
            import sys
            sys.path.append(os.path.dirname(__file__))
            from store import ServerSleepStore
            
        temp_store = ServerSleepStore()
        balance = temp_store.get_user_wallet_balance(user_id)

        self._record_sync_state(user_id, "client", "server_to_client", "success", merged_count=merged_count)
        elapsed_ms = round((_time.perf_counter() - started) * 1000, 2)
        logger.info(
            "[SyncHub] legacy pull finish request_id=%s user_id=%s merged_count=%s table_counts=%s elapsed_ms=%s",
            request_id,
            user_id,
            merged_count,
            {table: len(rows) for table, rows in tables.items()},
            elapsed_ms,
        )
        return {
            "tables": tables,
            "management_plans": self._management_plan_snapshot(user_id),
            "wallet": {
                "balance": balance
            },
            "server_time": _now(),
            "diagnostics": {
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
            },
            "sync_state": self._get_sync_state_map(user_id),
        }

    @traced("sync.handle_pull_by_version")
    async def handle_pull_by_version(self, since_version: int | None, user_id: int, limit: int = PULL_LIMIT_DEFAULT, request_id: str | None = None, include_ledger_snapshot: bool = False) -> dict:
        """按服务端版本流拉取变更；这是新同步协议的主增量路径。"""
        started = _time.perf_counter()
        from_version = int(since_version or 0)
        running_reward_snapshot = self._running_reward_snapshot(user_id)
        if running_reward_snapshot:
            old_wallets = running_reward_snapshot["tables"].get("server_user_wallets") or []
            wallet = old_wallets[0] if old_wallets else {"balance": 0}
            ledger_snapshot = self.get_reward_ledger_snapshot(user_id)
            return {
                "changes": [], "tables": {}, "management_plans": self._management_plan_snapshot(user_id),
                "from_version": from_version, "to_version": from_version, "has_more": False,
                "server_time": _now(), "wallet": {"balance": wallet["balance"]},
                "ledger_snapshot": ledger_snapshot, "reward_rebuild_epoch": ledger_snapshot["epoch"],
                "diagnostics": {"protocol": "server_version", "request_id": request_id,
                                "reward_rebuild_in_progress": True, "cursor_frozen": True},
                "sync_state": self._get_sync_state_map(user_id),
            }
        safe_limit = max(1, min(int(limit or PULL_LIMIT_DEFAULT), PULL_LIMIT_MAX))
        logger.info(
            "[SyncHub] version pull start request_id=%s user_id=%s since_version=%s limit=%s",
            request_id,
            user_id,
            from_version,
            safe_limit,
        )
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT server_version, change_id, device_id, table_name, record_id,
                       entity_type, entity_id, operation, changed_fields_json,
                       status, error, changed_at, created_at
                FROM server_change_log
                WHERE user_id = ?
                  AND server_version IS NOT NULL
                  AND server_version > ?
                ORDER BY server_version ASC
                LIMIT ?
                """,
                (user_id, from_version, safe_limit + 1),
            ).fetchall()
        finally:
            conn.close()

        has_more = len(rows) > safe_limit
        visible_rows = rows[:safe_limit]
        changes = [dict(row) for row in visible_rows]
        to_version = changes[-1]["server_version"] if changes else from_version
        if not changes and from_version > 0 and not include_ledger_snapshot:
            elapsed_ms = round((_time.perf_counter() - started) * 1000, 2)
            return {
                "changes": [], "tables": {}, "from_version": from_version, "to_version": from_version,
                "has_more": False, "server_time": _now(), "wallet": None,
                "diagnostics": {"protocol": "server_version", "request_id": request_id, "elapsed_ms": elapsed_ms,
                                "returned_changes": 0, "snapshot": False, "limit": safe_limit},
                "sync_state": {},
            }
        tables: dict[str, list[dict]] = {}
        if from_version == 0:
            for table in SYNC_TABLES:
                rows_for_table = self.get_changes_since(table, None, user_id)
                if rows_for_table:
                    tables[table] = rows_for_table
            if not changes and tables:
                to_version = self.db.allocate_server_version(user_id)
        record_ids_by_table: dict[str, set[str]] = {}
        for change in changes:
            table = str(change.get("table_name") or "").removeprefix("server_")
            if table in SYNC_TABLE_SET and str(change.get("operation") or "") != "delete" and not (from_version == 0 and table in tables):
                record_ids_by_table.setdefault(table, set()).add(str(change.get("record_id")))
        records_by_table = {table: self.get_records(table, ids, user_id) for table, ids in record_ids_by_table.items()}
        for change in changes:
            raw_table = str(change.get("table_name") or "")
            table = raw_table[7:] if raw_table.startswith("server_") else raw_table
            if table not in SYNC_TABLE_SET:
                continue
            if from_version == 0 and table in tables:
                continue
            operation = str(change.get("operation") or "")
            if operation == "delete":
                payload = {}
                try:
                    payload = json.loads(change.get("changed_fields_json") or "{}")
                except Exception:
                    payload = {}
                tombstone = {
                    **payload,
                    "id": str(change.get("record_id")),
                    "_sync_operation": "delete",
                    "updated_at": change.get("changed_at") or change.get("created_at") or _now(),
                }
                tables.setdefault(table, []).append(tombstone)
                continue
            record = records_by_table.get(table, {}).get(str(change.get("record_id")))
            if record:
                tables.setdefault(table, []).append(record)
        # Multiple device writes to the same natural key can produce several
        # change-log entries in one cursor window.  Return only the final
        # authoritative row per primary key so every client applies one fact.
        for table, rows in list(tables.items()):
            primary_key = primary_key_for(table)
            latest: dict[str, dict] = {}
            unkeyed: list[dict] = []
            for row in rows:
                key = row.get(primary_key)
                if key is None:
                    unkeyed.append(row)
                else:
                    latest[str(key)] = row
            tables[table] = [*latest.values(), *unkeyed]
        dependency_backfilled = self._include_habit_parents_for_checkins(tables, user_id, request_id)
        running_reward_snapshot = self._running_reward_snapshot(user_id)
        wallet = self.get_record("user_wallets", user_id, user_id)
        if running_reward_snapshot:
            old_wallets = running_reward_snapshot["tables"].get("server_user_wallets") or []
            wallet = old_wallets[0] if old_wallets else {"balance": 0}
        epoch_conn = self._conn()
        try:
            epoch_row = epoch_conn.execute(
                "SELECT active_epoch,published_version FROM server_reward_rebuild_epochs WHERE user_id=?", (user_id,),
            ).fetchone()
        finally:
            epoch_conn.close()
        reward_epoch = int(epoch_row["active_epoch"]) if epoch_row else 0
        published_version = int(epoch_row["published_version"]) if epoch_row else 0
        ledger_snapshot = self.get_reward_ledger_snapshot(user_id) if running_reward_snapshot or include_ledger_snapshot or from_version < published_version else None
        self._record_sync_state(user_id, "client", "server_to_client", "success", merged_count=len(changes))
        elapsed_ms = round((_time.perf_counter() - started) * 1000, 2)
        table_counts = {table: len(rows) for table, rows in tables.items()}
        logger.info(
            "[SyncHub] version pull finish request_id=%s user_id=%s from_version=%s to_version=%s returned_changes=%s dependency_backfilled=%s has_more=%s table_counts=%s elapsed_ms=%s",
            request_id,
            user_id,
            from_version,
            to_version,
            len(changes),
            dependency_backfilled,
            has_more,
            table_counts,
            elapsed_ms,
        )
        return {
            "changes": changes,
            "tables": tables,
            "management_plans": self._management_plan_snapshot(user_id),
            "from_version": from_version,
            "to_version": to_version,
            "has_more": has_more,
            "server_time": _now(),
            "wallet": {"balance": wallet["balance"]} if wallet else None,
            "ledger_snapshot": ledger_snapshot,
            "reward_rebuild_epoch": reward_epoch,
            "diagnostics": {
                "protocol": "server_version",
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
                "returned_changes": len(changes),
                "dependency_backfilled": dependency_backfilled,
                "snapshot": from_version == 0,
                "limit": safe_limit,
                "table_counts": table_counts,
            },
            "sync_state": self._get_sync_state_map(user_id),
        }

    def _backfill_unversioned_atm_changes(self, user_id: int):
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT 'atm_summary' AS client_table, s.id, s.date
                   FROM server_atm_summary s WHERE s.user_id=? AND NOT EXISTS (
                     SELECT 1 FROM server_change_log c WHERE c.user_id=s.user_id
                     AND c.table_name IN ('atm_summary','server_atm_summary')
                     AND c.record_id=CAST(s.id AS TEXT) AND c.operation!='delete')
                   UNION ALL
                   SELECT 'atm_activities', a.id, a.date
                   FROM server_atm_activities a WHERE a.user_id=? AND NOT EXISTS (
                     SELECT 1 FROM server_change_log c WHERE c.user_id=a.user_id
                     AND c.table_name IN ('atm_activities','server_atm_activities')
                     AND c.record_id=CAST(a.id AS TEXT) AND c.operation!='delete')
                   ORDER BY client_table, id""",
                (user_id, user_id),
            ).fetchall()
            for row in rows:
                table = row["client_table"]
                self.db.write_server_change(
                    user_id, table, str(row["id"]), "upsert", {"date": row["date"]},
                    table_name=f"server_{table}", conn=conn,
                )
            if rows:
                conn.commit()
                logger.info("[SyncHub] backfilled unversioned ATM changes user_id=%s count=%s", user_id, len(rows))
        except Exception as error:
            conn.rollback()
            logger.warning("补建 ATM 版本日志失败 user=%s category=%s", user_id, type(error).__name__)
        finally:
            conn.close()

    def _backfill_unversioned_huawei_sleep_changes(self, user_id: int):
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT h.id, h.date
                FROM server_huawei_sleep_data h
                WHERE h.user_id = ?
                  AND NOT EXISTS (
                    SELECT 1
                    FROM server_change_log c
                    WHERE c.user_id = h.user_id
                      AND c.table_name = 'huawei_sleep_data'
                      AND c.record_id = CAST(h.id AS TEXT)
                      AND c.operation != 'delete'
                  )
                ORDER BY h.updated_at ASC, h.id ASC
                LIMIT 100
                """,
                (user_id,),
            ).fetchall()
            for row in rows:
                self.db.write_server_change(
                    user_id,
                    "huawei_sleep_data",
                    str(row["id"]),
                    "upsert",
                    {"date": row["date"]},
                    table_name="huawei_sleep_data",
                    conn=conn,
                )
            if rows:
                conn.commit()
                logger.info(
                    "[SyncHub] backfilled unversioned huawei sleep changes user_id=%s count=%s",
                    user_id,
                    len(rows),
                )
        except Exception as e:
            conn.rollback()
            logger.warning("补建睡眠版本日志失败 user=%s: %s", user_id, e)
        finally:
            conn.close()

    # ======================== TickTick 轮询（兜底）=====================

    async def start_ticktick_poll(self, interval: int = TICKTICK_POLL_INTERVAL_SEC):
        await self._ticktick_sync_all_users()
        while True:
            await asyncio.sleep(interval)
            try:
                await self._ticktick_sync_all_users()
            except Exception as e:
                logger.error(f"TickTick 轮询异常: {e}")

    async def _ticktick_sync_all_users(self):
        try:
            conn = self._conn()
            users = [dict(r) for r in conn.execute("SELECT id FROM users").fetchall()]
            conn.close()
        except Exception as e:
            logger.error(f"SyncHub 获取用户列表失败: {e}")
            return

        for u in users:
            uid = u["id"]
            await self._ticktick_sync_once_for_user(uid)

    async def _ticktick_sync_once_for_user(self, user_id: int):
        """用户独立轮询拉取"""
        settings = self._get_ticktick_settings(user_id)
        if not settings.enabled:
            return
        TickTickClient = _get_ticktick_client_class()

        changed = False
        async with TickTickClient(
            settings.access_token,
            settings.host,
            verify_tls=settings.verify_tls,
            timeout_seconds=settings.timeout_seconds,
        ) as client:
            try:
                await self._pull_tasks(client, user_id)
                changed = True
            except Exception as e:
                logger.warning(f"用户 {user_id} 拉取任务失败: {e}")
            try:
                await self._pull_habits(client, user_id)
                changed = True
            except Exception as e:
                logger.warning(f"用户 {user_id} 拉取习惯失败: {e}")

        if changed:
            self._notify_clients(["tasks", "habits", "habit_checkins", "reward_ledger", "user_wallets"])

    async def force_pull_ticktick(
        self, user_id: int, request_id: str | None = None, job_id: str | None = None, manual: bool = False,
    ):
        """兼容 refresh=true 的 TickTick provider 对账入口。"""
        async with self._provider_reconcile_lock:
            existing = self._provider_reconcile_tasks.get(user_id)
            if existing and not existing.done():
                logger.info(
                    "[ProviderReconcile] skipped request_id=%s user_id=%s reason=in_flight",
                    request_id,
                    user_id,
                )
                return {
                    "ok": True,
                    "enabled": True,
                    "foreground": False,
                    "request_id": request_id,
                    "job_id": job_id,
                    "skipped": True,
                    "reason": "in_flight",
                    "started_at": _now(),
                    "finished_at": _now(),
                    "elapsed_ms": 0,
                    "merged_count": 0,
                    "tasks": {},
                    "habits": {},
                    "errors": [],
                }
            retry_at = None if manual else self._ticktick_cooldown_retry_at(user_id)
            if retry_at:
                return {
                    "ok": True, "status": "degraded", "enabled": True, "foreground": False,
                    "request_id": request_id, "job_id": job_id, "skipped": True, "reason": "cooldown",
                    "retry_at": retry_at, "failure_summary": "外部任务源部分更新，冷却中等待自动重试",
                    "started_at": _now(), "finished_at": _now(), "elapsed_ms": 0, "merged_count": 0,
                    "tasks": {}, "habits": {}, "errors": ["tasks:incomplete_snapshot"],
                }
            reconcile = self._force_pull_ticktick_impl(user_id, request_id, job_id) if job_id else self._force_pull_ticktick_impl(user_id, request_id)
            task = asyncio.create_task(reconcile)
            self._provider_reconcile_tasks[user_id] = task
        try:
            return await task
        finally:
            async with self._provider_reconcile_lock:
                if self._provider_reconcile_tasks.get(user_id) is task:
                    self._provider_reconcile_tasks.pop(user_id, None)

    async def _force_pull_ticktick_impl(self, user_id: int, request_id: str | None = None, job_id: str | None = None):
        """执行单轮 TickTick provider 对账；由 force_pull_ticktick 做并发单飞。"""
        started_at = _now()
        started_perf = _time.perf_counter()
        diagnostics = {
            "ok": True,
            "status": "success",
            "enabled": False,
            "foreground": True,
            "request_id": request_id,
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": None,
            "elapsed_ms": None,
            "merged_count": 0,
            "tasks": {},
            "habits": {},
            "errors": [],
        }
        logger.info("[ProviderReconcile] start request_id=%s user_id=%s", request_id, user_id)
        if request_id:
            log_event(logger, trace_id=request_id, job_id=job_id, user_id=user_id,
                      stage="provider_pull", event="start", outcome="running")
        settings = self._get_ticktick_settings(user_id)
        if not settings.enabled:
            diagnostics["ok"] = False
            diagnostics["status"] = "error"
            diagnostics["errors"].append("ticktick_not_configured")
            self._record_sync_state(
                user_id,
                "ticktick",
                "ticktick_to_server",
                "error",
                "ticktick_not_configured",
                diagnostics=diagnostics,
            )
            diagnostics["finished_at"] = _now()
            diagnostics["elapsed_ms"] = round((_time.perf_counter() - started_perf) * 1000, 2)
            logger.warning("[ProviderReconcile] skipped request_id=%s user_id=%s reason=ticktick_not_configured", request_id, user_id)
            return diagnostics
        diagnostics["enabled"] = True
        TickTickClient = _get_ticktick_client_class()

        changed = False
        async with TickTickClient(
            settings.access_token,
            settings.host,
            verify_tls=settings.verify_tls,
            timeout_seconds=settings.timeout_seconds,
            request_id=request_id,
        ) as client:
            try:
                logger.info("[ProviderReconcile] tasks start request_id=%s user_id=%s", request_id, user_id)
                diagnostics["tasks"] = await self._pull_tasks(client, user_id)
                if not diagnostics["tasks"].get("complete"):
                    diagnostics["status"] = "degraded"
                    diagnostics["retry_at"] = (datetime.now(CST) + timedelta(seconds=TICKTICK_DEGRADED_COOLDOWN_SECONDS)).isoformat(timespec="seconds")
                    diagnostics["failure_summary"] = "任务快照未完整读取，已保留已有任务，稍后重试"
                    diagnostics["failed_projects"] = diagnostics["tasks"].get("failed_projects", [])
                    diagnostics["errors"].append("tasks:incomplete_snapshot")
                changed = True
                logger.info("[ProviderReconcile] tasks finish request_id=%s user_id=%s stats=%s", request_id, user_id, diagnostics["tasks"])
            except Exception as e:
                error = f"tasks:{getattr(e, 'pull_code', type(e).__name__)}"
                diagnostics["tasks"] = getattr(e, "diagnostics", diagnostics["tasks"])
                diagnostics["ok"] = False
                diagnostics["status"] = "error"
                diagnostics["errors"].append(error)
                logger.warning("[ProviderReconcile] tasks failed request_id=%s user_id=%s error=%s", request_id, user_id, error)
            try:
                logger.info("[ProviderReconcile] habits start request_id=%s user_id=%s", request_id, user_id)
                diagnostics["habits"] = await self._pull_habits(client, user_id)
                if not diagnostics["habits"].get("complete"):
                    diagnostics["ok"] = False
                    diagnostics["status"] = "error"
                    diagnostics["errors"].append("habits:incomplete_snapshot")
                changed = True
                logger.info("[ProviderReconcile] habits finish request_id=%s user_id=%s stats=%s", request_id, user_id, diagnostics["habits"])
            except Exception as e:
                error = f"habits:{getattr(e, 'pull_code', type(e).__name__)}"
                diagnostics["habits"] = getattr(e, "diagnostics", diagnostics["habits"])
                diagnostics["ok"] = False
                diagnostics["status"] = "error"
                diagnostics["errors"].append(error)
                logger.warning("[ProviderReconcile] habits failed request_id=%s user_id=%s error=%s", request_id, user_id, error)

        if changed:
            self._notify_clients(["tasks", "habits", "habit_checkins", "reward_ledger"])
        merged_count = 0
        for key in ("tasks", "habits"):
            value = diagnostics.get(key) or {}
            if isinstance(value, dict):
                merged_count += sum(
                    v for stat_key, v in value.items()
                    if isinstance(v, int) and stat_key.endswith("_changes")
                )
        diagnostics["merged_count"] = merged_count
        diagnostics["finished_at"] = _now()
        diagnostics["elapsed_ms"] = round((_time.perf_counter() - started_perf) * 1000, 2)
        if diagnostics["ok"]:
            self._record_sync_state(
                user_id,
                "ticktick",
                "ticktick_to_server",
                diagnostics["status"],
                ";".join(diagnostics["errors"]) or None,
                merged_count=merged_count,
                diagnostics=diagnostics,
            )
        else:
            self._record_sync_state(
                user_id,
                "ticktick",
                "ticktick_to_server",
                "error",
                ";".join(diagnostics["errors"]),
                merged_count,
                diagnostics=diagnostics,
            )
        logger.info(
            "[ProviderReconcile] finish request_id=%s user_id=%s ok=%s merged_count=%s errors=%s elapsed_ms=%s",
            request_id,
            user_id,
            diagnostics["ok"],
            merged_count,
            diagnostics["errors"],
            diagnostics["elapsed_ms"],
        )
        if request_id:
            log_event(logger, trace_id=request_id, job_id=job_id, user_id=user_id,
                      stage="provider_pull", event="finish",
                      outcome=diagnostics["status"] if diagnostics["ok"] else "failure",
                      elapsed_ms=diagnostics["elapsed_ms"],
                      details={"merged_count": merged_count, "errors": diagnostics["errors"],
                               "tasks": diagnostics["tasks"], "habits": diagnostics["habits"]},
                      level=logging.INFO if diagnostics["ok"] else logging.WARNING)
        return diagnostics

    async def _pull_tasks(self, client: "TickTickClient", user_id: int):
        stats = {
            "projects": 0,
            "provider_requests": 0,
            "request_budget": TICKTICK_PULL_REQUEST_BUDGET,
            "request_budget_exceeded": False,
            "project_failures": 0,
            "failed_projects": [],
            "project_budget_truncated": [],
            "inbox_requested": False,
            "inbox_succeeded": False,
            "inbox_tasks": 0,
            "inbox_error": None,
            "completed_pull_succeeded": False,
            "completed_pull_error": None,
            "deletion_skipped_reason": None,
            "deleted_tasks": 0,
            "skipped_projects": [],
            "skipped_completed_projects": 0,
            "completed_detail_skipped": 0,
            "active_tasks": 0,
            "active_task_changes": 0,
            "active_task_unchanged": 0,
            "completed_tasks": 0,
            "completed_task_changes": 0,
            "completed_task_unchanged": 0,
            "completed_item_errors": [],
            "sample_fields": [],
            "missing_fields": [],
        }
        try:
            return await self._pull_tasks_impl(client, user_id, stats)
        except ProviderPullError:
            raise
        except Exception as exc:
            raise _attach_pull_diagnostics(
                exc, f"task_pull_failed:{type(exc).__name__}", stats,
            )

    async def _pull_tasks_impl(self, client: "TickTickClient", user_id: int, stats: dict):
        start_date = self._get_checklist_sync_start_date(user_id)
        async def provider_get(read):
            remaining = TICKTICK_PULL_REQUEST_BUDGET - stats["provider_requests"]
            if remaining <= 0:
                stats["request_budget_exceeded"] = True
                raise ValueError("provider_request_budget_exhausted")
            before = getattr(client, "get_request_attempts", None)
            setter = getattr(client, "set_get_attempt_limit", None)
            if callable(setter):
                setter(min(2, remaining))
            try:
                return await read()
            finally:
                actual = getattr(client, "get_request_attempts", None)
                attempts = int(actual - before) if isinstance(before, int) and isinstance(actual, int) else int(getattr(client, "last_get_attempts", 1) or 1)
                stats["provider_requests"] += max(1, min(attempts, remaining))

        projects = await provider_get(client.get_projects)
        stats["projects"] = len(projects)
        project_map = {
            str(p.get("id", "")): p.get("name", "")
            for p in projects
            if p.get("id")
        }
        skipped_project_ids = set(SKIPPED_TICKTICK_PROJECT_IDS)
        settings = self._get_ticktick_settings(user_id)
        inbox_enabled = bool(getattr(settings, "inbox_pull_enabled", True))
        active_projects = []
        seen_project_keys = set()
        for project in projects:
            project_id = str(project.get("id", ""))
            project_key = project_id.lower()
            if not project_id or project_id in skipped_project_ids:
                continue
            if project_key == "inbox" and not inbox_enabled:
                continue
            if project_key in seen_project_keys:
                continue
            seen_project_keys.add(project_key)
            active_projects.append(project)
        listed_inbox = "inbox" in seen_project_keys
        if inbox_enabled and not listed_inbox:
            active_projects.append({"id": "inbox", "name": "收集箱", "_inbox": True})
        if inbox_enabled:
            active_projects.sort(key=lambda project: str(project.get("id", "")).lower() != "inbox")

        # 1. 查询本地数据库中当前属于该用户的未完成（status=0）任务的 id
        db_active_tids = set()
        db_known_tids = set()
        local_snapshots = {}
        try:
            conn = self._conn()
            rows = conn.execute(
                "SELECT id FROM server_tasks WHERE user_id = ? AND status = 0",
                (user_id,)
            ).fetchall()
            db_active_tids = {row["id"] for row in rows if row["id"]}
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(server_tasks)").fetchall()
            }
            snapshot_columns = [
                column for column in (
                    "id", "title", "priority", "due_date", "tags", "project_id",
                    "project_name", "raw_json", "source_etag", "source_modified_time", "deleted_at",
                )
                if column in columns
            ]
            known_rows = conn.execute(
                f"SELECT {', '.join(snapshot_columns)} FROM server_tasks WHERE user_id = ?",
                (user_id,)
            ).fetchall()
            db_known_tids = {
                row["id"] for row in known_rows
                if row["id"] and not dict(row).get("deleted_at")
            }
            local_snapshots = {row["id"]: dict(row) for row in known_rows if row["id"]}
            conn.close()
        except Exception as e:
            logger.error(f"查询本地未完成任务失败 (user={user_id}): {e}")

        current_active_tids = set()
        task_fingerprints = {}
        try:
            task_fingerprints = self.db.get_provider_fingerprints(user_id, "server_tasks")
        except Exception as e:
            logger.warning(f"读取 TickTick 任务本地指纹失败，将回退全量比较 (user={user_id}): {e}")

        async def process_active_project(project: dict):
            requested_project_id = str(project.get("id", ""))
            is_inbox = requested_project_id.lower() == "inbox"
            request_project_id = "inbox" if is_inbox else requested_project_id
            project_name = project.get("name", "")
            if is_inbox:
                stats["inbox_requested"] = True
            try:
                data = await provider_get(lambda: client.get_project_data(request_project_id))
                if not isinstance(data, dict):
                    raise ValueError("invalid_project_payload")
                tasks = data.get("tasks", [])
                if not isinstance(tasks, list):
                    raise ValueError("invalid_project_tasks")
                if is_inbox:
                    stats["inbox_succeeded"] = True
                    stats["inbox_tasks"] = len(tasks)
                for t in tasks:
                    tid = t.get("id", "")
                    title = t.get("title", "")
                    if t.get("status") != 0:
                        continue
                    if not stats["sample_fields"] and isinstance(t, dict):
                        stats["sample_fields"] = sorted(t.keys())
                    for field in ("id", "title", "status", "priority", "dueDate", "tags"):
                        if field not in t and field not in stats["missing_fields"]:
                            stats["missing_fields"].append(field)
                    normalized_task = normalize_ticktick_task_times(t)
                    due_date = normalized_task.get("due_date") or normalized_task.get("dueDate") or ""
                    if due_date and due_date < start_date.beijing_start_datetime.strftime("%Y-%m-%d %H:%M:%S") and tid not in local_snapshots:
                        continue
                    task_project_id = (
                        t.get("projectId")
                        or t.get("project_id")
                        or t.get("projectID")
                        or (None if is_inbox else requested_project_id)
                    )
                    task_project_id = str(task_project_id or "")
                    current_active_tids.add(tid)
                    task_payload = {
                        "id": tid, "title": title,
                        "priority": t.get("priority", 0), "status": 0,
                        "due_date": due_date,
                        "tags": t.get("tags", []),
                        "project_name": project_map.get(task_project_id, project_name),
                        "project_id": task_project_id,
                        "etag": t.get("etag", ""),
                        "modifiedTime": t.get("modifiedTime", ""),
                        **{k: v for k, v in normalized_task.items() if k not in {"id", "title", "priority", "status", "tags"}},
                    }
                    try:
                        delta = classify_provider_records([task_payload], task_fingerprints, "task")
                    except MissingProviderFingerprintError as e:
                        logger.error(
                            "TickTick 任务缺少增量指纹，停止本轮任务拉取 user=%s project_id=%s task_id=%s field=%s",
                            user_id, task_project_id, tid, e.field_name,
                        )
                        raise
                    stats["active_tasks"] += 1
                    if delta.unchanged:
                        stats["active_task_unchanged"] += 1
                        continue
                    self._clear_task_reward(user_id, tid)
                    changed = self.db.upsert_task(user_id, task_payload)
                    if task_payload.get("etag"):
                        task_fingerprints[tid] = {
                            "id": tid,
                            "source_etag": task_payload.get("etag", ""),
                            "source_modified_time": task_payload.get("modifiedTime", ""),
                            "status": 0,
                        }
                    if changed:
                        stats["active_task_changes"] += 1
            except Exception as e:
                stats["project_failures"] += 1
                if len(stats["failed_projects"]) < 3:
                    stats["failed_projects"].append({"project_id_suffix": request_project_id[-6:], "error_type": type(e).__name__})
                if is_inbox:
                    stats["inbox_error"] = type(e).__name__
                logger.warning(
                    "拉取 TickTick 项目任务失败 user=%s project_id=%s error_type=%s",
                    user_id, request_project_id, type(e).__name__,
                )

        for index, project in enumerate(active_projects):
            if stats["provider_requests"] >= TICKTICK_PULL_REQUEST_BUDGET:
                stats["request_budget_exceeded"] = True
                stats["project_budget_truncated"].extend(
                    str(item.get("id", ""))
                    for item in active_projects[index:]
                )
                break
            await process_active_project(project)

        completed_today_tids = set()
        try:
            utc_start = start_date.utc_start_for_ticktick_completed
            completed = []
            continuation = None
            seen_continuations = set()
            seen_records = set()
            while True:
                if continuation is None:
                    page = await provider_get(lambda: client.get_completed_tasks(utc_start))
                else:
                    continuation_key = json.dumps(continuation, sort_keys=True, ensure_ascii=False)
                    if continuation_key in seen_continuations:
                        raise ValueError("completed_page_continuation_loop")
                    seen_continuations.add(continuation_key)
                    page = await provider_get(lambda: client.get_completed_tasks(utc_start, continuation))
                page_records, next_page = self._completed_task_page_parts(page)
                page_keys = [
                    str(item.get("id") or json.dumps(item, sort_keys=True, ensure_ascii=False))
                    for item in page_records if isinstance(item, dict)
                ]
                if len(page_keys) != len(page_records):
                    raise ValueError("completed_page_invalid_record")
                if len(set(page_keys)) != len(page_keys) or seen_records.intersection(page_keys):
                    raise ValueError("completed_page_duplicate_records")
                if next_page is not None and not page_keys:
                    raise ValueError("completed_page_no_progress")
                seen_records.update(page_keys)
                completed.extend(page_records)
                if next_page is None:
                    break
                continuation = next_page
            stats["completed_pull_succeeded"] = True
            for t in completed:
                if t.get("status") == 2:
                    tid = t.get("id", "")
                    local_snapshot = local_snapshots.get(tid, {})
                    project_id = (
                        t.get("projectId")
                        or t.get("project_id")
                        or t.get("projectID")
                        or local_snapshot.get("project_id")
                    )
                    if str(project_id or "") in skipped_project_ids:
                        stats["skipped_completed_projects"] += 1
                        continue
                    missing_completed_fields = [field for field in ("title", "priority", "dueDate", "tags") if field not in t]
                    if missing_completed_fields:
                        stats["completed_detail_skipped"] += 1
                        missing_key = f"completed_detail_skipped:{tid}"
                        if missing_key not in stats["missing_fields"]:
                            stats["missing_fields"].append(missing_key)
                    title = t.get("title") or local_snapshot.get("title", "")
                    normalized_task = normalize_ticktick_task_times(t)
                    due_date = normalized_task.get("due_date") or normalized_task.get("dueDate") or local_snapshot.get("due_date") or ""
                    completed_today_tids.add(tid)
                    tags = t.get("tags", local_snapshot.get("tags", []))
                    if isinstance(tags, str):
                        tags = [tag for tag in tags.split(",") if tag]
                    task_payload = {
                        "id": tid, "title": title,
                        "priority": t.get("priority", local_snapshot.get("priority", 0)), "status": 2,
                        "due_date": due_date,
                        "tags": tags,
                        "project_name": project_map.get(str(project_id or ""), local_snapshot.get("project_name", "")),
                        "project_id": project_id,
                        "etag": t.get("etag", local_snapshot.get("source_etag", "")),
                        "modifiedTime": t.get("modifiedTime", local_snapshot.get("source_modified_time", "")),
                        **{k: v for k, v in normalized_task.items() if k not in {"id", "title", "priority", "status", "tags"}},
                    }
                    try:
                        delta = classify_provider_records([task_payload], task_fingerprints, "task")
                    except MissingProviderFingerprintError as e:
                        logger.error(
                            "TickTick 已完成任务缺少增量指纹，停止本轮任务拉取 user=%s project_id=%s task_id=%s field=%s",
                            user_id, project_id, tid, e.field_name,
                        )
                        raise
                    stats["completed_tasks"] += 1
                    if delta.unchanged:
                        stats["completed_task_unchanged"] += 1
                        continue

                    try:
                        # 首次出现的历史完成任务必须先持久化并建立默认奖励配置。
                        changed = self.db.upsert_task(user_id, task_payload)
                        self._reward_task_if_new(tid, title, t, user_id)
                    except Exception as item_error:
                        error = {
                            "code": str(item_error).split(":", 1)[0] or type(item_error).__name__,
                            "error_type": type(item_error).__name__, "task_id_suffix": str(tid)[-6:],
                        }
                        stats["completed_item_errors"].append(error)
                        logger.warning("TickTick 已完成任务处理失败但继续 user=%s task_id_suffix=%s error=%s",
                                       user_id, str(tid)[-6:], item_error)
                        continue
                    if task_payload.get("etag"):
                        task_fingerprints[tid] = {
                            "id": tid,
                            "source_etag": task_payload.get("etag", ""),
                            "source_modified_time": task_payload.get("modifiedTime", ""),
                            "status": 2,
                        }
                    if changed:
                        stats["completed_task_changes"] += 1
        except Exception as e:
            stats["completed_pull_error"] = f"{type(e).__name__}:{str(e) or 'empty_error'}"
            logger.warning(f"拉取已完成任务失败 (user={user_id}): {e}")

        snapshot_complete = (
            not stats["request_budget_exceeded"]
            and stats["project_failures"] == 0
            and stats["completed_pull_succeeded"]
            and not stats["completed_item_errors"]
        )
        if snapshot_complete:
            missing_tids = db_known_tids - current_active_tids - completed_today_tids
            for tid in sorted(missing_tids):
                if self._delete_provider_task(user_id, tid):
                    stats["deleted_tasks"] += 1
        else:
            reasons = []
            if stats["request_budget_exceeded"]:
                reasons.append("request_budget_exceeded")
            if stats["project_failures"]:
                reasons.append("project_pull_failed")
            if not stats["completed_pull_succeeded"]:
                reasons.append("completed_pull_failed")
            if stats["completed_item_errors"]:
                reasons.append("task_persistence_failed")
            stats["deletion_skipped_reason"] = ",".join(reasons)

        stats["complete"] = snapshot_complete

        return stats

    def _delete_provider_task(self, user_id: int, task_id: str) -> bool:
        """按完整 provider 快照确认删除；禁止在此路径逐任务读取 TickTick。"""
        conn = self._conn()
        try:
            with conn:
                row = conn.execute(
                    "SELECT id FROM server_tasks WHERE user_id = ? AND id = ? AND deleted_at IS NULL",
                    (user_id, task_id),
                ).fetchone()
                if not row:
                    return False
                now = _now()
                deleted = self._reward_settlement.remove_state_ledgers_in_txn(
                    conn, user_id, task_id, ("task_complete",)
                )
                self._publish_reward_changes_in_txn(conn, user_id, deleted, None)
                conn.execute(
                    "UPDATE server_tasks SET deleted_at = ?, updated_at = ? WHERE user_id = ? AND id = ?",
                    (now, now, user_id, task_id),
                )
                self.db.write_server_change(
                    user_id, "task", task_id, "delete", {"id": task_id, "deleted_at": now},
                    change_id=f"provider:ticktick:task:{task_id}:delete:{_time.time_ns()}",
                    device_id="ticktick", table_name="server_tasks", conn=conn,
                )
            return True
        finally:
            conn.close()


    async def _pull_habits(self, client: "TickTickClient", user_id: int):
        start_date = self._get_checklist_sync_start_date(user_id)
        conn = None
        stats = {
            "provider_requests": 0,
            "habits": 0,
            "habit_changes": 0,
            "habit_unchanged": 0,
            "checkin_blocks": 0,
            "checkin_blocks_raw": 0,
            "checkin_blocks_with_habit_id": 0,
            "checkin_blocks_unique_habit_id": 0,
            "missing_checkin_blocks": 0,
            "missing_checkin_habits": [],
            "checkin_range": None,
            "section_error": None,
            "checkins": 0,
            "checkin_changes": 0,
            "checkin_unchanged": 0,
            "reward_reconcile_scanned": 0,
            "reward_reconcile_created": 0,
            "reward_reconcile_corrected": 0,
            "reward_reconcile_unchanged": 0,
            "reward_reconcile_unverifiable": 0,
            "checkin_pull_succeeded": False,
            "complete": False,
        }
        try:
            stats["provider_requests"] += 1
            try:
                habits = await client.get_habits()
            except Exception as list_error:
                raise _attach_pull_diagnostics(
                    list_error, f"habit_list_failed:{type(list_error).__name__}", stats,
                )
            visible = [h for h in habits if h.get("status") in (0, 1)]
            stats["habits"] = len(visible)
            visible.sort(key=lambda h: h.get("sortOrder", 0))

            # 获取习惯分组信息，建立分组ID至名称的映射
            section_map = {}
            try:
                stats["provider_requests"] += 1
                sections = await client.get_habit_sections()
                section_map = {s["id"]: s["name"] for s in sections if "id" in s and "name" in s}
            except Exception as se:
                stats["section_error"] = {"code": "habit_sections_failed", "error_type": type(se).__name__}
                logger.warning(f"拉取习惯分组(sections)失败 (user={user_id}): {se}")

            conn = self._conn()
            now = _now()
            try:
                habit_fingerprints = self.db.get_provider_fingerprints(user_id, "server_habits")
            except Exception as e:
                habit_fingerprints = {}
                logger.warning(f"读取 TickTick 习惯本地指纹失败，将回退全量比较 (user={user_id}): {e}")
            def record_provider_change(entity_type: str, entity_id: str, table_name: str, payload: dict):
                if not hasattr(self.db, "write_server_change"):
                    return
                self.db.write_server_change(
                    user_id,
                    entity_type,
                    str(entity_id),
                    "upsert",
                    payload,
                    change_id=f"provider:ticktick:{entity_type}:{entity_id}:{_time.time_ns()}",
                    device_id="ticktick",
                    table_name=table_name,
                    conn=conn,
                )

            for h in visible:
                hid = str(h.get("id", ""))
                local_hid = _ticktick_local_habit_id(user_id, hid)
                name = h.get("name", "")
                icon = h.get("iconRes", "🎯")
                if icon and icon.startswith("txt_"):
                    icon = icon[4:]
                sort_order = h.get("sortOrder", 0)
                is_active = h.get("status", 0)

                section_id = h.get("sectionId", "")
                section_name = section_map.get(section_id, "")
                category_id = self.db._get_category_id(user_id, section_name, [section_name], conn) if section_name else None

                repeat_rule = h.get("repeatRule", "")
                raw_json = json.dumps(h, ensure_ascii=False, default=str)
                source_etag = h.get("etag", "")
                source_modified_time = h.get("modifiedTime", "")

                next_habit = {
                    "name": name,
                    "color": "#A3BE8C",
                    "sort_order": sort_order,
                    "is_active": is_active,
                    "icon": icon,
                    "category_id": category_id,
                    "repeat_rule": repeat_rule,
                    "raw_json": raw_json,
                    "source_etag": source_etag,
                    "source_modified_time": source_modified_time,
                }
                try:
                    delta = classify_provider_records([{**h, "_provider_key": local_hid}], habit_fingerprints, "habit")
                except MissingProviderFingerprintError as e:
                    logger.error(
                        "TickTick 习惯缺少增量指纹，停止本轮习惯拉取 user=%s habit_id=%s field=%s",
                        user_id, hid, e.field_name,
                    )
                    raise
                if delta.unchanged:
                    stats["habit_unchanged"] += 1
                    continue
                if local_hid != hid:
                    legacy_existing = conn.execute(
                        "SELECT id FROM server_habits WHERE user_id = ? AND id = ?",
                        (user_id, hid),
                    ).fetchone()
                    if legacy_existing:
                        conn.execute(
                            "UPDATE server_habit_checkins SET habit_id = ? WHERE user_id = ? AND habit_id = ?",
                            (local_hid, user_id, hid),
                        )
                        conn.execute(
                            "UPDATE server_habits SET id = ? WHERE user_id = ? AND id = ?",
                            (local_hid, user_id, hid),
                        )
                existing = conn.execute(
                    "SELECT id, name, color, sort_order, is_active, icon, category_id, repeat_rule, raw_json, source_etag, source_modified_time FROM server_habits WHERE user_id = ? AND id = ?", (user_id, local_hid)
                ).fetchone()
                if existing:
                    changed_fields = {
                        key: value
                        for key, value in next_habit.items()
                        if existing[key] != value
                    }
                    if changed_fields:
                        conn.execute(
                            "UPDATE server_habits SET name=?, color=?, sort_order=?, is_active=?, icon=?, category_id=?, repeat_rule=?, raw_json=?, source_etag=?, source_modified_time=?, updated_at=? WHERE user_id=? AND id=?",
                            (name, '#A3BE8C', sort_order, is_active, icon, category_id, repeat_rule, raw_json, source_etag, source_modified_time, now, user_id, local_hid),
                        )
                    record_provider_change("habit", local_hid, "server_habits", {**next_habit, "id": local_hid})
                    stats["habit_changes"] += 1
                else:
                    conn.execute(
                        "INSERT INTO server_habits (id, user_id, name, icon, color, sort_order, category_id, repeat_rule, is_active, raw_json, source_etag, source_modified_time, difficulty, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (local_hid, user_id, name, icon, '#A3BE8C', sort_order, category_id, repeat_rule, is_active, raw_json, source_etag, source_modified_time, 'easy', now, now),
                    )
                    record_provider_change("habit", local_hid, "server_habits", {**next_habit, "id": local_hid})
                    stats["habit_changes"] += 1
                RewardConfigService().ensure_item(conn, user_id, "habit", local_hid, difficulty="easy")
                if source_etag:
                    habit_fingerprints[local_hid] = {
                        "id": local_hid,
                        "source_etag": source_etag,
                        "source_modified_time": source_modified_time,
                        "status": is_active,
                    }
            conn.commit()



            if visible:
                now_cst = datetime.now(CST)
                tomorrow = (now_cst + timedelta(days=1)).strftime("%Y%m%d")
                week_start = start_date.compact_date
                stats["provider_requests"] += 1
                blocks = await client.get_habit_checkins(
                    [h["id"] for h in visible], week_start, tomorrow
                )
                if not isinstance(blocks, list):
                    raise TypeError(f"habit_checkins_response_not_list:{type(blocks).__name__}")
                stats["checkin_pull_succeeded"] = True
                stats["checkin_blocks_raw"] = len(blocks)
                week_start_dash = f"{week_start[:4]}-{week_start[4:6]}-{week_start[6:8]}"
                tomorrow_dash = f"{tomorrow[:4]}-{tomorrow[4:6]}-{tomorrow[6:8]}"
                stats["checkin_range"] = {"from": week_start_dash, "to": tomorrow_dash}
                valid_blocks = [
                    block for block in blocks
                    if isinstance(block, dict) and block.get("habitId")
                ]
                stats["checkin_blocks_with_habit_id"] = len(valid_blocks)
                blocks_by_habit = {
                    str(block.get("habitId", "")): block
                    for block in valid_blocks
                }
                stats["checkin_blocks_unique_habit_id"] = len(blocks_by_habit)
                stats["checkin_blocks"] = len(blocks_by_habit)

                for h in visible:
                    hid = str(h.get("id", ""))
                    local_hid = _ticktick_local_habit_id(user_id, hid)
                    block = blocks_by_habit.get(hid)
                    if block is None:
                        stats["missing_checkin_blocks"] += 1
                        stats["missing_checkin_habits"].append({
                            "id_suffix": hid[-6:], "name": str(h.get("name") or "")[:80],
                        })
                        block = {"habitId": hid, "checkins": []}
                    habit_row = conn.execute(
                        "SELECT id, name, difficulty, icon FROM server_habits WHERE user_id = ? AND id = ?", (user_id, local_hid)
                    ).fetchone()
                    if not habit_row:
                        continue

                    local_habit_id = habit_row["id"]

                    # 滴答清单端在此期间的日期状态快照：2=成功，1=失败，缺失=未打卡。
                    remote_checkins_by_date = {}
                    for ci in block.get("checkins", []):
                        stats["checkins"] += 1
                        stamp = str(ci.get("stamp", ""))
                        if len(stamp) < 8 or not stamp[:8].isdigit():
                            logger.warning(
                                "TickTick 习惯打卡 stamp 非法，跳过 user=%s habit_id=%s stamp=%s",
                                user_id, hid, stamp,
                            )
                            continue
                        checkin_date = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
                        remote_status = ci.get("status")
                        if remote_status not in (1, 2):
                            continue
                        existing_remote = remote_checkins_by_date.get(checkin_date)
                        if existing_remote:
                            old_op = str(existing_remote["checkin"].get("opTime") or "")
                            new_op = str(ci.get("opTime") or "")
                            if new_op and old_op and new_op < old_op:
                                continue
                            if (not new_op or not old_op) and existing_remote["status"] == 2:
                                logger.warning(
                                    "TickTick 习惯打卡同日状态冲突，保留成功状态 user=%s habit_id=%s date=%s",
                                    user_id, hid, checkin_date,
                                )
                                continue
                            logger.warning(
                                "TickTick 习惯打卡同日状态冲突，使用较新记录 user=%s habit_id=%s date=%s old_status=%s new_status=%s",
                                user_id, hid, checkin_date, existing_remote["status"], remote_status,
                            )
                        remote_checkins_by_date[checkin_date] = {"status": remote_status, "checkin": ci}

                    # 查询本地在此期间的所有打卡记录
                    local_checkins = conn.execute(
                        "SELECT id, checkin_date, checkin_time, status, raw_json, source_modified_time FROM server_habit_checkins "
                        "WHERE user_id = ? AND habit_id = ? AND checkin_date >= ? AND checkin_date <= ?",
                        (user_id, local_habit_id, week_start_dash, tomorrow_dash)
                    ).fetchall()

                    local_checkin_by_date = {row["checkin_date"]: row for row in local_checkins}

                    for d in sorted(set(local_checkin_by_date) | set(remote_checkins_by_date)):
                        if d < start_date.date:
                            continue
                        remote_entry = remote_checkins_by_date.get(d)
                        next_status = int(remote_entry["status"]) if remote_entry else 0
                        source_checkin = remote_entry["checkin"] if remote_entry else {}
                        raw_json = json.dumps(source_checkin, ensure_ascii=False, default=str)
                        source_modified_time = str(source_checkin.get("opTime") or "")
                        provider_has_op_time = bool(source_modified_time)
                        checkin_time = _ticktick_checkin_time(source_modified_time)
                        local_row = local_checkin_by_date.get(d)
                        if not checkin_time and local_row and local_row["checkin_time"]:
                            checkin_time = local_row["checkin_time"]
                            source_modified_time = local_row["source_modified_time"]
                            raw_json = local_row["raw_json"]
                        old_status = int(local_row["status"]) if local_row else 0
                        needs_reward_reconcile = next_status == 2 and bool(checkin_time)
                        if next_status == 2:
                            stats["reward_reconcile_scanned"] += 1
                            if not checkin_time:
                                stats["reward_reconcile_unverifiable"] += 1
                                logger.warning(
                                    "TickTick 习惯成功缺少实际打卡时间，暂缓金币结算 user=%s habit_id=%s date=%s",
                                    user_id, local_habit_id, d,
                                )
                        delta_unchanged = False
                        if remote_entry and provider_has_op_time:
                            try:
                                delta = classify_provider_records(
                                    [{**source_checkin, "_provider_key": f"{local_habit_id}:{d}"}],
                                    {
                                        f"{local_habit_id}:{d}": {
                                            "source_modified_time": local_row["source_modified_time"] if local_row else "",
                                        }
                                    } if local_row else {},
                                    "habit_checkin",
                                )
                                delta_unchanged = bool(delta.unchanged)
                            except MissingProviderFingerprintError as e:
                                logger.error(
                                    "TickTick 习惯打卡缺少增量指纹，停止本轮习惯拉取 user=%s habit_id=%s checkin_date=%s field=%s status=%s",
                                    user_id, local_habit_id, d, e.field_name, next_status,
                                )
                                raise
                        elif remote_entry and local_row:
                            delta_unchanged = old_status == next_status
                        if delta_unchanged and old_status == next_status and not needs_reward_reconcile:
                            stats["checkin_unchanged"] += 1
                            continue
                        if local_row and old_status == next_status and not remote_entry:
                            stats["checkin_unchanged"] += 1
                            continue
                        checkin_changed = not (local_row and old_status == next_status and delta_unchanged)
                        if local_row and checkin_changed:
                            conn.execute(
                                "UPDATE server_habit_checkins SET date = ?, checkin_date = ?, checkin_time = ?, status = ?, updated_at = ?, pushed_at = NULL, habit_name = ?, raw_json = ?, source_modified_time = ? WHERE user_id = ? AND id = ?",
                                (d, d, checkin_time, next_status, now, habit_row["name"], raw_json, source_modified_time, user_id, local_row["id"]),
                            )
                            checkin_id = local_row["id"]
                        elif not local_row:
                            checkin_id = uuid.uuid4().hex
                            conn.execute(
                                "INSERT INTO server_habit_checkins (id, user_id, habit_id, habit_name, date, checkin_date, checkin_time, status, raw_json, source_modified_time, updated_at, pushed_at) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                                (checkin_id, user_id, local_habit_id, habit_row["name"], d, d, checkin_time, next_status, raw_json, source_modified_time, now),
                            )
                        reward_reconcile = self._replace_habit_reward_in_txn(
                            conn, user_id, local_habit_id, habit_row["name"],
                            habit_row["difficulty"], d, next_status, checkin_time,
                            defer_success_without_time=True,
                        )
                        if reward_reconcile in {"created", "corrected", "unchanged"}:
                            stats[f"reward_reconcile_{reward_reconcile}"] += 1
                        if checkin_changed:
                            record_provider_change(
                                "habit_checkin", str(checkin_id), "server_habit_checkins",
                                {"id": checkin_id, "habit_id": local_habit_id,
                                 "habit_name": habit_row["name"], "checkin_date": d,
                                 "checkin_time": checkin_time, "status": next_status,
                                 "raw_json": raw_json, "source_modified_time": source_modified_time},
                            )
                            stats["checkin_changes"] += 1
                        else:
                            stats["checkin_unchanged"] += 1

            conn.commit()
            stats["complete"] = bool(not visible or stats["checkin_pull_succeeded"])
            try:
                if SampleDataInitializationService(self.db.log_path).ensure_user_sample_data(user_id):
                    self._notify_clients(["goals", "goal_category_bindings", "rewards"], user_id)
            except Exception as seed_error:
                logger.warning("商店样例初始化重试失败 (user=%s): %s", user_id, seed_error)
        except Exception as e:
            if conn is not None:
                conn.rollback()
            logger.warning(f"拉取习惯失败 (user={user_id}): {e}")
            if isinstance(e, ProviderPullError) or getattr(e, "pull_code", None):
                raise
            raise _attach_pull_diagnostics(
                e, f"habit_pull_failed:{type(e).__name__}", stats,
            )
        finally:
            if conn is not None:
                conn.close()
        return stats

    # ======================== 金币结算 ========================

    def _publish_reward_changes_in_txn(self, conn, user_id: int, deleted: list[dict], ledger_id: str | None):
        if not hasattr(self.db, "write_server_change"):
            return
        for row in deleted:
            self.db.write_server_change(
                user_id, "reward_ledger", row["id"], "delete", {"id": row["id"]},
                change_id=f"provider:ticktick:reward_ledger:{row['id']}:delete:{_time.time_ns()}",
                device_id="ticktick", table_name="server_reward_ledger", conn=conn,
            )
        if ledger_id:
            row = conn.execute(
                "SELECT * FROM server_reward_ledger WHERE user_id = ? AND id = ?", (user_id, ledger_id)
            ).fetchone()
            if row:
                self.db.write_server_change(
                    user_id, "reward_ledger", ledger_id, "upsert", dict(row),
                    change_id=f"provider:ticktick:reward_ledger:{ledger_id}:upsert:{_time.time_ns()}",
                    device_id="ticktick", table_name="server_reward_ledger", conn=conn,
                )
        if deleted or ledger_id:
            wallet = self._reward_wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, _now)
            self.db.write_server_change(
                user_id, "user_wallets", str(user_id), "upsert",
                {"user_id": user_id, "balance": wallet["balance"], "updated_at": _now()},
                change_id=f"provider:ticktick:user_wallets:{user_id}:{_time.time_ns()}",
                device_id="ticktick", table_name="server_user_wallets", conn=conn,
            )

    def _replace_habit_reward_in_txn(
        self, conn, user_id, habit_id, title, difficulty, target_date, status,
        occurred_at=None, defer_success_without_time=False,
    ):
        keep_type = "habit_checkin" if status == 2 else "habit_fail" if status == 1 else None
        deleted = self._reward_settlement.remove_state_ledgers_in_txn(
            conn, user_id, habit_id, ("habit_checkin", "habit_fail"), target_date, keep_type
        )
        event_key = self._reward_settlement.completion_event_key("habit", habit_id, target_date)
        if status != 2:
            deleted.extend(self._reward_settlement.remove_task_unlocks_in_txn(
                conn, user_id, "habit", habit_id, event_key, reverse_used=True
            ))
        ledger_id = None
        settlement_status = None
        if status == 2:
            if defer_success_without_time and not occurred_at:
                self._publish_reward_changes_in_txn(conn, user_id, deleted, None)
                return "unverifiable"
            reward = self._reward_rules.calculate_habit_success(
                user_id, habit_id, title, difficulty, target_date, occurred_at
            )
            ledger_id, settlement_status = self._reward_settlement.reconcile_habit_success_in_txn(
                conn, user_id, habit_id, reward.title, reward.amount, target_date, occurred_at
            )
            self._reward_settlement.grant_task_unlocks_in_txn(
                conn, user_id, "habit", habit_id, event_key, title, target_date
            )
        elif status == 1:
            reward = self._reward_rules.calculate_habit_fail(user_id, habit_id, title, difficulty)
            ledger_id = self._reward_settlement.settle_habit_fail_in_txn(
                conn, user_id, habit_id, reward.title, reward.amount, target_date, occurred_at=occurred_at
            )
        publish_id = ledger_id if settlement_status not in {"unchanged", "unverifiable"} else None
        self._publish_reward_changes_in_txn(conn, user_id, deleted, publish_id)
        return settlement_status

    def _clear_task_reward(self, user_id: int, task_id: str):
        conn = self._conn()
        try:
            with conn:
                reward_ids = [row["id"] for row in conn.execute(
                    """SELECT id FROM server_reward_ledger
                       WHERE user_id=? AND source_type='task_complete'
                         AND (source_id=? OR source_id LIKE ?)""",
                    (user_id, task_id, f"{task_id}#%"),
                ).fetchall()]
                deleted = self._reward_wallet.remove_ledger_entries_in_txn(
                    conn, user_id, reward_ids, backpack_event=None,
                )
                deleted.extend(self._reward_settlement.remove_task_unlocks_for_source_in_txn(
                    conn, user_id, "checklist_task", task_id
                ))
                if deleted:
                    self._publish_reward_changes_in_txn(conn, user_id, deleted, None)
        finally:
            conn.close()

    def _reward_task_if_new(self, task_id: str, title: str, task: dict, user_id: int):
        completed_time = task.get("completedTime", "")
        if not completed_time:
            return
        start_date = self._get_checklist_sync_start_date(user_id)
        try:
            clean = completed_time.replace("+0000", "Z")
            dt = datetime.fromisoformat(clean.replace("Z", "+00:00"))
            dt_cst = dt.astimezone(CST)
            if dt_cst.date() < start_date.beijing_start_datetime.date():
                return "before_statistics_start"
        except Exception as e:
            logger.warning(f"Error parsing task completed time for filter: {e}")
            return "unverifiable"

        reward = self._reward_rules.calculate_task_success(user_id, task_id, title)

        target_dt = dt_cst.strftime("%Y-%m-%d %H:%M:%S")
        completion_source_id = f"{task_id}#{target_dt}"

        conn = self._conn()
        try:
            with conn:
                ledger_id = self._reward_settlement.settle_task_success_in_txn(
                    conn, user_id, completion_source_id, reward.title, reward.amount,
                    target_dt[:10], target_dt,
                )
                event_key = self._reward_settlement.completion_event_key(
                    "checklist_task", task_id, target_dt[:10], target_dt
                )
                unlock_ledger_ids = self._reward_settlement.grant_task_unlocks_in_txn(
                    conn, user_id, "checklist_task", task_id, event_key, title, target_dt[:10]
                )
                self._publish_reward_changes_in_txn(conn, user_id, [], ledger_id)
                for unlock_ledger_id in unlock_ledger_ids:
                    self._publish_reward_changes_in_txn(conn, user_id, [], unlock_ledger_id)
                return "settled"
        finally:
            conn.close()

    def _is_today_cst(self, time_str: str) -> bool:
        if not time_str:
            return False
        try:
            clean = time_str.replace("+0000", "Z")
            dt = datetime.fromisoformat(clean.replace("Z", "+00:00"))
            return dt.astimezone(CST).date() == datetime.now(CST).date()
        except Exception:
            return False

    def _is_today_or_overdue_cst(self, time_str: str) -> bool:
        if not time_str:
            return False
        try:
            clean = time_str
            if clean.endswith("+0000"):
                clean = clean[:-5] + "+00:00"
            elif clean.endswith("Z"):
                clean = clean[:-1] + "+00:00"
            dt = datetime.fromisoformat(clean)
            return dt.astimezone(CST).date() <= datetime.now(CST).date()
        except Exception as e:
            logger.warning(f"Error parsing task due date '{time_str}': {e}")
            return False


    def _get_task_coins(self, task_id: str, user_id: int) -> float:
        configured = self.db.get_item_reward(user_id, "task", task_id)
        return float(configured["reward"])

    # ======================== 配置 ========================

    def _get_checklist_sync_start_date(self, user_id: int):
        conn = self._conn()
        try:
            return get_user_statistics_start_date(conn, user_id)
        finally:
            conn.close()

    def _get_ticktick_settings(self, user_id: int):
        """调用链路：SyncHub TickTick 入口 -> 本函数 -> ticktick_config.load_ticktick_settings -> DB/env。

        SQL：读取 server_system_config.ticktick_config。
        返回：TickTickSettings，包含 token、host、timeout、verify_tls；缺 token 时 enabled=False。
        """
        conn = None
        try:
            conn = self._conn()
            return load_ticktick_settings(conn, user_id)
        finally:
            if conn is not None:
                conn.close()

    def _get_ticktick_token(self, user_id: int) -> str | None:
        # 兼容旧测试/调试入口；新链路统一走 _get_ticktick_settings。
        return self._get_ticktick_settings(user_id).access_token

    def _get_ticktick_host(self, user_id: int) -> str:
        # 兼容旧测试/调试入口；新链路统一走 _get_ticktick_settings。
        return self._get_ticktick_settings(user_id).host
