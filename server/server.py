# -*- coding: utf-8 -*-
"""
服务端主模块 (server.py)
========================
基于 FastAPI 的睡眠分析 HTTP 服务，提供以下功能：

【API 端点一览】
  认证相关：
    POST /auth/register  — 用户注册
    POST /auth/login     — 用户登录，返回 Bearer Token
    GET  /auth/me        — 获取当前用户信息（需 Bearer Token）

  基础端点：
    GET  /ping           — 健康检查（无需认证）
    GET  /               — Web 管理界面

  睡眠分析：
    POST /upload                  — 上传截图，触发快速分析（后台异步）
    GET  /status/{request_id}     — 查询分析状态
    GET  /status_by_date/{date}   — 按日期查询分析状态
    GET  /events/{request_id}     — SSE 实时进度流
    POST /generate_report         — 触发完整分析（异步等待，最多 30s，不阻塞事件循环）

  数据同步：
    GET  /sync_data      — 增量拉取已完成记录（支持 since 参数）
    POST /ack_sync       — 确认客户端已同步的记录

  日记：
    POST /reflection     — 保存晨间日记
    POST /evening_diary  — 保存晚间日记

  其他：
    GET  /recent         — 获取最近 N 条已完成记录

【认证方式】
  - Bearer Token：通过 /auth/login 获取，有效期 30 天
  - Legacy Token：通过 server/config.json 的 security.legacy_auth_token 配置，兼容旧版客户端

【全局对象】
  - store: ServerSleepStore 实例，管理 SQLite 数据库
  - progress_queues: dict[request_id, Queue]，SSE 进度消息队列（有生命周期管理）
  - time_logger_db: StudyLogger 实例，用于完整报告生成时拉取 aTimeLogger 数据
"""

import asyncio
import hashlib
import json
import re
import sqlite3
import sys
import os
import queue
import shutil
import threading
import uuid
import logging
import httpx
import psutil
import requests
import atexit
import signal
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import markdown
from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Request, Response, UploadFile, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)


def _source_revision() -> str:
    configured = str(os.getenv("MTL_BUILD_REVISION") or "").strip()
    if configured:
        return configured[:40]
    try:
        head_path = os.path.join(root_dir, ".git", "HEAD")
        with open(head_path, "r", encoding="utf-8") as handle:
            head = handle.read().strip()
        if head.startswith("ref: "):
            with open(os.path.join(root_dir, ".git", head[5:].replace("/", os.sep)),
                      "r", encoding="utf-8") as handle:
                head = handle.read().strip()
        return head[:12] or "unknown"
    except OSError:
        return "unknown"


BUILD_REVISION = _source_revision()
ATIMELOGGER_FINAL_BACKUP_VERSION = 2
ATIMELOGGER_FINAL_ONLY_CUTOVER = os.getenv(
    "MTL_ATIMELOGGER_FINAL_CUTOVER", "2026-07-25 19:33:00+08:00",
)

try:
    from .config_manager import server_config
except (ImportError, ValueError):
    from config_manager import server_config

try:
    from .logging_config import LoggingConfigStore, configure_logging, format_module_levels, request_logging_middleware
except (ImportError, ValueError):
    from logging_config import LoggingConfigStore, configure_logging, format_module_levels, request_logging_middleware


def _server_relative_path(value: str | None, default_name: str) -> str:
    raw = str(value or default_name).strip()
    return raw if os.path.isabs(raw) else os.path.join(current_dir, raw)


LOG_DIR = _server_relative_path(server_config.get_runtime("log_dir", "log"), "log")
logging_config_store = LoggingConfigStore(os.path.join(current_dir, "data", "logging_config.json"))


def apply_runtime_logging_config(config=None):
    """从权威配置统一应用业务 logger 与 Uvicorn logger 级别。"""
    runtime_config = config or logging_config_store.load()
    return configure_logging(
        log_dir=LOG_DIR,
        global_level=runtime_config.global_level,
        module_levels=format_module_levels(runtime_config.module_levels),
    )


ACTIVE_LOG_FILE = apply_runtime_logging_config()


def _reconcile_enabled_atimelogger_jobs() -> int:
    conn = store._connect()
    try:
        rows = conn.execute(
            "SELECT user_id,value FROM server_system_config WHERE key='atimelogger_config'"
        ).fetchall()
    finally:
        conn.close()
    repaired = 0
    backup_store = ATimeLoggerBackupStore(store._connect)
    for row in rows:
        try:
            cfg = json.loads(row["value"] or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(cfg, dict):
            safe_cfg = _clean_provider_config("atimelogger_config", cfg, {})
            if safe_cfg != cfg:
                _write_user_provider_config(int(row["user_id"]), "atimelogger_config", safe_cfg)
            cfg = safe_cfg
        if isinstance(cfg, dict) and cfg.get("enabled") and cfg.get("token"):
            repaired += backup_store.reconcile_user(
                int(row["user_id"]), cutover=ATIMELOGGER_FINAL_ONLY_CUTOVER,
            )
    if repaired:
        logger.info("aTimeLogger final-backup reconciliation repaired=%s", repaired)
    return repaired


async def _run_atimelogger_reconciliation():
    try:
        await asyncio.to_thread(_reconcile_enabled_atimelogger_jobs)
    except Exception as exc:
        logger.warning("aTimeLogger final-backup reconciliation failed: %s", type(exc).__name__)
logger = logging.getLogger("server")
logger.info(f"服务端日志文件: {ACTIVE_LOG_FILE}")


def _sync_table_counts(tables: dict | None) -> dict:
    return {
        table: len(rows) if isinstance(rows, list) else 0
        for table, rows in (tables or {}).items()
    }

try:
    from .security_utils import redact_mapping, redact_timer_lease_event
    from .store import ServerSleepStore
    from .domain.sample_data_initialization_service import SampleDataInitializationService
    from .domain.live_timer_lease_service import LiveTimerLeaseService
    from .domain.atimelogger_backup_store import ATimeLoggerBackupStore, beijing_text
    from .domain.atimelogger_final_backup import ATimeLoggerFinalBackupWorker
    from .domain.ticktick_task_mutation_service import TickTickTaskMutationService
    from .domain.habit_checkin_command_service import HabitCheckinCommandService
    from .domain.management_plan_service import ManagementPlanError, ManagementPlanService
    from .domain.user_behavior_audit_service import UserBehaviorAuditService
    from .domain.management_planning_policy import system_policy_prompt
    from .domain.learning_plan_service import LearningPlanService
    from .domain.flash_card_service import FlashCardError, FlashCardService
    from .domain.flash_proofreading import validate_minimal_polish
    from .domain.flash_skill_feedback_service import FlashSkillFeedbackService
    from .domain.flash_processing_log_service import FlashProcessingLogService
    from .domain.reward_config_service import RewardConfigService
    from .domain.source_reward_service import SourceRewardError, SourceRewardService
    from .domain.reward_rebuild_service import RewardRebuildError, RewardRebuildService
    from .domain.reward_rebuild_diagnostics import log_event, normalize_trace_id
    from .models.habit_checkin_command_store import HabitCheckinCommandStore
    from .models.ticktick_task_operation_store import TickTickTaskOperationStore
    from .ticktick_client import TickTickClient
    from .ticktick_config import load_ticktick_settings
    from .account_contamination_recovery import preview_contamination, recover_contamination
    from .ticktick_reset import preview_ticktick_reset
    from .ticktick_reset_execute import reset_ticktick_data
    from .statistics_start_date import get_user_statistics_start_date, resolve_statistics_start_date
    from .runtime_config import bootstrap_server_system_config, ensure_server_runtime_config
    from .analyzer import SleepAnalyzer
    from .domain.sleep_automation_service import BEIJING, SleepAutomationService, STEP_BEDTIME_DEADLINE, STEP_TIMER_SWITCH, due_step, beijing_now
    from .domain.sleep_reward_service import BEDTIME_COIN_EFFECTIVE_DATE
    from .domain.exercise_v4_service import ExerciseV4Service
    from .huawei_sleep_sync import (
        SleepDataSource,
        normalize_structured_sleep_payload,
        sleep_field_mapping,
    )
except (ImportError, ValueError):
    from security_utils import redact_mapping, redact_timer_lease_event
    from store import ServerSleepStore
    from domain.sample_data_initialization_service import SampleDataInitializationService
    from domain.live_timer_lease_service import LiveTimerLeaseService
    from domain.atimelogger_backup_store import ATimeLoggerBackupStore, beijing_text
    from domain.atimelogger_final_backup import ATimeLoggerFinalBackupWorker
    from domain.ticktick_task_mutation_service import TickTickTaskMutationService
    from domain.habit_checkin_command_service import HabitCheckinCommandService
    from domain.management_plan_service import ManagementPlanError, ManagementPlanService
    from domain.user_behavior_audit_service import UserBehaviorAuditService
    from domain.management_planning_policy import system_policy_prompt
    from domain.learning_plan_service import LearningPlanService
    from domain.flash_card_service import FlashCardError, FlashCardService
    from domain.flash_proofreading import validate_minimal_polish
    from domain.flash_skill_feedback_service import FlashSkillFeedbackService
    from domain.flash_processing_log_service import FlashProcessingLogService
    from domain.reward_config_service import RewardConfigService
    from domain.source_reward_service import SourceRewardError, SourceRewardService
    from domain.reward_rebuild_service import RewardRebuildError, RewardRebuildService
    from domain.reward_rebuild_diagnostics import log_event, normalize_trace_id
    from models.habit_checkin_command_store import HabitCheckinCommandStore
    from models.ticktick_task_operation_store import TickTickTaskOperationStore
    from ticktick_client import TickTickClient
    from ticktick_config import load_ticktick_settings
    from account_contamination_recovery import preview_contamination, recover_contamination
    from ticktick_reset import preview_ticktick_reset
    from ticktick_reset_execute import reset_ticktick_data
    from statistics_start_date import get_user_statistics_start_date, resolve_statistics_start_date
    from runtime_config import bootstrap_server_system_config, ensure_server_runtime_config
    from analyzer import SleepAnalyzer
    from domain.sleep_automation_service import BEIJING, SleepAutomationService, STEP_BEDTIME_DEADLINE, STEP_TIMER_SWITCH, due_step, beijing_now
    from domain.sleep_reward_service import BEDTIME_COIN_EFFECTIVE_DATE
    from domain.exercise_v4_service import ExerciseV4Service
    from huawei_sleep_sync import (
        SleepDataSource,
        normalize_structured_sleep_payload,
        sleep_field_mapping,
    )

import uvicorn

# 辅助函数
def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ATTACHMENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "attachments"))

ensure_server_runtime_config()

try:
    from .db_wrapper import ServerDBWrapper
    from .sync_hub import SyncHub
    from .sync_constants import SSE_KEEPALIVE_INTERVAL_SEC
    from .webdav_backup import S3BackupConfig, S3BackupService, S3Client
except (ImportError, ValueError):
    from db_wrapper import ServerDBWrapper
    from sync_hub import SyncHub
    from sync_constants import SSE_KEEPALIVE_INTERVAL_SEC
    from webdav_backup import S3BackupConfig, S3BackupService, S3Client

store = ServerSleepStore()
sleep_automation_service = SleepAutomationService(store._transact, store._record_server_change)
# 初始化主数据库连接，用于拉取 TimeLogger 数据生成完整报告
time_logger_db = ServerDBWrapper(store.db_path)
# 四端同步引擎
sync_hub = SyncHub(time_logger_db, goal_store=store)
ticktick_task_operation_store = TickTickTaskOperationStore(store._connect)
ticktick_task_mutation_service = TickTickTaskMutationService(ticktick_task_operation_store)
habit_checkin_command_store = HabitCheckinCommandStore(store._connect)
habit_checkin_command_service = HabitCheckinCommandService(
    store._transact, store.habit_domain_service, habit_checkin_command_store
)
management_plan_service = ManagementPlanService(store._connect)
def _behavior_audit_service() -> UserBehaviorAuditService:
    return UserBehaviorAuditService(store._connect)
learning_plan_service = LearningPlanService(store._connect, store._record_server_change)
flash_card_service = FlashCardService(store._connect, store._record_server_change)
flash_skill_feedback_service = FlashSkillFeedbackService(store._connect)
flash_processing_log_service = FlashProcessingLogService(store._connect)
source_reward_service = SourceRewardService(store._connect)
reward_rebuild_service = RewardRebuildService(store)
reward_rebuild_tasks: dict[str, asyncio.Task] = {}


def _migrate_flash_recommendations_on_startup(max_attempts: int = 4) -> int:
    """短暂 SQLite 锁不应阻止 FastAPI 绑定端口；下次启动仍会幂等补齐。"""
    for attempt in range(max_attempts):
        try:
            return flash_card_service.migrate_legacy_recommendations()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt + 1 >= max_attempts:
                logger.warning("闪念历史推荐迁移暂缓：%s", exc)
                return 0
            time.sleep(0.5 * (attempt + 1))
    return 0


TIMER_STATE_CAPABILITY = "timer-current-state-v1"


def _ensure_sample_data_for_user(user_id: int) -> None:
    SampleDataInitializationService(store.db_path).ensure_user_sample_data(user_id)


def _repair_learning_categories_on_startup() -> int:
    with store._connect() as conn:
        user_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM users")]
    service = SampleDataInitializationService(store.db_path)
    repaired = sum(service.repair_learning_categories(user_id) for user_id in user_ids)
    logger.info("learning category integrity repaired users=%s tasks=%s", len(user_ids), repaired)
    return repaired


def _repair_v4_diet_rule_keys_on_startup() -> int:
    with store._connect() as conn:
        user_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM users")]
    service = SampleDataInitializationService(store.db_path)
    repaired = sum(service.repair_v4_diet_rule_keys(user_id) for user_id in user_ids)
    logger.info("V4 diet rule identity repaired users=%s rows=%s", len(user_ids), repaired)
    return repaired


def _retire_legacy_noon_bedtime_penalties_on_startup() -> dict:
    """幂等撤销已废弃 noon 规则的精确历史流水。"""
    result = store.sleep_reward_service.rollback_bedtime_coins()
    logger.info("legacy noon bedtime penalties retired deleted=%s users=%s",
                result["deleted_ledgers"], result["affected_users"])
    return result


def _materialize_reward_configs() -> int:
    with store._transact() as conn:
        user_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM users")]
        created = sum(RewardConfigService().materialize_user(conn, user_id) for user_id in user_ids)
    logger.info("reward configuration materialized users=%s created=%s", len(user_ids), created)
    return created


def _bootstrap_private_config_for_user(user_id: int) -> None:
    try:
        result = bootstrap_server_system_config(user_id=user_id, db_path=store.db_path)
        logger.info("Private env config bootstrap result: %s", result)
    except Exception as exc:
        logger.warning("Private env config bootstrap failed for user_id=%s: %s", user_id, exc)


def _username_for_user_id(user_id: int | None) -> str:
    if not user_id:
        return ""
    conn = sqlite3.connect(store.db_path)
    try:
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


s3_backup = S3BackupService(
    os.path.join(current_dir, "data", "webdav_backup_config.json"),
    config_loader=lambda: _service_manager_s3_config(),
)
progress_queues: dict[str, queue.Queue] = {}
progress_latest: dict[str, dict] = {}
def _backfill_exercise_score_snapshots_in_txn(conn: sqlite3.Connection, today: str) -> set[int]:
    groups = conn.execute(
        """SELECT DISTINCT user_id,date,plan_version FROM server_exercise_checkins
           WHERE date<?""",
        (today,),
    ).fetchall()
    changed_users: set[int] = set()
    for group in groups:
        user_id, target_date = int(group["user_id"]), str(group["date"])[:10]
        if target_date < get_user_statistics_start_date(conn, user_id).date:
            continue
        plan_version = str(group["plan_version"] or "v0")
        # V4 snapshots are assembled from the three server-authoritative scopes
        # by ExerciseV4Service.  The legacy check-in backfill only understands
        # the old schedule/training model and must never overwrite that result.
        if plan_version == "v4":
            continue
        current = conn.execute(
            """SELECT * FROM server_exercise_daily_logs
               WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'""",
            (user_id, target_date, plan_version),
        ).fetchone()
        day_key = _exercise_day_key(target_date)
        items = [dict(row) for row in conn.execute(
            """SELECT id,day_key,variant,section,sort_order,name,sets,intensity,color,tags_json
               FROM server_exercise_plan_items
               WHERE user_id=? AND plan_version=? AND day_key=? AND is_active=1 ORDER BY variant,sort_order""",
            (user_id, plan_version, day_key),
        ).fetchall()]
        checkins = [dict(row) for row in conn.execute(
            "SELECT * FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=?",
            (user_id, target_date, plan_version),
        ).fetchall()]
        definition = _exercise_plan_definition(conn, user_id, plan_version)
        score = _exercise_score(items, checkins, definition, day_key, target_date)
        if not items:
            rules = definition.get("sundayScore" if day_key == "日" else "saturdayScore" if day_key == "六" else "weekdayScore") or []
            expected = {f"sc-{target_date}-{rule[0]}" for rule in rules if len(rule) >= 3}
            if not expected:
                continue
            done = {str(row.get("item_key")) for row in checkins if int(row.get("status") or 0) == 1}
            score.update(completed_items=len(expected & done), total_items=len(expected))
        score["plan_version"] = plan_version
        try:
            current_score = json.loads(current["score_snapshot"]) if current and current["score_snapshot"] else None
        except (TypeError, ValueError, json.JSONDecodeError):
            current_score = None
        if current and current_score == score and int(current["completed_items"] or 0) == score["completed_items"] \
                and int(current["total_items"] or 0) == score["total_items"] and current["day_name"] == day_key:
            continue
        now = _exercise_now_str()
        log_id = current["id"] if current else f"server-exercise-{user_id}-{target_date}-{plan_version}-daily"
        conn.execute(
            """INSERT INTO server_exercise_daily_logs
               (id,user_id,date,plan_version,exercise_type,week_num,day_name,completed_items,total_items,score_snapshot,created_at,updated_at)
               VALUES (?,?,?,?, 'daily',1,?,?,?,?,?,?)
               ON CONFLICT(user_id,date,plan_version,exercise_type) DO UPDATE SET
                 day_name=excluded.day_name,completed_items=excluded.completed_items,total_items=excluded.total_items,
                 score_snapshot=excluded.score_snapshot,updated_at=excluded.updated_at""",
            (log_id, user_id, target_date, plan_version, day_key, score["completed_items"], score["total_items"],
             json.dumps(score, ensure_ascii=False, sort_keys=True), now, now),
        )
        row = dict(conn.execute(
            """SELECT * FROM server_exercise_daily_logs
               WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'""",
            (user_id, target_date, plan_version),
        ).fetchone())
        _exercise_write_change(conn, user_id, "exercise_daily_log", row["id"], row)
        changed_users.add(user_id)
    return changed_users


def _settle_completed_goal_periods() -> int:
    """补偿每个用户的已结束目标周期，并通知其已连接客户端。"""
    with store._connect() as conn:
        user_ids = [row["id"] for row in conn.execute("SELECT id FROM users").fetchall()]
    changed = 0
    for user_id in user_ids:
        if store.auto_settle_goals(user_id):
            changed += 1
            sync_hub._notify_clients(["goals", "external_rewards", "reward_ledger", "user_wallets"], user_id)
    return changed


def _settle_completed_exercise_days() -> int:
    """北京时间跨日后锁定昨天及更早的运动评分，并按总分写入一次账本。"""
    today = _beijing_today()
    changed_users: set[int] = set()
    with store._transact() as conn:
        changed_users.update(_backfill_exercise_score_snapshots_in_txn(conn, today))
        yesterday = datetime.strptime(today, "%Y-%m-%d").date() - timedelta(days=1)
        for user_row in conn.execute("SELECT id FROM users").fetchall():
            user_id = int(user_row["id"])
            start = datetime.strptime(get_user_statistics_start_date(conn, user_id).date, "%Y-%m-%d").date()
            active_plan = _exercise_active_plan(conn, user_id)
            if active_plan == "v4":
                service = _exercise_v4()
                v4_cursor = max(start, datetime.strptime("2026-09-10", "%Y-%m-%d").date())
                while v4_cursor <= yesterday:
                    overdue_date = v4_cursor.isoformat()
                    diet_changed = service.close_diet(conn, user_id, overdue_date, _beijing_now())
                    body_fact = service.settle_body_deadline(conn, user_id, overdue_date, _beijing_now())
                    service.settle(conn, user_id, overdue_date, _beijing_now())
                    if diet_changed or (body_fact and body_fact.get("_changed")):
                        changed_users.add(user_id)
                    v4_cursor += timedelta(days=1)
                # V4 has its own score/reward lifecycle.  Do not fall through to
                # the legacy missing-snapshot penalty or score-band settlement.
                continue
            cursor = start
            while cursor <= yesterday:
                target_date = cursor.isoformat()
                existing = conn.execute(
                    "SELECT 1 FROM server_exercise_settlements WHERE user_id=? AND business_date=?",
                    (user_id, target_date),
                ).fetchone()
                scored = conn.execute(
                    "SELECT 1 FROM server_exercise_daily_logs WHERE user_id=? AND date=? AND score_snapshot IS NOT NULL",
                    (user_id, target_date),
                ).fetchone()
                if active_plan == "v4" and target_date < "2026-09-10" and not existing and not scored:
                    cursor += timedelta(days=1)
                    continue
                if not existing and not scored:
                    day_name = _exercise_day_key(target_date)
                    amount = 0 if day_name in {"六", "日"} else -50
                    status = "settled_zero" if amount == 0 else "settled_penalty"
                    settlement_id = f"exercise-settlement:{user_id}:{active_plan}:{target_date}"
                    now = _exercise_now_str()
                    conn.execute(
                        """INSERT OR IGNORE INTO server_exercise_settlements
                           (id,user_id,business_date,plan_version,score_snapshot,score_total,category_scores,completed_items,total_items,settlement_status,reason_code,rule_version,coin_amount,occurred_at,created_at,updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (settlement_id, user_id, target_date, active_plan, json.dumps({"total": 0, "cats": {}}, ensure_ascii=False), 0, "{}", 0, 0,
                         status, "missing_score_snapshot", "v1", amount, f"{target_date} 00:00:00", now, now),
                    )
                    source_id = f"exercise-score:{active_plan}:{target_date}"
                    title = f"{active_plan} {day_name} 0分 · 0/0项 · 缺少评分"
                    store.reward_settlement_service.settle_in_txn(
                        conn, user_id, amount, "exercise", title, "exercise_score", source_id,
                        target_date, amount >= 0, f"exercise-score:{user_id}:{active_plan}:{target_date}",
                        occurred_at=f"{target_date} 00:00:00",
                    )
                    settlement_row = conn.execute("SELECT * FROM server_exercise_settlements WHERE user_id=? AND business_date=? AND plan_version=?", (user_id, target_date, active_plan)).fetchone()
                    if settlement_row:
                        _exercise_write_change(conn, user_id, "exercise_settlement", settlement_row["id"], dict(settlement_row))
                    changed_users.add(user_id)
                cursor += timedelta(days=1)
        rows = conn.execute(
            """SELECT * FROM server_exercise_daily_logs
               WHERE date<? AND score_snapshot IS NOT NULL AND plan_version!='v4'""",
            (today,),
        ).fetchall()
        grouped: dict[tuple[int, str], list[dict]] = {}
        for raw in rows:
            row = dict(raw)
            try:
                snapshot = json.loads(row["score_snapshot"])
                row["_score_total"] = float(snapshot.get("total"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            grouped.setdefault((int(row["user_id"]), str(row["date"])[:10]), []).append(row)
        for (user_id, target_date), candidates in grouped.items():
            if target_date < get_user_statistics_start_date(conn, user_id).date:
                continue
            def authority_rank(value: dict):
                completed, total = int(value.get("completed_items") or 0), int(value.get("total_items") or 0)
                return (completed / total if total else -1, completed, value["_score_total"],
                        str(value.get("updated_at") or ""), str(value.get("plan_version") or "v0"))
            row = max(candidates, key=authority_rank)
            score_total = row["_score_total"]
            plan_version = str(row.get("plan_version") or "v0")
            source_id = f"exercise-score:{plan_version}:{target_date}"
            title = f"{row.get('plan_version') or 'v0'} {row.get('day_name') or '运动'}"
            reward = store.reward_rule_service.calculate_exercise_score_band(
                title, score_total, row.get("day_name"), row.get("completed_items"), row.get("total_items"),
            )
            reward = type(reward)(amount=reward.amount, title=f"{reward.title} · {int(round(score_total))}分 · {int(row.get('completed_items') or 0)}/{int(row.get('total_items') or 0)}项", is_makeup=reward.is_makeup, days_late=reward.days_late)
            expected_description = store.reward_settlement_service.format_description(
                reward.amount >= 0, "exercise", reward.title,
            )
            ledgers = conn.execute(
                """SELECT id,source_id,amount,description,occurred_at FROM server_reward_ledger
                   WHERE user_id=? AND source_type='exercise_score' AND target_date=?""",
                (user_id, target_date),
            ).fetchall()
            stale_ids = [item["id"] for item in ledgers if item["source_id"] != source_id]
            matching = next((item for item in ledgers if item["source_id"] == source_id), None)
            if matching and (
                float(matching["amount"]) != float(reward.amount)
                or matching["description"] != expected_description
                or matching["occurred_at"] != f"{target_date} 00:00:00"
            ):
                stale_ids.append(matching["id"])
                matching = None
            if stale_ids:
                store.reward_wallet_service.remove_ledger_entries_in_txn(
                    conn, user_id, stale_ids, backpack_event=None,
                )
                changed_users.add(user_id)
            existing = matching is not None
            should_settle = not existing
            if should_settle:
                store.reward_settlement_service.settle_in_txn(
                    conn, user_id, reward.amount, "exercise", reward.title, "exercise_score", source_id,
                    target_date, reward.amount >= 0, f"exercise-score:{user_id}:{plan_version}:{target_date}",
                    occurred_at=f"{target_date} 00:00:00",
                )
            settlement_id = f"exercise-settlement:{user_id}:{plan_version}:{target_date}"
            settlement_status = "settled_reward" if reward.amount > 0 else "settled_penalty" if reward.amount < 0 else "settled_zero"
            is_all_complete, completion_reward_amount, completion_reason = _settle_exercise_completion_reward_in_txn(
                conn, user_id, target_date, plan_version, _exercise_now_str(),
            )
            conn.execute(
                """INSERT INTO server_exercise_settlements
                   (id,user_id,business_date,plan_version,score_snapshot,score_total,category_scores,completed_items,total_items,settlement_status,reason_code,rule_version,coin_amount,is_all_complete,completion_reward_amount,completion_reason,occurred_at,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,business_date,plan_version) DO UPDATE SET score_snapshot=excluded.score_snapshot,score_total=excluded.score_total,
                     category_scores=excluded.category_scores,completed_items=excluded.completed_items,total_items=excluded.total_items,
                     settlement_status=excluded.settlement_status,reason_code=excluded.reason_code,coin_amount=excluded.coin_amount,is_all_complete=excluded.is_all_complete,
                     completion_reward_amount=excluded.completion_reward_amount,completion_reason=excluded.completion_reason,occurred_at=excluded.occurred_at,updated_at=excluded.updated_at""",
                (settlement_id, user_id, target_date, plan_version, row.get("score_snapshot"), score_total,
                 json.dumps(json.loads(row.get("score_snapshot") or "{}").get("cats", {}), ensure_ascii=False, sort_keys=True),
                 int(row.get("completed_items") or 0), int(row.get("total_items") or 0), settlement_status,
                 "score_band", "v1", reward.amount, int(is_all_complete), completion_reward_amount, completion_reason,
                 f"{target_date} 00:00:00", _exercise_now_str(), _exercise_now_str()),
            )
            settlement_row = conn.execute("SELECT * FROM server_exercise_settlements WHERE user_id=? AND business_date=? AND plan_version=?", (user_id, target_date, plan_version)).fetchone()
            if settlement_row:
                _exercise_write_change(conn, user_id, "exercise_settlement", settlement_row["id"], dict(settlement_row))
            for candidate in candidates:
                if candidate.get("locked_at") is None:
                    now = _exercise_now_str()
                    conn.execute("UPDATE server_exercise_daily_logs SET locked_at=?,updated_at=? WHERE id=?", (now, now, candidate["id"]))
                    _exercise_write_change(conn, user_id, "exercise_daily_log", candidate["id"], {**candidate, "locked_at": now, "updated_at": now})
                    changed_users.add(user_id)
            if should_settle:
                changed_users.add(user_id)
    for user_id in changed_users:
        sync_hub._notify_clients(["exercise_daily_logs", "exercise_item_scores", "exercise_settlements", "reward_ledger", "user_wallets"], user_id)
    return len(changed_users)


async def _run_goal_settlement_schedule():
    """服务启动补偿一次，随后在每个北京时间零点后运行。"""
    await asyncio.to_thread(_settle_completed_goal_periods)
    while True:
        now = datetime.now(timezone(timedelta(hours=8)))
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=1, microsecond=0)
        await asyncio.sleep(max(1, (next_midnight - now).total_seconds()))
        await asyncio.to_thread(_settle_completed_goal_periods)


async def _run_exercise_settlement_schedule():
    """服务启动补偿一次，随后在每个北京时间零点后锁定运动日。"""
    await asyncio.to_thread(_settle_completed_exercise_days)
    while True:
        now = datetime.now(timezone(timedelta(hours=8)))
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=1, microsecond=0)
        await asyncio.sleep(max(1, (next_midnight - now).total_seconds()))
        await asyncio.to_thread(_settle_completed_exercise_days)


async def _run_body_metric_deadline_schedule():
    """启动补偿一次；随后每天北京时间 09:00 由服务端执行不可逆锁。"""
    await asyncio.to_thread(_lock_overdue_body_metrics)
    while True:
        now = _beijing_now()
        next_run = now.replace(hour=9, minute=0, second=1, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        await asyncio.sleep(max(1, (next_run - now).total_seconds()))
        await asyncio.to_thread(_lock_overdue_body_metrics)


def _run_scheduled_sleep_automation(now=None):
    """补偿北京时间12:00入睡金币及22:30/22:35睡眠自动化。"""
    current = now or beijing_now()
    local = current.astimezone(BEIJING)
    minute = local.hour * 60 + local.minute
    if minute < 12 * 60:
        return 0
    sleep_date = local.strftime("%Y-%m-%d")
    steps = [STEP_BEDTIME_DEADLINE] if sleep_date >= BEDTIME_COIN_EFFECTIVE_DATE else []
    if minute >= 22 * 60 + 30:
        steps.append(STEP_TIMER_SWITCH)
    if minute >= 22 * 60 + 35:
        steps.append("full_analysis")
    if not steps:
        return 0
    with store._connect() as conn:
        user_ids = [int(row["id"]) for row in conn.execute("SELECT id FROM users")]
    created = 0
    for user_id in user_ids:
        if STEP_BEDTIME_DEADLINE in steps and sleep_automation_service.claim_step(user_id, sleep_date, STEP_BEDTIME_DEADLINE):
            try:
                store.sleep_reward_service.reconcile_bedtime_coin(user_id, sleep_date, deadline_reached=True)
                sleep_automation_service.finish_step(user_id, sleep_date, STEP_BEDTIME_DEADLINE, "done")
            except Exception as exc:
                sleep_automation_service.finish_step(user_id, sleep_date, STEP_BEDTIME_DEADLINE, "error", str(exc))
        if STEP_TIMER_SWITCH in steps:
            transition = sleep_automation_service.create_timer_switch(user_id, sleep_date)
            if transition:
                command = transition["command"]
                current_timer = _live_timer_service().read(user_id).get("state") or {}
                operation = "switch" if current_timer.get("active") else "start"
                outcome = _live_timer_service().command(user_id, operation, {
                    "session_id": f"sleep-{user_id}-{sleep_date}",
                    "device_id": "server-sleep-automation",
                    "observed_revision": int(current_timer.get("revision") or 0),
                    "idempotency_key": f"sleep-timer:{user_id}:{sleep_date}",
                    "user_intent_id": command["id"], "category_name": "睡觉",
                    "timer_mode": "countup", "duration_ms": 0,
                })
                if outcome.get("status") == "accepted":
                    sleep_automation_service.finish_timer_switch(user_id, sleep_date, "done")
                    sync_hub.notify_timer_state(user_id, outcome["revision"])
                    if outcome.get("completed_session_id"):
                        sync_hub.notify_completed_session(user_id)
                    created += 1
                else:
                    sleep_automation_service.finish_timer_switch(user_id, sleep_date, "error", outcome.get("error_code") or outcome.get("status"))
        if "full_analysis" in steps and sleep_automation_service.claim_full_analysis(user_id, sleep_date):
            existing_job = store.get_job_by_date(sleep_date, user_id=user_id)
            if _can_reuse_sleep_report(existing_job, full=True, force=False):
                sleep_automation_service.finish_full_analysis(user_id, sleep_date, "reused")
                created += 1
                continue
            sleep_data = store.get_huawei_sleep_data(user_id, sleep_date)
            image_path = ""
            has_structured_data = bool(sleep_data and SleepAnalyzer.validate_data(sleep_data)[0])
            if not has_structured_data:
                with store._connect() as conn:
                    image_row = conn.execute(
                        """SELECT image_path FROM server_sleep_jobs
                           WHERE user_id=? AND date=? AND image_path IS NOT NULL AND image_path<>''
                           ORDER BY updated_at DESC LIMIT 1""",
                        (user_id, sleep_date),
                    ).fetchone()
                image_path = str(image_row["image_path"] or "") if image_row else ""
            if not has_structured_data and not (image_path and os.path.exists(image_path)):
                sleep_automation_service.finish_full_analysis(user_id, sleep_date, "skipped_missing_source")
                continue
            request_id = f"sleep-auto:{user_id}:{sleep_date}"
            store.create_job(request_id, image_path, user_id=user_id, date=sleep_date)
            threading.Thread(
                target=_run_scheduled_full_sleep_analysis,
                args=(request_id, user_id, sleep_date, image_path), daemon=True,
            ).start()
            created += 1
    return created


def _run_scheduled_full_sleep_analysis(request_id: str, user_id: int, sleep_date: str, image_path: str):
    _run_analysis(request_id, image_path, user_id=user_id, full=True, force_refresh=False)
    job = store.get_job(request_id, user_id=user_id) or {}
    sleep_data = job.get("sleep_data") or {}
    has_full_report = (
        _report_status(job) == 2
        and sleep_data.get("full_report_state") == "generated"
        and _has_report(job)
    )
    if job.get("status") in {"done", "reused"} and has_full_report:
        status, detail = "done", None
    elif job.get("status") in {"done", "reused"} and sleep_data.get("full_report_state") == "insufficient_time_records":
        status, detail = "waiting_for_records", json.dumps({
            "reason": "insufficient_time_records",
            "tracked_duration_seconds": int(sleep_data.get("tracked_duration_seconds") or 0),
        })
    else:
        status, detail = "error", job.get("error") or "full_report_missing"
    sleep_automation_service.finish_full_analysis(user_id, sleep_date, status, detail)


async def _run_sleep_automation_schedule():
    """启动即补扫，并持续以一分钟频率生成睡眠切换事实。"""
    while True:
        await asyncio.to_thread(_run_scheduled_sleep_automation)
        now = beijing_now()
        wait_seconds = max(1, 60 - now.second - now.microsecond / 1_000_000)
        await asyncio.sleep(wait_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务生命周期：启动内部调度；TickTick 仅由清单显式请求。"""
    apply_runtime_logging_config()
    atimelogger_backup_task = None
    atimelogger_backup_worker = None
    atimelogger_reconcile_task = None
    goal_settlement_task = None
    exercise_settlement_task = None
    body_metric_deadline_task = None
    sleep_automation_task = None
    _migrate_flash_recommendations_on_startup()
    try:
        completed = sync_hub.run_startup_sync_migrations()
        logger.info("core sync historical version migration completed_users=%s", completed)
    except Exception as e:
        logger.error(f"❌ 服务端启动 core 同步历史版本迁移失败: {e}")
    _cleanup_stale_temp_upload_images(max_age_seconds=0)
    try:
        time_logger_db.reload_category_cache()
        logger.info("✅ 已完成服务端 server_categories 缓存预热同步")
    except Exception as e:
        logger.error(f"❌ 服务端启动分类缓存同步失败: {e}")
    try:
        _repair_learning_categories_on_startup()
    except Exception as e:
        logger.error(f"❌ 服务端启动学习分类修复失败: {e}")
    try:
        _repair_v4_diet_rule_keys_on_startup()
    except Exception as e:
        logger.error(f"❌ 服务端启动 V4 饮食规则修复失败: {e}")
    try:
        _retire_legacy_noon_bedtime_penalties_on_startup()
    except Exception as e:
        logger.error(f"❌ 服务端启动旧 noon 入睡处罚撤销失败: {e}")
    try:
        _materialize_reward_configs()
    except Exception as e:
        logger.error(f"❌ 服务端启动奖励配置补齐失败: {e}")

    atimelogger_backup_worker = ATimeLoggerFinalBackupWorker(
        ATimeLoggerBackupStore(store._connect),
        store._connect,
        lambda user_id: _load_user_provider_config(user_id, "atimelogger_config"),
        _mark_atimelogger_auth_required,
    )
    atimelogger_backup_task = asyncio.create_task(atimelogger_backup_worker.run())
    atimelogger_reconcile_task = asyncio.create_task(_run_atimelogger_reconciliation())
    goal_settlement_task = asyncio.create_task(_run_goal_settlement_schedule())
    exercise_settlement_task = asyncio.create_task(_run_exercise_settlement_schedule())
    body_metric_deadline_task = asyncio.create_task(_run_body_metric_deadline_schedule())
    sleep_automation_task = asyncio.create_task(_run_sleep_automation_schedule())
    try:
        yield
    finally:
        if atimelogger_backup_task:
            atimelogger_backup_worker.stop()
            atimelogger_backup_task.cancel()
            try:
                await atimelogger_backup_task
            except asyncio.CancelledError:
                logger.info("aTimeLogger 最终记录备份任务已停止")
        if atimelogger_reconcile_task and not atimelogger_reconcile_task.done():
            atimelogger_reconcile_task.cancel()
        if goal_settlement_task:
            goal_settlement_task.cancel()
            try:
                await goal_settlement_task
            except asyncio.CancelledError:
                logger.info("目标周期结算调度已停止")
        if exercise_settlement_task:
            exercise_settlement_task.cancel()
            try:
                await exercise_settlement_task
            except asyncio.CancelledError:
                logger.info("运动总分结算调度已停止")
        if body_metric_deadline_task:
            body_metric_deadline_task.cancel()
            try:
                await body_metric_deadline_task
            except asyncio.CancelledError:
                logger.info("体重体脂截止锁调度已停止")
        if sleep_automation_task:
            sleep_automation_task.cancel()
            try:
                await sleep_automation_task
            except asyncio.CancelledError:
                logger.info("睡眠自动化调度已停止")


app = FastAPI(
    title="MyTimeLogger Sleep Server API",
    version="1.0",
    lifespan=lifespan,
)
app.middleware("http")(request_logging_middleware)


def _cors_origins() -> list[str]:
    origins = server_config.get_cors("allowed_origins", [])
    if isinstance(origins, str):
        return [item.strip() for item in origins.split(",") if item.strip()]
    if isinstance(origins, list):
        return [str(item).strip() for item in origins if str(item).strip()]
    return []


def _is_allowed_cors_origin(origin: str | None) -> bool:
    return bool(origin and origin in set(_cors_origins()))


def _apply_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Vary"] = "Origin"


@app.middleware("http")
async def dynamic_cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = _is_allowed_cors_origin(origin)
    if request.method == "OPTIONS" and request.headers.get("access-control-request-method"):
        if not allowed or not origin:
            return Response(status_code=400)
        response = Response(status_code=200)
        _apply_cors_headers(response, origin)
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "*")
        response.headers["Access-Control-Max-Age"] = "600"
        return response

    response = await call_next(request)
    if allowed and origin:
        _apply_cors_headers(response, origin)
    return response


CORE_HEALTH_PATHS = {"/ping", "/api/sync/push", "/api/sync/pull"}


@app.middleware("http")
async def core_health_observability_middleware(request: Request, call_next):
    """仅观测 core 小同步生命周期；不读取请求体，也不触发外部提供方。"""
    if request.url.path not in CORE_HEALTH_PATHS:
        return await call_next(request)
    request_id = request.headers.get("x-sync-run-id") or request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("[core_health] request_id=%s route=%s stage=handler failure_category=%s elapsed_ms=%s",
                         request_id, request.url.path, type(exc).__name__, round((time.perf_counter() - started) * 1000, 2))
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    category = "server_error" if response.status_code >= 500 else "ok"
    logger.info("[core_health] request_id=%s route=%s stage=responded status=%s failure_category=%s elapsed_ms=%s",
                request_id, request.url.path, response.status_code, category, elapsed_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Core-Stage"] = "responded"
    return response


auth_scheme = HTTPBearer()
_login_failures: dict[str, tuple[int, float]] = {}


def _login_failure_limit() -> int:
    return int(server_config.get_security("login_failure_limit", 5) or 5)


def _login_lock_seconds() -> int:
    return int(server_config.get_security("login_lock_seconds", 300) or 300)


def _request_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown"))


def _login_key(request: Request, username: str) -> str:
    return f"{_request_ip(request)}:{str(username or '').strip().lower()}"


def _assert_login_allowed(request: Request, username: str) -> None:
    key = _login_key(request, username)
    count, until = _login_failures.get(key, (0, 0.0))
    now = time.time()
    if count >= _login_failure_limit() and until > now:
        raise HTTPException(status_code=429, detail="Too many login attempts, please retry later")
    if until <= now:
        _login_failures.pop(key, None)


def _record_login_result(request: Request, username: str, success: bool) -> None:
    key = _login_key(request, username)
    if success:
        _login_failures.pop(key, None)
        return
    count, until = _login_failures.get(key, (0, 0.0))
    now = time.time()
    count = count + 1 if until <= now else count + 1
    lock_until = now + _login_lock_seconds() if count >= _login_failure_limit() else 0.0
    _login_failures[key] = (count, lock_until)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    token = credentials.credentials
    user = store.get_user_by_session(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_service_manager(user: dict):
    """服务级配置仅允许首个注册的默认用户管理。"""
    if not _is_service_manager(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅服务管理者可操作服务级配置")
    return user


def _is_service_manager(user: dict) -> bool:
    return int(user.get("id") or -1) == int(store.get_default_user_id() or -2)

def get_current_user_optional(
    token: str | None = None,
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False))
):
    """仅接受 Bearer 会话或同一会话的 SSE query token。"""
    if credentials:
        user = store.get_user_by_session(credentials.credentials)
        if user: return user

    # Query Token 鉴权 (针对 EventSource)
    if token:
        user = store.get_user_by_session(token)
        if user: return user

    raise HTTPException(status_code=401, detail="Authentication required")


def _live_timer_service() -> LiveTimerLeaseService:
    return LiveTimerLeaseService(store._connect)


def _require_timer_state_capability(request: Request) -> None:
    if request.headers.get("X-MTL-Timer-State") != TIMER_STATE_CAPABILITY:
        raise HTTPException(status_code=426, detail="客户端需要升级以启用跨端当前计时")


def _lease_response(result: dict, accepted_status: int = 200) -> JSONResponse:
    if result.get("status") == "conflict":
        return JSONResponse(status_code=409, content=result)
    if result.get("status") == "accepted":
        return JSONResponse(status_code=accepted_status, content=result)
    return JSONResponse(status_code=200, content=result)


def build_ai_cfg():
    raise HTTPException(status_code=400, detail="当前用户未配置大模型，请先在我的大模型中填写配置")


def build_ai_cfg_for_user(user_id: int):
    cfg = _load_user_provider_config(user_id, "ai_model_config")
    if not _configured(cfg.get("vision_base_url"), cfg.get("vision_api_key"), cfg.get("vision_model")):
        raise HTTPException(status_code=400, detail="当前用户未配置视觉大模型，请先在我的大模型中填写配置")
    if not _configured(cfg.get("text_base_url"), cfg.get("text_api_key"), cfg.get("text_model")):
        raise HTTPException(status_code=400, detail="当前用户未配置文本大模型，请先在我的大模型中填写配置")
    return {
        "vision_base_url": cfg.get("vision_base_url", ""),
        "vision_api_key": cfg.get("vision_api_key", ""),
        "vision_model": cfg.get("vision_model", ""),
        "text_base_url": cfg.get("text_base_url", ""),
        "text_api_key": cfg.get("text_api_key", ""),
        "text_model": cfg.get("text_model", ""),
        "backup_base_url": cfg.get("backup_base_url", ""),
        "backup_api_key": cfg.get("backup_api_key", ""),
        "backup_model": cfg.get("backup_model", ""),
    }


def _management_plan_model_runner(user_id: int):
    """返回受限的文本模型调用器；不会把密钥写入日志或草案。"""
    cfg = _load_user_provider_config(user_id, "ai_model_config")
    base_url = str(cfg.get("text_base_url") or "").strip()
    api_key = str(cfg.get("text_api_key") or "").strip()
    model = str(cfg.get("text_model") or "").strip()
    if not (base_url and api_key and model):
        raise ManagementPlanError("ai_config_required", "当前账号未配置可用的文本大模型", status=400)

    def normalize_payload(payload: object, intent: str) -> object:
        if not isinstance(payload, dict):
            return payload
        if intent == "review":
            source = payload.get("review") if isinstance(payload.get("review"), dict) else payload
            review = {key: ([value] if isinstance((value := source.get(key)), str) and value.strip() else value) for key in ("strengths", "risks", "recommendations")}
            if any(value is not None for value in review.values()):
                return {**payload, "items": [], "review": review, "mode": "review"}
            if isinstance(payload.get("items"), list) and not payload["items"]:
                summary = payload.get("summary")
                return {**payload, "items": [], "mode": "review", "review": {"strengths": [summary] if isinstance(summary, str) and summary.strip() else [], "risks": [], "recommendations": []}}
            return payload
        if not isinstance(payload.get("items"), list):
            return payload
        namespaces = {
            "existing_task_reward": "task", "ticktick_task": "task",
            "existing_habit_reward": "habit", "local_habit": "habit",
            "learning": "learning", "exercise": "exercise", "goal": "goal", "reward_item": "reward",
        }
        key_pattern = re.compile(r"^[a-z][a-z0-9-]{1,80}\.[a-z0-9][a-z0-9._-]{0,120}$")
        items = []
        used_keys: set[str] = set()
        for index, item in enumerate(payload["items"], start=1):
            if not isinstance(item, dict):
                items.append(item)
                continue
            normalized = dict(item)
            if normalized.get("type") == "sleep":
                normalized["type"] = "goal"
            logical_key = normalized.get("logical_key")
            if isinstance(logical_key, str) and "." in logical_key:
                namespace, local_key = logical_key.split(".", 1)
                normalized["logical_key"] = f"{namespace.replace('_', '-')}.{local_key}"
            candidate = normalized.get("logical_key")
            if not isinstance(candidate, str) or not key_pattern.fullmatch(candidate) or candidate in used_keys:
                namespace = namespaces.get(str(normalized.get("type") or ""), "plan")
                candidate = f"{namespace}.item-{index}"
                suffix = 2
                while candidate in used_keys:
                    candidate = f"{namespace}.item-{index}-{suffix}"
                    suffix += 1
                normalized["logical_key"] = candidate
            used_keys.add(str(normalized["logical_key"]))
            items.append(normalized)
        return {**payload, "items": items}

    def run(request_text: str, context: dict) -> dict:
        from openai import APIConnectionError, APIStatusError, OpenAI

        # Model endpoints are direct user-configured HTTPS services. Do not inherit
        # a machine proxy that may replace their certificate chain.
        http_client = httpx.Client(trust_env=False)
        intent = str(context.get("planning_intent") or "proposal")
        logger.info("management_plan step=model_request_start user_id=%s intent=%s retry=%s evidence_rules=%s evidence_store=%s", user_id, intent, bool(context.get("review_contract_retry")), len((context.get("review_evidence") or {}).get("reward_rules", [])), len((context.get("review_evidence") or {}).get("store_items", [])))
        system_prompt = (
            "你是 MyTimeLogger 的自我管理方案规划器。只返回 JSON 对象，格式为 "
            f"{{schema_version:'1',mode:'{intent}',policy_version:string,title:string,plan_key:string,summary:string,items:[]}}。"
            "items 只能使用 existing_task_reward、existing_habit_reward、ticktick_task、local_habit、"
            "learning、exercise、goal、reward_item 类型；每项必须有 logical_key、type、action。"
            "logical_key 必须严格使用英文命名空间.英文键，例如 reward.weekend-game 或 habit.morning-brush，"
            "符合 ^[a-z][a-z0-9-]{1,80}\\.[a-z0-9][a-z0-9._-]{0,120}$，不得使用中文、空格或下划线分隔命名空间。"
            "action 只能是 create、update、bind、keep、disable。"
            "所有面向用户的自然语言字段必须使用简体中文；必要英文专名只能出现在中文句子中。"
            "合法项目示例：{logical_key:'reward.weekend-game',type:'reward_item',action:'create',reward:{coins:8}}。"
            "禁止输出 SQL、URL、凭据、钱包、流水、背包事件和小时级日历。"
            + ("上一次输出未通过 review 合同。必须返回 review 对象，且 strengths、risks、recommendations 都是字符串数组，items 必须是 []。" if context.get("review_contract_retry") else "")
            + ("上一次输出包含非简体中文。请只返回简体中文自然语言，保持 JSON 合同、动作和数值不变。" if context.get("language_contract_retry") else "")
            + system_policy_prompt(intent)
        )
        try:
            client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"), http_client=http_client)
            response = client.chat.completions.create(
                model=model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps({"request": request_text, "context": context}, ensure_ascii=False)},
                ],
            )
            content = response.choices[0].message.content if response.choices else "{}"
            logger.info("management_plan step=model_response_received user_id=%s intent=%s content_length=%s choices=%s", user_id, intent, len(content or ""), len(response.choices or []))
            try:
                return normalize_payload(json.loads(content or "{}"), intent)
            except json.JSONDecodeError as exc:
                raise ManagementPlanError("ai_response_invalid", "模型没有返回合法 JSON", status=422) from exc
        except (APIConnectionError, httpx.HTTPError) as exc:
            logger.warning("management plan model connection failed user_id=%s error_type=%s", user_id, type(exc).__name__)
            raise ManagementPlanError("ai_connection_failed", "大模型连接失败，请检查网络后重试", status=502) from exc
        except APIStatusError as exc:
            logger.warning(
                "management plan model provider failed user_id=%s error_type=%s status_code=%s",
                user_id,
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )
            raise ManagementPlanError("ai_provider_failed", "大模型服务返回错误，请检查模型配置后重试", status=502) from exc
        finally:
            http_client.close()

    return run


def _flash_card_polish_runner(user_id: int):
    """Return a text-only AI command. Card text is never written to logs."""
    cfg = _load_user_provider_config(user_id, "ai_model_config")
    base_url = str(cfg.get("text_base_url") or "").strip()
    api_key = str(cfg.get("text_api_key") or "").strip()
    model = str(cfg.get("text_model") or "").strip()
    if not (base_url and api_key and model):
        raise FlashCardError("ai_config_required", "当前账号未配置可用的文本大模型", 400)

    def run(original_text: str) -> str:
        from openai import APIConnectionError, APIStatusError, OpenAI

        http_client = httpx.Client(trust_env=False)
        logger.info("flash_card step=polish_request_start user_id=%s text_length=%s", user_id, len(original_text))
        try:
            client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"), http_client=http_client)
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "你只做忠实润色。删除语气词和重复，修复明显错别字与不通顺表达；不得改变原义，不得添加任何事实、计划、时间、人物或结论。只返回 JSON：{\"polished_text\":\"...\"}。"},
                    {"role": "user", "content": original_text},
                ],
            )
            content = response.choices[0].message.content if response.choices else "{}"
            result = json.loads(content or "{}")
            value = result.get("polished_text") if isinstance(result, dict) else None
            if not isinstance(value, str):
                raise FlashCardError("flash_card_polish_invalid", "AI 润色结果格式无效", 422)
            logger.info("flash_card step=polish_response_received user_id=%s output_length=%s", user_id, len(value))
            return value
        except FlashCardError:
            raise
        except (APIConnectionError, httpx.HTTPError, APIStatusError, json.JSONDecodeError) as exc:
            logger.warning("flash_card step=polish_failed user_id=%s error_type=%s", user_id, type(exc).__name__)
            raise FlashCardError("flash_card_polish_failed", "AI 润色失败，请稍后重试", 502) from exc
        finally:
            http_client.close()

    return run


def _flash_todo_diary_skill(user_id: int | None = None) -> str:
    if user_id:
        active = flash_skill_feedback_service.active_content(user_id)
        if active:
            return active
    with open(os.path.join(os.path.dirname(__file__), "skills", "flash-todo-diary-extraction", "SKILL.md"), encoding="utf-8") as handle:
        return handle.read()


def _flash_skill_creator_instruction() -> str:
    with open(os.path.join(os.path.dirname(__file__), "skills", "flash-skill-creator", "SKILL.md"), encoding="utf-8") as handle:
        return handle.read()


FLASH_SKILL_BASE_VERSION = "flash-todo-diary-extraction-v10"


def _flash_skill_version(user_id: int) -> str:
    return flash_skill_feedback_service.active_version(user_id) or FLASH_SKILL_BASE_VERSION


_FLASH_ACTION_STATES = {"actionable", "completed", "non_action", "none"}
_FLASH_ACTION_SCOPES = {"pending_action": "actionable", "completed_or_cancelled": "completed", "meta_record": "completed", "non_action": "non_action", "none": "none"}
_FLASH_AFFECT_SCOPES = {"current_experience", "future_attitude", "none"}
_FLASH_AFFECT_STATES = {"emotion", "physical_feeling", "subjective_evaluation", "none"}
_FLASH_FAMILY_STATES = {"pleasant": "emotion", "calm": "emotion", "anxious": "emotion", "sad": "emotion", "angry": "emotion", "frustrated": "emotion", "fatigued": "physical_feeling", "discomfort": "physical_feeling", "confused": "emotion"}
_FLASH_FAMILY_EMOJIS = {"pleasant": "😄", "calm": "😌", "anxious": "😰", "sad": "😢", "angry": "😠", "frustrated": "😣", "fatigued": "😫", "discomfort": "😣", "confused": "😕"}
_FLASH_LEGACY_MOOD_EMOJIS = {"烦": "😣", "烦躁": "😣", "焦虑": "😰", "难过": "😢", "委屈": "🥺", "生气": "😠", "疲惫": "😫", "累": "😫", "开心": "😄", "满足": "😊", "平静": "😌", "踏实": "😌", "放松": "😮‍💨", "困惑": "😕"}


def _model_candidates(cfg: dict, modality: str) -> list[dict]:
    prefixes = [modality, f"{modality}_backup_1", f"{modality}_backup_2"]
    candidates = []
    for index, prefix in enumerate(prefixes):
        values = {"slot": "主模型" if index == 0 else f"备用模型 {index}", "base_url": str(cfg.get(f"{prefix}_base_url") or "").strip(), "api_key": str(cfg.get(f"{prefix}_api_key") or "").strip(), "model": str(cfg.get(f"{prefix}_model") or "").strip()}
        if modality == "vision" and index == 1 and not all(values[key] for key in ("base_url", "api_key", "model")):
            values.update({"base_url": str(cfg.get("backup_base_url") or "").strip(), "api_key": str(cfg.get("backup_api_key") or "").strip(), "model": str(cfg.get("backup_model") or "").strip()})
        if all(values[key] for key in ("base_url", "api_key", "model")):
            candidates.append(values)
    return candidates


def _valid_flash_diary(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    mood, content, family = (str(value.get(key) or "").strip() for key in ("mood", "content", "emotion_family"))
    if mood.lower() in ("null", "none") or content.lower() in ("null", "none"):
        return None
    if not re.search(r"[\u4e00-\u9fff]", mood):
        return None
    emoji = _FLASH_FAMILY_EMOJIS.get(family) or _FLASH_LEGACY_MOOD_EMOJIS.get(mood)
    return {"mood": f"{mood} {emoji}", "content": content} if emoji and content and len(content) <= 1000 else None


def _valid_flash_todos(value: object) -> list[dict]:
    if not isinstance(value, list) or len(value) > 3:
        return []
    todos = []
    for item in value:
        title, reason = (str(item.get(key) or "").strip() for key in ("task", "reason")) if isinstance(item, dict) else ("", "")
        if title and len(title) <= 120 and len(reason) <= 240 and title not in {entry["title"] for entry in todos}:
            todos.append({"title": title, "reason": reason})
    return todos


def _flash_evidence_matches(text: str, evidence: str) -> bool:
    normalize = lambda value: re.sub(r"[\s，。！？、,.!?：:；;‘’“”\"']+", "", value)
    return bool(evidence) and normalize(evidence) in normalize(text)


def _faithful_flash_polish(text: str, proposed: str) -> str:
    return validate_minimal_polish(text, proposed)[0]


def _flash_semantic_result(payload: object, text: str) -> tuple[dict | None, bool, str]:
    if not isinstance(payload, dict):
        return None, False, ""
    proposed = str(payload.get("polished_text") or "").strip()
    if not proposed:
        return None, False, ""
    polished, polish_code, edits = validate_minimal_polish(text, proposed)
    audit = {"_polish_code": polish_code, "_polish_edit_count": len(edits)}
    todos, diary = _valid_flash_todos(payload.get("todos")), _valid_flash_diary(payload.get("diary"))
    has_contract = "action_state" in payload or "affect_state" in payload
    if not has_contract:
        return {"polished_text": polished, "todos": todos, "diary": diary} | audit, True, ""
    action_state, affect_state = str(payload.get("action_state") or ""), str(payload.get("affect_state") or "")
    affect_state = _FLASH_FAMILY_STATES.get(affect_state, affect_state)
    action_evidence, affect_evidence = str(payload.get("action_evidence") or "").strip(), str(payload.get("affect_evidence") or "").strip()
    if action_state not in _FLASH_ACTION_STATES or affect_state not in _FLASH_AFFECT_STATES:
        return {"polished_text": polished, "todos": [], "diary": None} | audit, False, action_state
    action_scope = str(payload.get("action_scope") or "")
    action_scope_ok = not action_scope or _FLASH_ACTION_SCOPES.get(action_scope) == action_state
    action_ok = action_scope_ok and (action_state == "actionable") == bool(todos) and (action_state == "none" or _flash_evidence_matches(text, action_evidence))
    affect_scope = str(payload.get("affect_scope") or "")
    scope_ok = not affect_scope or (affect_scope in _FLASH_AFFECT_SCOPES and (affect_scope == "current_experience") == (affect_state != "none"))
    affect_ok = scope_ok and (affect_state != "none") == bool(diary) and (affect_state == "none" or _flash_evidence_matches(text, affect_evidence))
    result = {"polished_text": polished, "todos": todos if action_ok else [], "diary": diary if affect_ok else None} | audit
    return result, action_ok and affect_ok, action_state


def _normalize_flash_semantics(payload: object, text: str) -> dict | None:
    result, consistent, _ = _flash_semantic_result(payload, text)
    return result if consistent else None


def _repair_flash_semantics(text: str, raw_output: str, candidate: dict, client, openai, skill: str, review_completed: bool = False, polish_only: bool = False) -> tuple[dict | None, str]:
    try:
        review_rule = "只修复上下文唯一确定的错别字、重复、赘余、标点或单一病句；保留其余原文、口语和俚语，禁止改写或补充事实。" if polish_only else ("首轮 completed 结论不被直接接受。只有原文明示谁已经做完以及完成事实/结果，才能保留 completed；没有叙述主体的独立备忘短句必须改为 actionable 并生成待办。" if review_completed else "逐项核对语义状态、逐字证据和可选结果；每个枚举字段只能返回一个合法值，禁止复制带 | 的枚举说明。")
        response = openai(api_key=candidate["api_key"], base_url=candidate["base_url"].rstrip("/"), http_client=client).chat.completions.create(
            model=candidate["model"], temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": f"{review_rule}\n{skill}"}, {"role": "user", "content": f"原文：{text}\n首轮结构：{raw_output}\n重新裁决并只返回修正后的完整 JSON。"}],
        )
        repaired_raw = str(response.choices[0].message.content or "")
        return _normalize_flash_semantics(json.loads(repaired_raw or "{}"), text), repaired_raw
    except Exception:
        return None, ""


def _review_flash_completion(text: str, candidate: dict, client, openai) -> tuple[bool, dict | None]:
    try:
        response = openai(api_key=candidate["api_key"], base_url=candidate["base_url"].rstrip("/"), http_client=client).chat.completions.create(
            model=candidate["model"], temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": "只做句法信息抽取，不判断完成态。actor_evidence 必须逐字复制原文中明确出现的动作执行者；省略的执行者不能推断，动作对象不是执行者。同时生成简洁 candidate_task 和 candidate_reason。只返回 {\"actor_kind\":\"explicit|omitted\",\"actor_evidence\":\"\",\"candidate_task\":\"\",\"candidate_reason\":\"\"}。"}, {"role": "user", "content": text}],
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        actor = str(payload.get("actor_evidence") or "").strip()
        normalized_actor = re.sub(r"\s+", "", actor)
        normalized_text = re.sub(r"\s+", "", text)
        actor_is_local = bool(normalized_actor) and normalized_actor != normalized_text and len(normalized_actor) <= 20
        explicitly_completed = str(payload.get("actor_kind") or "") == "explicit" and actor_is_local and _flash_evidence_matches(text, actor)
        task = str(payload.get("candidate_task") or "").strip()
        reason = "闪念中的备忘行动"
        return explicitly_completed, {"title": task, "reason": reason} if task and len(task) <= 120 and len(reason) <= 240 else None
    except Exception:
        return True, None


def _flash_todo_diary_analysis(user_id: int, text: str, skill: str | None = None) -> dict:
    cfg = _load_user_provider_config(user_id, "ai_model_config")
    candidates = _model_candidates(cfg, "text")
    if not candidates:
        raise FlashCardError("flash_insight_config_required", "当前账号未配置可用的文本大模型", 400)
    from openai import OpenAI
    client = httpx.Client(trust_env=False)
    raw_output, attempts, call_succeeded = "", [], False
    try:
        skill = skill or _flash_todo_diary_skill(user_id)
        for candidate in candidates:
            try:
                response = OpenAI(api_key=candidate["api_key"], base_url=candidate["base_url"].rstrip("/"), http_client=client).chat.completions.create(model=candidate["model"], temperature=0, response_format={"type": "json_object"}, messages=[{"role": "system", "content": skill}, {"role": "user", "content": text}])
                call_succeeded = True
                raw_output = str(response.choices[0].message.content or "")
                try:
                    payload = json.loads(raw_output or "{}")
                except json.JSONDecodeError:
                    repaired, repaired_raw = _repair_flash_semantics(text, raw_output, candidate, client, OpenAI, skill)
                    if repaired:
                        return repaired | {"raw_output": repaired_raw, "attempts": attempts + [{"slot": candidate["slot"], "status": "done"}, {"stage": "semantic_repair", "code": "done"}]}
                    return {"polished_text": text.strip(), "todos": [], "diary": None, "_polish_code": "polish_contract_invalid", "_polish_edit_count": 0, "raw_output": raw_output, "attempts": attempts + [{"slot": candidate["slot"], "status": "done"}, {"stage": "semantic_repair", "code": "invalid"}]}
                polished = str(payload.get("polished_text") or "").strip() if isinstance(payload, dict) else ""
                if not polished:
                    attempts.append({"slot": candidate["slot"], "stage": "contract", "code": "invalid_polished_text"})
                    continue
                fallback, consistent, action_state = _flash_semantic_result(payload, text)
                normalized = fallback if consistent else None
                polish_attempt = []
                if normalized and normalized.get("_polish_code") != "polish_accepted":
                    repaired, repaired_raw = _repair_flash_semantics(text, raw_output, candidate, client, OpenAI, skill, polish_only=True)
                    if repaired:
                        normalized, raw_output = repaired, repaired_raw
                        polish_attempt = [{"stage": "polish_retry", "code": "accepted" if repaired.get("_polish_code") == "polish_accepted" else "fallback"}]
                    else:
                        polish_attempt = [{"stage": "polish_retry", "code": "invalid"}]
                if normalized and action_state != "completed":
                    return normalized | {"raw_output": raw_output, "attempts": attempts + [{"slot": candidate["slot"], "status": "done"}] + polish_attempt}
                if normalized and action_state == "completed" and payload.get("action_scope") == "meta_record":
                    return normalized | {"raw_output": raw_output, "attempts": attempts + [{"slot": candidate["slot"], "status": "done"}] + polish_attempt}
                if normalized and action_state == "completed":
                    completed, candidate_task = _review_flash_completion(text, candidate, client, OpenAI)
                    if completed or not candidate_task:
                        return normalized | {"raw_output": raw_output, "attempts": attempts + [{"slot": candidate["slot"], "status": "done"}] + polish_attempt + [{"stage": "completion_review", "code": "completed"}]}
                    normalized["todos"] = [candidate_task]
                    return normalized | {"raw_output": raw_output, "attempts": attempts + [{"slot": candidate["slot"], "status": "done"}] + polish_attempt + [{"stage": "completion_review", "code": "actionable"}]}
                repaired, repaired_raw = _repair_flash_semantics(text, raw_output, candidate, client, OpenAI, skill, review_completed=action_state == "completed")
                if repaired:
                    return repaired | {"raw_output": repaired_raw, "attempts": attempts + [{"slot": candidate["slot"], "status": "done"}, {"stage": "semantic_repair", "code": "done"}]}
                fallback = fallback or {"polished_text": polished, "todos": [], "diary": None}
                return fallback | {"raw_output": raw_output, "attempts": attempts + [{"slot": candidate["slot"], "status": "done"}, {"stage": "semantic_repair", "code": "invalid"}]}
            except ValueError as exc: attempts.append({"slot": candidate["slot"], "stage": "contract", "code": str(exc)})
            except Exception as exc: attempts.append({"slot": candidate["slot"], "stage": "provider", "code": type(exc).__name__})
        if call_succeeded:
            return {"polished_text": text.strip(), "todos": [], "diary": None, "_polish_code": "polish_contract_invalid", "_polish_edit_count": 0, "raw_output": raw_output, "attempts": attempts}
        error = FlashCardError("flash_insight_analysis_failed", "闪念分析失败，请稍后重试", 502)
        error.raw_output, error.attempts = raw_output, attempts
        raise error
    except FlashCardError:
        raise
    except Exception as exc:
        logger.warning("flash_insight step=failed user_id=%s error_type=%s", user_id, type(exc).__name__)
        error = FlashCardError("flash_insight_analysis_failed", "闪念分析失败，请稍后重试", 502)
        error.raw_output = raw_output
        error.attempts = attempts
        raise error from exc
    finally:
        client.close()


def _flash_feedback_analysis(user_id: int, text: str, label: str) -> dict:
    if label not in {"todo", "mood"}:
        raise FlashCardError("flash_feedback_label_invalid", "反馈分类无效")
    constraint = "人工已确认：这是待办。必须只保留原文直接表达的待办，diary 必须为 null。" if label == "todo" else "人工已确认：这是心情卡片。不得生成 todos；只在原文有真实感受时生成 diary。"
    result = _flash_todo_diary_analysis(user_id, text, f"{_flash_todo_diary_skill(user_id)}\n\n{constraint}")
    return result | ({"diary": None} if label == "todo" else {"todos": []})


def _flash_skill_candidate_contract(content: str) -> tuple[bool, str]:
    required = ("# Flash Todo Diary Extraction Skill", "polished_text", "diary", "todos", "action_evidence", "affect_evidence")
    missing = [value for value in required if value not in content]
    return (not missing, "passed" if not missing else f"missing:{','.join(missing)}")


def _evaluate_flash_skill_candidate(user_id: int, content: str, samples: list[dict]) -> tuple[bool, str]:
    valid, summary = _flash_skill_candidate_contract(content)
    if not valid:
        return False, summary
    retained = [sample for sample in samples if sample.get("kind") == "classification"][:6]
    cases = [{"input": "明天把垃圾带下楼", "expected_label": "todo"}, {"input": "antigravity真是战犯，纯粹是卧底捣乱。", "expected_label": "mood"}] + retained
    for case in cases:
        result = _flash_todo_diary_analysis(user_id, case["input"], content)
        polished = str(result.get("polished_text") or "").strip()
        if not polished or _faithful_flash_polish(case["input"], polished) != polished:
            return False, "fixed_polish_fidelity_failed"
        if case["expected_label"] == "todo" and (not result["todos"] or result["diary"] is not None):
            return False, "todo_regression_failed"
        if case["expected_label"] == "mood" and (result["todos"] or result["diary"] is None):
            return False, "mood_regression_failed"
    must_correct = [
        ("切尔西买了一个有一个，三层巴士了！", "切尔西买了一个又一个，三层巴士了！"),
        ("我今夭很烦", "我今天很烦"),
        ("好烦烦啊", "好烦啊"),
        ("大约半个小时左右", "大约半个小时"),
    ]
    for source, expected in must_correct:
        if str(_flash_todo_diary_analysis(user_id, source, content).get("polished_text") or "").strip() != expected:
            return False, "fixed_polish_correction_failed"
    must_keep = ("antigravity真是战犯啊！纯粹是卧底捣乱的！", "切尔西买了一个又一个，三层巴士了！")
    for source in must_keep:
        if str(_flash_todo_diary_analysis(user_id, source, content).get("polished_text") or "").strip() != source:
            return False, "fixed_polish_preservation_failed"
    for case in [sample for sample in samples if sample.get("kind") == "polish"][:6]:
        result = _flash_todo_diary_analysis(user_id, case["input"], content)
        if str(result.get("polished_text") or "").strip() != str(case["expected_output"]).strip():
            return False, "polish_retained_set_failed"
    return True, "fixed_labels_and_proofreading_sets_passed"


def _try_refresh_flash_skill(user_id: int) -> None:
    samples = flash_skill_feedback_service.feedback_samples(user_id)
    if len(samples) < 3:
        return
    candidates = _model_candidates(_load_user_provider_config(user_id, "ai_model_config"), "text")
    if not candidates:
        return
    from openai import OpenAI
    client = httpx.Client(trust_env=False)
    try:
        provider = candidates[0]
        response = OpenAI(api_key=provider["api_key"], base_url=provider["base_url"].rstrip("/"), http_client=client).chat.completions.create(
            model=provider["model"], temperature=0, messages=[
                {"role": "system", "content": _flash_skill_creator_instruction()},
                {"role": "user", "content": json.dumps(samples, ensure_ascii=False)},
            ],
        )
        candidate = flash_skill_feedback_service.create_candidate(user_id, str(response.choices[0].message.content or ""), samples, _flash_skill_version(user_id), _flash_todo_diary_skill(user_id))
        flash_skill_feedback_service.evaluate_and_activate(user_id, candidate["id"], lambda content: _evaluate_flash_skill_candidate(user_id, content, samples))
    except Exception as exc:
        logger.warning("flash_skill step=candidate_skipped user_id=%s error_type=%s", user_id, type(exc).__name__)
    finally:
        client.close()


def _queue_for(request_id):
    if request_id not in progress_queues:
        progress_queues[request_id] = queue.Queue(maxsize=50)
    return progress_queues[request_id]


def _push_progress(request_id, payload):
    progress_latest[request_id] = payload
    q = _queue_for(request_id)
    try:
        q.put_nowait(payload)
    except queue.Full:
        pass


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _has_report(job: dict | None) -> bool:
    if not job:
        return False
    if job.get("analysis_report"):
        return True
    sleep_data = job.get("sleep_data") or {}
    return bool(sleep_data.get("analysis_report"))


def _report_status(job: dict | None) -> int:
    if not job:
        return 0
    sleep_data = job.get("sleep_data") or {}
    try:
        return int(sleep_data.get("report_status") or 0)
    except (TypeError, ValueError):
        return 0


def _can_reuse_sleep_report(job: dict | None, *, full: bool, force: bool) -> bool:
    if not job or force or not _has_report(job):
        return False
    if full and (job.get("sleep_data") or {}).get("full_report_state") != "generated":
        return False
    return _report_status(job) == (2 if full else 1)


def _public_job(job):
    if not job:
        return None
    # 兼容处理：支持从 store._row_to_dict 出来的 sleep_data 字段
    result = job.get("sleep_data") or {}
    date_str = job.get("date") or result.get("date") or result.get("sleep_date")

    user_id = job.get("user_id") or store.get_default_user_id()
    if date_str and user_id:
        try:
            db_data = store.get_huawei_sleep_data(user_id, date_str)
            if db_data:
                result = dict(result)
                for k, v in db_data.items():
                    if v is not None:
                        result[k] = v
        except Exception as e:
            logger.error(f"从底层数据库回填 _public_job 失败: {e}")

    # 强行确保 result 里有 date / sleep_date 字段，防止前端界面产生 undefined 日期
    if date_str:
        result = dict(result)
        result["date"] = date_str
        result["sleep_date"] = date_str

    # 确保 report_status 存在，至少为 0
    if "report_status" not in result:
        result = dict(result)
        result["report_status"] = 0

    # 优先从字段读取，如果没有则从 result 字典里读
    raw_report = job.get("analysis_report") or result.get("analysis_report") or ""

    if raw_report:
        result = dict(result)
        result["analysis_report"] = raw_report
        result["analysis_html"] = markdown.markdown(raw_report, extensions=["fenced_code", "tables"])

    return {
        "request_id": job.get("request_id"),
        "date": job.get("date") or result.get("date") or result.get("sleep_date"),
        "status": "done" if job.get("status") == "reused" else job.get("status"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error"),
        "result": result,
    }


def _cleanup_queue(request_id: str, delay_seconds: int = 300):
    """
    延迟清理 progress_queues 中的队列对象，防止内存泄漏。

    分析完成后队列不再需要，但客户端可能还在读取最后几条消息，
    因此延迟 5 分钟（默认）后再清理，给客户端足够时间消费完队列。

    Args:
        request_id: 要清理的队列对应的 request_id
        delay_seconds: 延迟秒数，默认 300（5 分钟）
    """
    def _do_cleanup():
        import time
        time.sleep(delay_seconds)
        progress_queues.pop(request_id, None)
        progress_latest.pop(request_id, None)
        logger.debug(f"🧹 Cleaned up progress queue for request_id={request_id}")
    threading.Thread(target=_do_cleanup, daemon=True).start()


def _normalize_sleep_date(value):
    if not value:
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    return None


def _set_job_image_path(request_id, image_path):
    try:
        conn = store._connect()
        conn.execute(
            "UPDATE server_sleep_jobs SET image_path=? WHERE request_id=?",
            (image_path, request_id),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"更新 job 数据库图片路径失败: {exc}")


def _cleanup_temp_upload_image(request_id, image_path=None):
    candidates = []
    if image_path:
        candidates.append(image_path)
    attachments_root = os.path.abspath(ATTACHMENTS_DIR)
    try:
        if os.path.isdir(ATTACHMENTS_DIR):
            for name in os.listdir(ATTACHMENTS_DIR):
                if name.startswith(f"{request_id}_"):
                    candidates.append(os.path.join(ATTACHMENTS_DIR, name))
    except Exception as exc:
        logger.warning("扫描临时上传图片失败: request_id=%s error=%s", request_id, exc)

    for path in dict.fromkeys(candidates):
        if not path:
            continue
        name = os.path.basename(path)
        if re.fullmatch(r"sleep_\d{4}-\d{2}-\d{2}\.jpg", name):
            continue
        abs_path = os.path.abspath(path)
        try:
            is_attachment_file = os.path.commonpath([attachments_root, abs_path]) == attachments_root
        except ValueError:
            is_attachment_file = False
        if not is_attachment_file:
            continue
        if path != image_path and not name.startswith(f"{request_id}_"):
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info("🧹 已清理临时上传图片: %s", name)
        except OSError as exc:
            logger.warning("清理临时上传图片失败: %s", exc)


def _cleanup_stale_temp_upload_images(max_age_seconds=3600):
    attachments_root = os.path.abspath(ATTACHMENTS_DIR)
    if not os.path.isdir(ATTACHMENTS_DIR):
        return

    cutoff = time.time() - max_age_seconds
    temp_name_pattern = re.compile(r"^[0-9a-f]{32}_.+\.(?:jpg|jpeg|png|webp)$", re.IGNORECASE)
    for name in os.listdir(ATTACHMENTS_DIR):
        if re.fullmatch(r"sleep_\d{4}-\d{2}-\d{2}\.jpg", name):
            continue
        if not temp_name_pattern.fullmatch(name):
            continue

        path = os.path.join(ATTACHMENTS_DIR, name)
        abs_path = os.path.abspath(path)
        try:
            if os.path.commonpath([attachments_root, abs_path]) != attachments_root:
                continue
            if os.path.getmtime(abs_path) > cutoff:
                continue
            os.remove(abs_path)
            logger.info("🧹 已清理过期临时上传图片: %s", name)
        except OSError as exc:
            logger.warning("清理过期临时上传图片失败: %s error=%s", name, exc)


def _archive_sleep_image(image_path, sleep_date, request_id, user_id):
    """
    将本次上传图片归档到识别出的睡眠日期；已有日期备份时只复用，不覆盖。
    """
    normalized_date = _normalize_sleep_date(sleep_date)
    if not image_path or not os.path.exists(image_path):
        return image_path
    if not normalized_date:
        logger.warning("跳过睡眠图片日期归档：缺少有效识别日期 request_id=%s user_id=%s", request_id, user_id)
        return image_path

    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    final_name = f"sleep_{normalized_date}.jpg"
    final_path = os.path.join(ATTACHMENTS_DIR, final_name)
    if os.path.abspath(image_path) == os.path.abspath(final_path):
        _set_job_image_path(request_id, final_path)
        return final_path

    try:
        if os.path.exists(final_path):
            logger.info("💾 同日睡眠图片已存在，跳过覆盖归档: %s", final_name)
            try:
                os.remove(image_path)
            except OSError as exc:
                logger.warning("清理重复上传临时图片失败: %s", exc)
            _set_job_image_path(request_id, final_path)
            return final_path
        os.rename(image_path, final_path)
        logger.info("💾 服务端图片已按识别日期归档: %s", final_name)
        _set_job_image_path(request_id, final_path)
        return final_path
    except Exception as exc:
        logger.error(f"服务端归档睡眠图片失败: {exc}")
        return image_path


def _mark_upload_validated(request_id, date, sleep_data, image_path):
    if not isinstance(sleep_data, str):
        sleep_data = json.dumps(sleep_data or {}, ensure_ascii=False)
    try:
        conn = store._connect()
        conn.execute(
            """
            UPDATE server_sleep_jobs
            SET status='uploaded', date=?, image_path=?, result_json=?, analysis_report='', error=NULL, updated_at=?
            WHERE request_id=?
            """,
            (date, image_path, sleep_data, _now_str(), request_id),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"更新上传校验状态失败: {exc}")


def _run_upload_validation(request_id, image_path, user_id):
    try:
        job = store.get_job(request_id, user_id=user_id)
        date_str = job.get("date") if job else None
        logger.info(
            "[sleep-report] upload validation start request_id=%s user_id=%s date=%s image_path=%s",
            request_id,
            user_id,
            date_str,
            image_path,
        )
        store.mark_running(request_id)
        _push_progress(request_id, {"status": "running", "msg": "正在上传并解析睡眠截图..."})
        analyzer = SleepAnalyzer(
            ai_cfg=build_ai_cfg_for_user(user_id),
            image_path=image_path,
            date_str=date_str,
            include_time_analysis=False,
            db=time_logger_db,
            progress_callback=lambda msg: _push_progress(request_id, {"status": "progress", "msg": msg}),
            force_refresh=True,
            user_id=user_id,
        )
        _push_progress(request_id, {"status": "progress", "msg": "正在 OCR 提取睡眠数据和截图日期..."})
        sleep_data = analyzer._extract_sleep_data()
        is_valid, validation_reason = SleepAnalyzer.validate_data(sleep_data)
        logger.info(
            "[sleep-report] upload validation extracted request_id=%s valid=%s reason=%s keys=%s",
            request_id,
            is_valid,
            validation_reason,
            sorted((sleep_data or {}).keys()),
        )
        if not is_valid:
            raise ValueError(validation_reason)
        _push_progress(request_id, {"status": "progress", "msg": "睡眠数据已提取，正在校验日期..."})
        result_date = _normalize_sleep_date(sleep_data.get("sleep_date")) or _normalize_sleep_date(sleep_data.get("date"))
        if not result_date:
            raise ValueError("未识别到有效的睡眠日期，上传校验中止。")
        if date_str and result_date != date_str:
            raise ValueError(f"日期不匹配！截图日期是 {result_date}，而当前处理日期是 {date_str}。请确认是否选错了图。")
        sleep_data["date"] = result_date
        sleep_data["sleep_date"] = result_date
        sleep_data["source"] = SleepDataSource.SCREENSHOT_OCR.value
        sleep_data["sync_status"] = sleep_data.get("sync_status") or "success"
        image_path = _archive_sleep_image(image_path, result_date, request_id, user_id)
        _mark_upload_validated(request_id, result_date, sleep_data, image_path)
        logger.info(
            "[sleep-report] upload validation done request_id=%s user_id=%s date=%s image_path=%s",
            request_id,
            user_id,
            result_date,
            image_path,
        )
        _push_progress(request_id, {"status": "uploaded", "result": sleep_data, "msg": f"{result_date} 图片已上传"})
    except Exception as exc:
        logger.error("上传截图日期校验失败: request_id=%s error=%s", request_id, exc, exc_info=True)
        logger.error("[sleep-report] upload validation error request_id=%s user_id=%s date=%s error=%s", request_id, user_id, date_str if 'date_str' in locals() else None, exc, exc_info=True)
        store.mark_error(request_id, str(exc))
        _push_progress(request_id, {"status": "error", "msg": str(exc)})
    finally:
        _cleanup_temp_upload_image(request_id, image_path)
        _cleanup_queue(request_id)


def _run_analysis(request_id, image_path, user_id, full=True, force_refresh=False):
    """
    后台分析任务入口。在独立线程中运行，不阻塞事件循环。
    """
    try:
        # 获取现有的 job 详情以备份服务端的日记内容，防止分析后覆盖丢失
        job = store.get_job(request_id, user_id=user_id)
        date_str = job.get("date") if job else None
        image_hash = job.get("image_hash") if job else None
        logger.info(
            "[sleep-report] analysis job start request_id=%s user_id=%s date=%s full=%s force=%s image_path=%s",
            request_id,
            user_id,
            date_str,
            full,
            force_refresh,
            image_path,
        )

        existing_data = job.get("sleep_data") if job else {}
        morning_diary = existing_data.get("morning_diary") or existing_data.get("sleep_reflection")
        evening_diary = existing_data.get("evening_diary")

        store.mark_running(request_id)
        _push_progress(request_id, {"status": "running", "msg": f"开始服务端{'完整' if full else '快速'}睡眠分析..."})

        def progress(msg):
            _push_progress(request_id, {"status": "progress", "msg": msg})

        # 组装初始 of sleep_data，把备份的日记注入进去作为分析底本
        init_sleep_data = {}
        if morning_diary:
            init_sleep_data["morning_diary"] = morning_diary
        if evening_diary:
            init_sleep_data["evening_diary"] = evening_diary
        if existing_data and SleepAnalyzer.validate_data(existing_data)[0]:
            init_sleep_data.update(existing_data)
            progress("检测到上传阶段已提取完整睡眠数据，跳过重复 OCR...")
            logger.info("[sleep-report] analysis reuse upload_sleep_data request_id=%s date=%s", request_id, date_str)
        if date_str:
            structured_data = store.get_huawei_sleep_data(user_id, date_str)
            if structured_data and structured_data.get("source") != SleepDataSource.SCREENSHOT_OCR.value:
                valid, reason = SleepAnalyzer.validate_data(structured_data)
                if valid:
                    init_sleep_data.update(structured_data)
                    progress("检测到结构化华为睡眠数据，将以数据库睡眠数据重新生成报告...")
                    logger.info("♻️ 结构化睡眠数据命中，跳过 OCR: user_id=%s date=%s force=%s", user_id, date_str, force_refresh)
                    logger.info("[sleep-report] analysis reuse structured_data request_id=%s date=%s source=%s", request_id, date_str, structured_data.get("source"))
                elif image_path and os.path.exists(image_path):
                    progress(f"结构化睡眠数据校验失败，回退截图 OCR: {reason}")
                    logger.warning("[sleep-report] analysis structured invalid fallback_ocr request_id=%s date=%s reason=%s", request_id, date_str, reason)

        def reuse_by_sleep_date(target_date, extracted_sleep_data):
            reusable_job = store.get_job_by_date(target_date, user_id=user_id)
            if reusable_job and reusable_job.get("request_id") != request_id and reusable_job.get("status") == "done" and (not full or _can_reuse_sleep_report(reusable_job, full=True, force=False)):
                logger.info(
                    "♻️ OCR 日期命中已完成结果，跳过重复报告生成: user_id=%s date=%s source_request_id=%s request_id=%s",
                    user_id,
                    target_date,
                    reusable_job.get("request_id"),
                    request_id,
                )
                logger.info(
                    "[sleep-report] analysis reuse completed_report request_id=%s source_request_id=%s date=%s",
                    request_id,
                    reusable_job.get("request_id"),
                    target_date,
                )
                return {
                    "date": target_date,
                    "sleep_data": reusable_job.get("sleep_data") or extracted_sleep_data,
                    "analysis_report": reusable_job.get("analysis_report") or "",
                    "report_path": "",
                }
            return None

        report_provider_config = {
            "ai_model_config": build_ai_cfg_for_user(user_id),
            "atimelogger": _load_user_provider_config(user_id, "atimelogger_config"),
        }
        analyzer = SleepAnalyzer(
            ai_cfg=report_provider_config["ai_model_config"],
            image_path=image_path,
            sleep_data=init_sleep_data if init_sleep_data else None,
            date_str=date_str,
            include_time_analysis=full,
            db=time_logger_db,
            progress_callback=progress,
            force_refresh=force_refresh,
            pre_report_callback=reuse_by_sleep_date,
            report_provider_config=report_provider_config,
            user_id=user_id,
        )

        result = analyzer.analyze()
        logger.info(
            "[sleep-report] analysis analyzer result request_id=%s status=%s date=%s report_path=%s error=%s",
            request_id,
            result.status,
            result.date,
            result.report_path,
            result.error,
        )
        if result.status == "done":
            progress("OCR 与睡眠指标校验完成，正在整理报告数据...")
            sleep_data = result.sleep_data or {}
            result_date = (
                _normalize_sleep_date(result.date)
                or _normalize_sleep_date(sleep_data.get("date"))
                or _normalize_sleep_date(sleep_data.get("sleep_date"))
            )
            if result_date and not force_refresh:
                reusable_job = store.get_job_by_date(result_date, user_id=user_id)
                if reusable_job and reusable_job.get("request_id") != request_id and reusable_job.get("status") == "done" and (not full or _can_reuse_sleep_report(reusable_job, full=True, force=False)):
                    archived_path = _archive_sleep_image(image_path, result_date, request_id, user_id)
                    store.mark_reused_from_job(request_id, reusable_job, image_path=archived_path, image_hash=image_hash)
                    logger.info("[sleep-report] analysis mark reused request_id=%s source_request_id=%s date=%s", request_id, reusable_job.get("request_id"), result_date)
                    _push_progress(request_id, {"status": "done", "result": reusable_job.get("sleep_data") or {}, "reused": True, "cache_reason": "sleep_date"})
                    return
            if not sleep_data.get("source"):
                sleep_data["source"] = SleepDataSource.SCREENSHOT_OCR.value
            if not sleep_data.get("sync_status"):
                sleep_data["sync_status"] = "success"
            # 双重回填保护，防止 Null 值覆写
            if morning_diary and not sleep_data.get("morning_diary"):
                sleep_data["morning_diary"] = morning_diary
            if evening_diary and not sleep_data.get("evening_diary"):
                sleep_data["evening_diary"] = evening_diary

            # 报告时效只接受本次睡眠报告在服务端成功生成的完成时刻，绝不读取设备同步时间。
            if result.analysis_report or result.report_path:
                sleep_data["report_completed_at"] = _beijing_now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                sleep_data.pop("report_completed_at", None)
            sleep_data["sleep_date"] = result_date
            report_content = result.analysis_report or ""
            if report_content.strip():
                sleep_data["analysis_report"] = report_content
                sleep_data["report_status"] = 2 if full and result.report_path else max(1, int(sleep_data.get("report_status") or 0))
            elif sleep_data.get("full_report_state") == "insufficient_time_records":
                sleep_data["report_status"] = min(1, int(sleep_data.get("report_status") or 0))
            settlement = store.save_huawei_sleep_data(
                user_id, result_date, sleep_data, settle_score=True,
                report_completed_at=sleep_data.get("report_completed_at"),
            )
            sleep_data["score_settlement"] = settlement

            if result.report_path:
                skill_dir = os.path.join(current_dir, "skills", "time-management")
                if skill_dir not in sys.path:
                    sys.path.insert(0, skill_dir)
                from generate_full_report import apply_sleep_settlement_to_report
                report_content = apply_sleep_settlement_to_report(result.report_path, settlement)
            if result.analysis_report:
                sleep_data["analysis_report"] = report_content
            if result.report_path:
                progress("报告文件已生成，正在上传备份...")
                logger.info("[sleep-report] analysis s3 upload start request_id=%s date=%s report_path=%s", request_id, result_date, result.report_path)
                s3_backup.upload_report_with_config(
                    _s3_config_for_user({"id": user_id, "username": _username_for_user_id(user_id)}),
                    result.report_path,
                    username=_username_for_user_id(user_id),
                    user_id=user_id,
                )
                logger.info("[sleep-report] analysis s3 upload finish request_id=%s date=%s", request_id, result_date)

            image_path = _archive_sleep_image(image_path, result_date, request_id, user_id)

            progress("正在保存报告和睡眠数据...")
            if result.report_path and report_content.strip():
                sleep_data["analysis_report"] = report_content
                sleep_data["analysis_html"] = markdown.markdown(
                    report_content, extensions=["fenced_code", "tables"],
                )
            store.mark_done(request_id, result_date, sleep_data, report_content)
            try:
                sync_hub._notify_clients(["huawei_sleep_data", "sleep_score_settlements", "reward_ledger", "user_wallets"], user_id)
            except Exception:
                logger.exception("[sleep-report] sync notification failed request_id=%s user_id=%s", request_id, user_id)
            logger.info(
                "[sleep-report] analysis mark done request_id=%s user_id=%s date=%s report_status=%s full_report_state=%s tracked_duration_seconds=%s fall_asleep_min=%s wake_up_min=%s",
                request_id,
                user_id,
                result_date,
                sleep_data.get("report_status"),
                sleep_data.get("full_report_state"),
                sleep_data.get("tracked_duration_seconds"),
                sleep_data.get("fall_asleep_min"),
                sleep_data.get("wake_up_min"),
            )
            _push_progress(request_id, {"status": "done", "result": sleep_data, "msg": "分析完成，报告已更新"})
        else:
            if isinstance(result.error, str) and "aTimeLogger 授权已失效" in result.error:
                _mark_atimelogger_auth_required(user_id)
            store.mark_error(request_id, result.error)
            logger.error("[sleep-report] analysis mark error request_id=%s user_id=%s date=%s error=%s", request_id, user_id, date_str, result.error)
            _push_progress(request_id, {"status": "error", "msg": result.error})


    except Exception as exc:
        # 顶层保护：确保任何未预期异常都能正确更新 job 状态
        # 否则 job 会永远停留在 running，客户端 SSE 流永远不会收到结束信号
        logger.exception(f"_run_analysis 未预期异常: request_id={request_id}, error={exc}")
        logger.exception("[sleep-report] analysis unexpected error request_id=%s user_id=%s error=%s", request_id, user_id, exc)
        try:
            store.mark_error(request_id, f"内部错误: {exc}")
            _push_progress(request_id, {"status": "error", "msg": f"内部错误: {exc}"})
        except Exception:
            pass  # 如果连错误标记都失败了，至少不要让异常继续传播

    finally:
        # 分析结束后延迟清理队列，防止长期运行导致内存泄漏
        _cleanup_temp_upload_image(request_id, image_path)
        _cleanup_queue(request_id)


@app.post("/auth/register")
async def register(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if store.create_user(username, password):
        user_id = store.verify_user(username, password)
        if user_id:
            _ensure_sample_data_for_user(user_id)
            _bootstrap_private_config_for_user(user_id)
        logger.info(f"🆕 New user registered: {username}")
        return {"status": "ok", "msg": "Registration successful"}
    logger.warning(f"⚠️ Registration failed (user exists): {username}")
    raise HTTPException(status_code=400, detail="Username already exists")


@app.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    _assert_login_allowed(request, username)
    user_id = store.verify_user(username, password)
    if user_id:
        _ensure_sample_data_for_user(user_id)
        _bootstrap_private_config_for_user(user_id)
        token = store.create_session(user_id)
        store.cleanup_expired_sessions()
        _record_login_result(request, username, True)
        logger.info(f"✅ User logged in: {username} (ID: {user_id})")
        return {"status": "ok", "token": token, "username": username}
    _record_login_result(request, username, False)
    logger.warning(f"❌ Login failed for user: {username}")
    raise HTTPException(status_code=401, detail="Invalid username or password")


@app.get("/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"status": "ok", "user": user}


@app.post("/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme), user: dict = Depends(get_current_user)):
    store.revoke_session(credentials.credentials)
    return {"status": "ok"}


@app.post("/checklist/ticktick-reset/preview")
async def ticktick_reset_preview(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    start_date = resolve_statistics_start_date(body.get("start_date")).date
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=preview_start start_date=%s", request_id, user["id"], start_date)
    result = preview_ticktick_reset(store.db_path, int(user["id"]), start_date)
    logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=preview_finish counts=%s", request_id, user["id"], result["counts"])
    return result


REWARD_REBUILD_CONFIRMATION = "REBUILD REWARD LEDGER"


@app.get("/api/rewards/rebuild/capabilities")
def reward_rebuild_capabilities(user: dict = Depends(get_current_user)):
    return {"version": 2, "supported": True, "confirmation_phrase": REWARD_REBUILD_CONFIRMATION}


@app.post("/api/rewards/rebuild/preview")
async def reward_rebuild_preview(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    trace_id = normalize_trace_id(getattr(request.state, "request_id", None) or request.headers.get("x-request-id"))
    if not isinstance(body, dict) or body.get("contract_version") != 2:
        raise HTTPException(status_code=426, detail="reward_rebuild_v2_required")
    try:
        return reward_rebuild_service.preview(int(user["id"]), body.get("statistics_start_date"), trace_id)
    except (RewardRebuildError, ValueError) as exc:
        log_event(logger, trace_id=trace_id, job_id=None, user_id=int(user["id"]),
                  stage="preview", event="finish", outcome="failure",
                  details={"error_type": type(exc).__name__, "code": str(exc)}, level=logging.WARNING)
        raise HTTPException(status_code=422, detail=str(exc), headers={"X-Trace-ID": trace_id}) from exc


async def _run_reward_rebuild(user_id: int, job_id: str, start_date: str):
    pull = None
    job = reward_rebuild_service.get_job(user_id, job_id)
    trace_id = job["trace_id"]
    stage = "ticktick_reset"
    try:
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage="job_finish", event="start", outcome="running")
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage=stage, event="start", outcome="running")
        reset_preview = preview_ticktick_reset(store.db_path, user_id, start_date)
        await asyncio.to_thread(
            reset_ticktick_data, store.db_path, user_id, start_date,
            reset_preview["summary_hash"], f"RESET TICKTICK USER {user_id}", trace_id, True,
        )
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage=stage, event="finish", outcome="success", details=reset_preview.get("counts") or {})
        stage = "provider_pull"
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage=stage, event="start", outcome="running")
        pull = await sync_hub.force_pull_ticktick(user_id, request_id=trace_id, job_id=job_id)
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage=stage, event="finish", outcome="success" if pull.get("ok") else "failure",
                  details={"merged_count": pull.get("merged_count"), "errors": pull.get("errors")})
        stage = "candidate_build"
        report = await asyncio.to_thread(
            reward_rebuild_service.build_and_publish, user_id, job_id, pull,
        )
        sync_hub._notify_clients(
            ["tasks", "habits", "habit_checkins", "reward_ledger", "user_wallets", "backpack_events", "reward_fragments", "exercise_item_scores", "exercise_settlements"],
            user_id,
        )
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage="job_finish", event="finish", outcome="success",
                  details={"epoch": report.get("epoch"), "ledger_rows": report.get("ledger_rows"), "balance": report.get("balance")})
    except Exception as exc:
        failed_stage = stage if stage in {"ticktick_reset", "provider_pull"} else None
        report = await asyncio.to_thread(
            reward_rebuild_service.fail_and_restore, user_id, job_id, exc, pull, failed_stage,
        )
        sync_hub._notify_clients(["reward_ledger", "user_wallets", "backpack_events", "reward_fragments"], user_id)
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage="job_finish", event="finish", outcome="failure",
                  details={"code": report.get("code"), "failed_stage": report.get("failed_stage"),
                           "recovery": report.get("recovery")}, level=logging.ERROR)
        logger.exception("[RewardRebuild] failed trace_id=%s user_id=%s job_id=%s", trace_id, user_id, job_id)
    finally:
        reward_rebuild_tasks.pop(job_id, None)


@app.post("/api/rewards/rebuild/start")
async def reward_rebuild_start(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    trace_id = normalize_trace_id(getattr(request.state, "request_id", None) or request.headers.get("x-request-id"))
    if not isinstance(body, dict) or body.get("contract_version") != 2:
        raise HTTPException(status_code=426, detail="reward_rebuild_v2_required")
    if body.get("confirmation_phrase") != REWARD_REBUILD_CONFIRMATION:
        raise HTTPException(status_code=409, detail="confirmation_invalid")
    try:
        job, created = reward_rebuild_service.start(
            int(user["id"]), body.get("statistics_start_date"), str(body.get("preview_hash") or ""),
            trace_id,
        )
    except (RewardRebuildError, ValueError) as exc:
        log_event(logger, trace_id=trace_id, job_id=None, user_id=int(user["id"]),
                  stage="job_create", event="finish", outcome="failure",
                  details={"error_type": type(exc).__name__, "code": str(exc)}, level=logging.WARNING)
        raise HTTPException(status_code=409, detail=str(exc), headers={"X-Trace-ID": trace_id}) from exc
    if created:
        reward_rebuild_tasks[job["id"]] = asyncio.create_task(
            _run_reward_rebuild(int(user["id"]), job["id"], job["statistics_start_date"]),
        )
    return {"created": created, "job": job}


@app.get("/api/rewards/rebuild/jobs/{job_id}")
def reward_rebuild_job(job_id: str, user: dict = Depends(get_current_user)):
    try:
        return reward_rebuild_service.get_job(int(user["id"]), job_id)
    except RewardRebuildError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _ticktick_task_settings(user_id: int):
    conn = store._connect()
    try:
        return load_ticktick_settings(conn, user_id)
    finally:
        conn.close()


def _publish_confirmed_ticktick_task(user_id: int, operation: str, command: dict, task: dict | None = None) -> None:
    """Publish only a provider-confirmed task change to the existing versioned sync stream."""
    if operation == "delete":
        sync_hub._delete_provider_task(user_id, str(command["result_task_id"]))
    elif task:
        payload = dict(task)
        payload.update({
            "id": task["id"], "title": task.get("title", ""), "priority": task.get("priority", 0),
            "status": task.get("status", 0), "due_date": task.get("dueDate", ""),
            "tags": task.get("tags", []), "project_id": task.get("projectId") or command.get("project_id", ""),
            "project_name": "", "etag": task.get("etag", ""), "modifiedTime": task.get("modifiedTime", ""),
        })
        time_logger_db.upsert_task(user_id, payload)
    sync_hub._notify_clients(["tasks"], user_id)


@app.post("/api/ticktick/tasks/commands")
async def ticktick_task_command(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    user_id = int(user["id"])
    request_id = str(body.get("request_id") or "").strip()
    operation = str(body.get("operation") or "").strip()
    if not request_id or operation not in {"create", "update", "delete", "reconcile"}:
        return {"request_id": request_id, "status": "failed", "error_code": "validation_error"}
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else ({"title": body.get("title")} if "title" in body else {})
    expected = body.get("expected") if isinstance(body.get("expected"), dict) else {}
    recommendation = None
    recommendation_id = str(body.get("flash_recommendation_id") or "").strip()
    if recommendation_id:
        if operation != "create": return {"request_id": request_id, "status": "failed", "error_code": "validation_error"}
        try:
            recommendation = flash_card_service.get_recommendation(user_id, recommendation_id)
        except FlashCardError as exc:
            return {"request_id": request_id, "status": "failed", "error_code": exc.code}
        if recommendation["status"] == "added": return {"request_id": request_id, "status": "confirmed", "result_task_id": recommendation.get("local_task_id") or recommendation.get("provider_task_id")}
        if recommendation["status"] != "pending": return {"request_id": request_id, "status": "failed", "error_code": "flash_recommendation_not_pending"}
        body["title"] = recommendation["title"]
        recommendation = flash_card_service.confirm_recommendation(user_id, recommendation_id)
        sync_hub._notify_clients(["flash_task_recommendations", "tasks"], user_id)
        return {"request_id": request_id, "status": "confirmed", "result_task_id": recommendation["local_task_id"], "project_id": "local"}
    if operation == "create" and not str(body.get("title") or "").strip():
        return {"request_id": request_id, "status": "failed", "error_code": "validation_error"}
    if operation == "update" and not patch:
        return {"request_id": request_id, "status": "failed", "error_code": "validation_error"}
    if operation in {"update", "delete"} and (not str(body.get("task_id") or "").strip() or not str(body.get("project_id") or "").strip()):
        if not str(body.get("task_id") or "").strip():
            return {"request_id": request_id, "status": "failed", "error_code": "validation_error"}
        conn = store._connect()
        try:
            row = conn.execute("SELECT raw_json FROM server_tasks WHERE user_id=? AND id=?", (int(user["id"]), body["task_id"])).fetchone()
        finally:
            conn.close()
        try:
            snapshot = json.loads(row[0] if row else "{}")
            body["project_id"] = snapshot.get("project_id") or snapshot.get("projectId") or ""
        except (TypeError, ValueError):
            body["project_id"] = ""
        if not body["project_id"]:
            return {"request_id": request_id, "status": "failed", "error_code": "provider_task_not_found"}
    settings = _ticktick_task_settings(user_id)
    if not settings.enabled:
        return {"request_id": request_id, "status": "failed", "error_code": "provider_not_configured"}
    async with TickTickClient(settings.access_token, settings.host, settings.verify_tls, settings.timeout_seconds, request_id=request_id) as client:
        if operation == "create":
            result = await ticktick_task_mutation_service.create(user_id, request_id, body["title"], client, body.get("due_date"), body.get("tags"))
        elif operation == "update":
            result = await ticktick_task_mutation_service.update(user_id, request_id, body["project_id"], body["task_id"], patch, expected, client)
        elif operation == "reconcile":
            result = await ticktick_task_mutation_service.reconcile_create(user_id, request_id, client)
        else:
            result = await ticktick_task_mutation_service.delete(user_id, request_id, body["project_id"], body["task_id"], client)
        if result.get("status") == "confirmed":
            provider_task = None if operation == "delete" else await client.get_task(result["project_id"], result["result_task_id"])
            if operation == "create" and not provider_task:
                return {**result, "status": "failed", "error_code": "provider_task_not_found"}
            _publish_confirmed_ticktick_task(user_id, operation, result, provider_task)
            learning_task_id = str(body.get("learning_task_id") or "").strip()
            if operation == "create" and learning_task_id:
                store.link_learning_checklist_task(user_id, learning_task_id, str(result["result_task_id"]))
            if recommendation:
                flash_card_service.mark_recommendation_added(user_id, recommendation_id, str(result["result_task_id"]))
                sync_hub._notify_clients(["flash_task_recommendations"], user_id)
        return result


@app.post("/api/learning/checklist-links/{learning_task_id}/cancel")
async def cancel_learning_checklist_link(learning_task_id: str, user: dict = Depends(get_current_user)):
    """Cancel an unfinished TickTick task before reversing its linked learning unit."""
    user_id = int(user["id"])
    try:
        link = store.get_learning_checklist_cancellation(user_id, learning_task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not link:
        return {"status": "not_linked"}
    if link["provider_missing"]:
        store.cancel_learning_checklist_task(user_id, learning_task_id, link["checklist_task_id"])
        sync_hub._notify_clients(["learning_tasks", "learning_krs", "learning_objectives"], user_id)
        return {"status": "confirmed", "result_task_id": link["checklist_task_id"]}
    settings = _ticktick_task_settings(user_id)
    if not settings.enabled:
        return {"status": "failed", "error_code": "provider_not_configured"}
    request_id = f"learning-cancel:{learning_task_id}:{link['checklist_task_id']}"
    async with TickTickClient(settings.access_token, settings.host, settings.verify_tls, settings.timeout_seconds, request_id=request_id) as client:
        result = await ticktick_task_mutation_service.delete(
            user_id, request_id, link["project_id"], link["checklist_task_id"], client,
        )
    if result.get("status") == "confirmed":
        _publish_confirmed_ticktick_task(user_id, "delete", result)
        store.cancel_learning_checklist_task(user_id, learning_task_id, link["checklist_task_id"])
        sync_hub._notify_clients(["learning_tasks", "learning_krs", "learning_objectives"], user_id)
    return result


@app.get("/api/ticktick/tasks/operations/{request_id}")
def get_ticktick_task_operation(request_id: str, user: dict = Depends(get_current_user)):
    operation = ticktick_task_operation_store.get(int(user["id"]), request_id)
    if not operation:
        raise HTTPException(status_code=404, detail="任务操作不存在")
    return operation


def _management_plan_error(exc: ManagementPlanError) -> HTTPException:
    detail = {"error_code": exc.code, "message": str(exc)}
    if exc.details is not None:
        detail["details"] = exc.details
    return HTTPException(status_code=exc.status, detail=detail)


@app.post("/api/management-plans/drafts")
async def create_management_plan_draft(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        generated = body.get("payload") if isinstance(body.get("payload"), dict) else None
        runner = None if generated is not None else _management_plan_model_runner(int(user["id"]))
        return management_plan_service.create_draft(
            int(user["id"]), body.get("request"), generated_payload=generated, model_runner=runner,
            requested_intent=body.get("intent"),
        )
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.get("/api/management-plans/drafts/{draft_id}")
def get_management_plan_draft(draft_id: str, user: dict = Depends(get_current_user)):
    try:
        return management_plan_service.get_draft(int(user["id"]), draft_id)
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.post("/api/management-plans/drafts/{draft_id}/preview")
async def preview_management_plan_draft(draft_id: str, request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        return management_plan_service.preview(int(user["id"]), draft_id, body.get("payload"))
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.post("/api/management-plans/drafts/{draft_id}/apply")
async def apply_management_plan_draft(draft_id: str, request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        user_id = int(user["id"])
        plan_digest = str(body.get("plan_digest") or "")
        idempotency_key = str(body.get("idempotency_key") or "")
        existing = management_plan_service.application_for_key(user_id, idempotency_key) if idempotency_key else None
        if existing:
            return existing
        external_items = management_plan_service.external_items_for_apply(user_id, draft_id, plan_digest)
        external_results: dict[str, dict] | None = None
        if external_items:
            external_results = {}
            settings = _ticktick_task_settings(user_id)
            if settings.enabled:
                async with TickTickClient(settings.access_token, settings.host, settings.verify_tls, settings.timeout_seconds, request_id=idempotency_key) as client:
                    for item in external_items:
                        command_id = "mgmt-" + hashlib.sha256(
                            f"{user_id}:{idempotency_key}:{item['logical_key']}".encode("utf-8")
                        ).hexdigest()[:48]
                        if item.get("action") == "update":
                            task_id = str(item.get("record_id") or "").strip()
                            project_id = str(item.get("project_id") or "").strip()
                            if not task_id or not project_id:
                                command = {"request_id": command_id, "status": "failed", "error_code": "provider_task_not_found"}
                            else:
                                command = await ticktick_task_mutation_service.update_title(
                                    user_id,
                                    command_id,
                                    project_id,
                                    task_id,
                                    str(item.get("title") or item["logical_key"]),
                                    client,
                                    item.get("expected_title"),
                                )
                        else:
                            command = await ticktick_task_mutation_service.create(
                                user_id, command_id, str(item.get("title") or item["logical_key"]), client
                            )
                        if command.get("status") == "unknown":
                            command = await ticktick_task_mutation_service.reconcile_create(user_id, command_id, client)
                        external_results[item["logical_key"]] = command
            else:
                for item in external_items:
                    external_results[item["logical_key"]] = {
                        "request_id": idempotency_key,
                        "status": "failed",
                        "error_code": "provider_not_configured",
                    }
        result = management_plan_service.apply(user_id, draft_id, plan_digest, idempotency_key, external_results)
        if result.get("status") == "applied":
            sync_hub._notify_clients(["management_plan_revisions", "management_plan_bindings", "management_plan_change_log"], int(user["id"]))
        return result
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.get("/api/management-plans/revisions")
def list_management_plan_revisions(user: dict = Depends(get_current_user)):
    return {"revisions": management_plan_service.list_revisions(int(user["id"]))}


@app.get("/api/management-plans/mindmap")
def get_management_plan_mindmap(user: dict = Depends(get_current_user)):
    try:
        return management_plan_service.mindmap_snapshot(int(user["id"]))
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.post("/api/v1/behavior-events/batch")
async def append_behavior_events(request: Request, user: dict = Depends(get_current_user)):
    events = (await request.json()).get("events", [])
    if not isinstance(events, list) or len(events) > 100:
        raise HTTPException(status_code=400, detail="invalid_behavior_batch")
    try: accepted = _behavior_audit_service().append(int(user["id"]), events)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"accepted": accepted}

@app.get("/api/v1/behavior-events")
def list_behavior_events(date: str, cursor: str = "", limit: int = 50, user: dict = Depends(get_current_user)):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date): raise HTTPException(status_code=400, detail="invalid_behavior_date")
    try: parsed_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc: raise HTTPException(status_code=400, detail="invalid_behavior_date") from exc
    start = f"{date} 00:00:00"; end = (parsed_date + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    before_at, _, before_id = cursor.partition("|")
    query = "SELECT event_id,occurred_at,runtime,page,event_type,action,target_type,target_id,result,error_code,trace_id,metadata_json FROM server_user_behavior_events WHERE user_id=? AND occurred_at>=? AND occurred_at<?"
    params: list[object] = [int(user["id"]), start, end]
    if before_at and before_id: query += " AND (occurred_at<? OR (occurred_at=? AND event_id<?))"; params.extend([before_at, before_at, before_id])
    with store._connect() as conn: rows = [dict(row) for row in conn.execute(query + " ORDER BY occurred_at DESC,event_id DESC LIMIT ?", [*params, min(max(limit, 1), 100)]).fetchall()]
    rows = [{**{key: value for key, value in row.items() if key != "metadata_json"}, **_behavior_audit_service().present(row)} for row in rows]
    next_cursor = f"{rows[-1]['occurred_at']}|{rows[-1]['event_id']}" if len(rows) == min(max(limit, 1), 100) else ""
    return {"events": rows, "next_cursor": next_cursor}


@app.get("/api/management-plans/revisions/{revision_id}/export")
def export_management_plan_revision(revision_id: str, user: dict = Depends(get_current_user)):
    try:
        return management_plan_service.export_revision(int(user["id"]), revision_id)
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.post("/api/management-plans/import/preview")
async def preview_management_plan_import(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        return management_plan_service.import_preview(int(user["id"]), body.get("manifest") or body)
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.post("/api/management-plans/import/apply")
async def apply_management_plan_import(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        result = management_plan_service.publish_manifest(
            int(user["id"]), body.get("manifest") or {},
            reason=str(body.get("reason") or "导入管理方案"),
            revision_kind=str(body.get("revision_kind") or "major"),
            parent_revision_id=body.get("parent_revision_id"),
        )
        sync_hub._notify_clients(["management_plan_revisions", "management_plan_bindings", "management_plan_change_log"], int(user["id"]))
        return result
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.post("/api/management-plans/revisions/{revision_id}/patch/preview")
async def preview_management_plan_patch(revision_id: str, request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        return management_plan_service.patch_preview(int(user["id"]), revision_id, body.get("patch") or body)
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.get("/api/management-plans/revisions/compare")
def compare_management_plan_revisions(left: str, right: str, user: dict = Depends(get_current_user)):
    try:
        return management_plan_service.compare_revisions(int(user["id"]), left, right)
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.get("/api/v1/management-plan/export")
def export_management_bundle(user: dict = Depends(get_current_user)):
    try:
        return management_plan_service.export_bundle(int(user["id"]))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/management-plan/import/preview")
async def preview_management_bundle(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        incoming_bundle = body.get("bundle") or body
        mode = body.get("mode", "merge")
        return management_plan_service.preview_bundle(int(user["id"]), mode, incoming_bundle)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/v1/management-plan/import/apply")
async def apply_management_bundle(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        incoming_bundle = body.get("bundle") or body
        idempotency_key = body.get("idempotency_key")
        mode = body.get("mode", "merge")
        
        if not idempotency_key:
            raise HTTPException(status_code=422, detail="Missing idempotency_key")
            
        revision_id = management_plan_service.apply_bundle(
            int(user["id"]), idempotency_key, incoming_bundle, mode
        )
        
        # Notify clients
        sync_hub._notify_clients(["management_plan_revisions", "management_plan_bindings", "management_plan_change_log", "categories", "tasks", "habits", "learning_objectives", "goals", "rewards", "exercise_plan_versions"], int(user["id"]))
        
        return {"revision_id": revision_id}
    except HTTPException:
        raise
    except ValueError as exc:
        # Assuming our BundleValidationError maps here
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/learning/plans")
async def apply_learning_plan(request: Request, user: dict = Depends(get_current_user)):
    try:
        return learning_plan_service.command(int(user["id"]), await request.json())
    except ManagementPlanError as exc:
        raise _management_plan_error(exc) from exc


@app.get("/api/timebook/flash-cards")
def list_flash_cards(date: str | None = None, user: dict = Depends(get_current_user)):
    return {"cards": flash_card_service.list(int(user["id"]), date)}


def _sanitized_flash_attempts(exc: Exception) -> list[dict]:
    return [
        {key: str(attempt[key])[:80] for key in ("slot", "stage", "code") if key in attempt}
        for attempt in getattr(exc, "attempts", []) if isinstance(attempt, dict)
    ]


def _flash_insight_log_normalized(insights: dict, feedback_label: str | None = None) -> dict:
    """构造不含模型原始回复的闪念处理审计摘要。"""
    normalized = {key: insights[key] for key in ("polished_text", "todos", "diary") if key in insights}
    normalized["proofreading"] = {
        "code": str(insights.get("_polish_code", "not_evaluated"))[:80],
        "edit_count": int(insights.get("_polish_edit_count", 0)),
    }
    attempts = [
        {key: str(attempt[key])[:80] for key in ("slot", "stage", "code") if key in attempt}
        for attempt in insights.get("attempts", []) if isinstance(attempt, dict)
    ]
    if attempts:
        normalized["attempts"] = attempts
    if feedback_label:
        normalized["feedback_label"] = feedback_label
    return normalized


def _process_synced_flash_card(user_id: int, card_id: str) -> None:
    card, audit_id = flash_card_service.get(user_id, card_id), None
    try:
        audit_id = flash_processing_log_service.start(
            user_id, card_id, card["original_text"], _flash_todo_diary_skill(user_id), _flash_skill_version(user_id)
        )
        insights = _flash_todo_diary_analysis(user_id, card["original_text"])
        flash_card_service.save_insights(user_id, card_id, insights["polished_text"], insights["diary"], insights["todos"])
        flash_processing_log_service.finish(
            user_id, audit_id, raw_output=insights.get("raw_output"),
            normalized=_flash_insight_log_normalized(insights),
        )
    except Exception as exc:
        error_code = exc.code if isinstance(exc, FlashCardError) else "flash_insight_analysis_failed"
        flash_card_service.mark_analysis_failed(user_id, card_id, error_code)
        if audit_id:
            flash_processing_log_service.finish(
                user_id, audit_id, normalized={"attempts": _sanitized_flash_attempts(exc)}, error_code=error_code
            )
    finally:
        sync_hub._notify_clients(["flash_cards", "flash_task_recommendations", "tasks"], user_id)


def _process_feedback_reanalysis(user_id: int, card_id: str, run_id: str, label: str) -> None:
    audit_id = None
    try:
        card = flash_card_service.get(user_id, card_id)
        audit_id = flash_processing_log_service.start(user_id, card_id, card["original_text"], _flash_todo_diary_skill(user_id), f"{_flash_skill_version(user_id)}-feedback")
        insights = _flash_feedback_analysis(user_id, card["original_text"], label)
        flash_card_service.save_feedback_reanalysis(user_id, card_id, run_id, insights["polished_text"], insights["diary"], insights["todos"])
        flash_processing_log_service.finish(user_id, audit_id, raw_output=insights.get("raw_output"), normalized=_flash_insight_log_normalized(insights, label))
    except Exception as exc:
        error_code = exc.code if isinstance(exc, FlashCardError) else "flash_feedback_analysis_failed"
        flash_card_service.mark_feedback_reanalysis_failed(user_id, card_id, run_id, error_code)
        if audit_id:
            flash_processing_log_service.finish(user_id, audit_id, normalized={"feedback_label": label, "attempts": _sanitized_flash_attempts(exc)}, error_code=error_code)
    finally:
        sync_hub._notify_clients(["flash_cards", "flash_task_recommendations"], user_id)
        _try_refresh_flash_skill(user_id)


@app.post("/api/timebook/flash-cards")
async def create_flash_card(request: Request, user: dict = Depends(get_current_user)):
    try:
        return flash_card_service.create(int(user["id"]), await request.json())
    except FlashCardError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@app.post("/api/timebook/flash-cards/record")
async def record_flash_card(request: Request, user: dict = Depends(get_current_user)):
    try:
        user_id = int(user["id"])
        card = flash_card_service.create(user_id, await request.json())
        audit_id = None
        try:
            audit_id = flash_processing_log_service.start(
                user_id, card["id"], card["original_text"], _flash_todo_diary_skill(user_id), _flash_skill_version(user_id)
            )
        except Exception as exc:
            logger.warning("flash_insight step=audit_start_failed user_id=%s error_type=%s", user_id, type(exc).__name__)
        try:
            insights = _flash_todo_diary_analysis(user_id, card["original_text"])
            saved_card = flash_card_service.save_insights(user_id, card["id"], insights["polished_text"], insights["diary"], insights["todos"])
            if audit_id:
                try:
                    flash_processing_log_service.finish(user_id, audit_id, raw_output=insights.get("raw_output"), normalized=_flash_insight_log_normalized(insights))
                except Exception as finish_error:
                    logger.warning("flash_insight step=audit_finish_failed user_id=%s error_type=%s", user_id, type(finish_error).__name__)
            return {
                "card": saved_card,
                "polish_status": "done", "task_analysis_status": "done", "task_recommendations": insights["todos"],
            }
        except FlashCardError as exc:
            card = flash_card_service.mark_analysis_failed(user_id, card["id"], exc.code)
            if audit_id:
                try:
                    flash_processing_log_service.finish(user_id, audit_id, raw_output=getattr(exc, "raw_output", None), normalized={"attempts": _sanitized_flash_attempts(exc)}, error_code=exc.code)
                except Exception as finish_error:
                    logger.warning("flash_insight step=audit_finish_failed user_id=%s error_type=%s", user_id, type(finish_error).__name__)
            return {"card": card, "polish_status": "failed", "message": exc.message, "task_analysis_status": "failed", "task_analysis_message": exc.message, "task_recommendations": []}
    except FlashCardError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@app.post("/api/timebook/flash-cards/{card_id}/classification-feedback")
async def classify_flash_card(card_id: str, request: Request, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    try:
        feedback = flash_card_service.record_classification_feedback(int(user["id"]), card_id, str((await request.json()).get("label") or ""), _flash_skill_version(int(user["id"])))
        background_tasks.add_task(_process_feedback_reanalysis, int(user["id"]), card_id, feedback["run_id"], feedback["label"])
        return {"feedback": feedback}
    except FlashCardError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@app.post("/api/timebook/flash-cards/{card_id}/polish-corrections")
async def correct_flash_polish(card_id: str, request: Request, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    try:
        user_id = int(user["id"])
        version = _flash_skill_version(user_id)
        card = flash_card_service.correct_polish(user_id, card_id, await request.json(), version)
        sync_hub._notify_clients(["flash_cards"], user_id)
        background_tasks.add_task(_try_refresh_flash_skill, user_id)
        return {"card": card}
    except FlashCardError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@app.get("/api/timebook/flash-skill/history")
def list_flash_skill_history(cursor: str | None = None, limit: int = 20, user: dict = Depends(get_current_user)):
    return flash_skill_feedback_service.history(int(user["id"]), cursor, limit)


@app.put("/api/timebook/flash-cards/{card_id}")
async def update_flash_card(card_id: str, request: Request, user: dict = Depends(get_current_user)):
    try:
        return flash_card_service.update(int(user["id"]), card_id, await request.json())
    except FlashCardError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@app.delete("/api/timebook/flash-cards/{card_id}")
def delete_flash_card(card_id: str, user: dict = Depends(get_current_user)):
    try:
        user_id = int(user["id"])
        flash_card_service.delete(user_id, card_id)
        flash_processing_log_service.delete_for_card(user_id, card_id)
        return {"status": "ok"}
    except FlashCardError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@app.get("/api/timebook/flash-processing-logs")
def list_flash_processing_logs(flash_card_id: str | None = None, user: dict = Depends(get_current_user)):
    return {"logs": flash_processing_log_service.list(int(user["id"]), flash_card_id)}


@app.post("/api/timebook/flash-recommendations/{recommendation_id}/ignore")
def ignore_flash_recommendation(recommendation_id: str, user: dict = Depends(get_current_user)):
    try:
        recommendation = flash_card_service.ignore_recommendation(int(user["id"]), recommendation_id)
        sync_hub._notify_clients(["flash_task_recommendations"], int(user["id"]))
        return {"recommendation": recommendation}
    except FlashCardError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@app.post("/api/timebook/flash-cards/{card_id}/polish")
def polish_flash_card(card_id: str, user: dict = Depends(get_current_user)):
    try:
        return flash_card_service.polish(int(user["id"]), card_id, _flash_card_polish_runner(int(user["id"])))
    except FlashCardError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@app.post("/checklist/ticktick-reset/confirm")
async def ticktick_reset_confirm(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json(); start_date = resolve_statistics_start_date(body.get("start_date")).date
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    try:
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=confirm_start start_date=%s", request_id, user["id"], start_date)
        result = reset_ticktick_data(store.db_path, int(user["id"]), start_date, str(body.get("summary_hash") or ""), str(body.get("confirmation_phrase") or ""), request_id=request_id)
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=provider_pull_start", request_id, user["id"])
        result["pull"] = await sync_hub.force_pull_ticktick(int(user["id"]), request_id=request_id)
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=provider_pull_finish ok=%s merged=%s errors=%s", request_id, user["id"], result["pull"].get("ok"), result["pull"].get("merged_count"), result["pull"].get("errors"))
        return result
    except ValueError:
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=confirm_rejected", request_id, user["id"])
        raise HTTPException(status_code=409, detail="确认摘要或确认短语无效")


@app.get("/admin/account-contamination/{user_id}/preview")
def contamination_preview(user_id: int, user: dict = Depends(get_current_user)):
    require_service_manager(user)
    try:
        return preview_contamination(store.db_path, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/admin/account-contamination/{user_id}/recover")
async def contamination_recover(user_id: int, request: Request, user: dict = Depends(get_current_user)):
    require_service_manager(user)
    body = await request.json()
    try:
        return recover_contamination(store.db_path, int(user["id"]), user_id, str(body.get("summary_hash") or ""), str(body.get("confirmation_phrase") or ""))
    except ValueError:
        raise HTTPException(status_code=409, detail="确认摘要或确认短语无效")


@app.get("/ping")
def ping():
    return {
        "status": "ok",
        "time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
        "build_revision": BUILD_REVISION,
        "capabilities": {
            "atimelogger_final_backup": {
                "mode": "final_only",
                "version": ATIMELOGGER_FINAL_BACKUP_VERSION,
            },
            "checklist_ticktick_reset": {
                "version": 1,
            },
            "reward_ledger_rebuild": {
                "version": 2,
            },
        },
    }


@app.get("/admin/s3-backup/config")
@app.get("/admin/webdav-backup/config")
def get_s3_backup_config(user: dict = Depends(get_current_user)):
    require_service_manager(user)
    config = _service_manager_s3_config()
    public = config.public()
    return public


@app.put("/admin/s3-backup/config")
@app.put("/admin/webdav-backup/config")
async def put_s3_backup_config(request: Request, user: dict = Depends(get_current_user)):
    require_service_manager(user)
    raise HTTPException(status_code=409, detail="请在 /config 页面保存 S3 配置")


@app.post("/admin/s3-backup/test")
@app.post("/admin/webdav-backup/test")
async def test_s3_backup(request: Request, user: dict = Depends(get_current_user)):
    require_service_manager(user)
    values = await request.json()
    target_name = values.get("target", "reports")
    saved = _service_manager_s3_config()
    candidate = S3BackupConfig(**{
        **saved.__dict__,
        **{key: value for key, value in values.items() if key in saved.__dict__ and not (key == "secret_key" and value == "")},
    })
    try:
        if target_name != "reports":
            raise HTTPException(status_code=400, detail="仅支持用户报告上传路径测试")
        remote_prefix = await asyncio.to_thread(
            S3Client(candidate.reports_target()).test,
            candidate.account_reports_prefix(user.get("username"), user.get("id")),
        )
        return {"status": "ok", "target": target_name, "remote_prefix": remote_prefix}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"S3 connection failed: {str(exc)[:200]}") from exc


def _configured(*values: str | None) -> bool:
    return all(bool(str(value or "").strip()) for value in values)


def _load_user_ticktick_config(user_id: int) -> dict:
    return _load_user_provider_config(user_id, "ticktick_config")


def _legacy_service_config_diagnostics() -> dict:
    legacy = server_config.legacy_service_sections()
    return {
        "present": bool(legacy),
        "sections": sorted(legacy.keys()),
        "diagnostic": "检测到旧共享服务配置，已忽略；请每个用户在我的配置中单独填写" if legacy else "",
    }


def _load_user_provider_config(user_id: int, key: str) -> dict:
    conn = sqlite3.connect(getattr(store, "db_path", None) or time_logger_db.log_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT value FROM server_system_config WHERE user_id=? AND key=?",
            (user_id, key),
        ).fetchone()
        if not row or not row["value"]:
            return {}
        try:
            parsed = json.loads(row["value"])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    finally:
        conn.close()


USER_SERVICE_CONFIG_SCHEMA = "mytimelogger.user-service-config.v1"


def _provider_allowed_fields(key: str) -> set[str]:
    return {
        "ticktick_config": {"enabled", "access_token", "host", "timeout_seconds", "verify_tls", "username", "sync_interval"},
        "atimelogger_config": {
            "enabled", "username", "token", "auth_required", "auth_verified_at",
        },
        "s3_backup_config": {"enabled", "endpoint", "bucket", "region", "access_key", "access_key_id", "secret_key", "secret_access_key", "reports_prefix"},
        "ai_model_config": {"text_base_url", "text_api_key", "text_model", "vision_base_url", "vision_api_key", "vision_model", "text_backup_1_base_url", "text_backup_1_api_key", "text_backup_1_model", "text_backup_2_base_url", "text_backup_2_api_key", "text_backup_2_model", "vision_backup_1_base_url", "vision_backup_1_api_key", "vision_backup_1_model", "vision_backup_2_base_url", "vision_backup_2_api_key", "vision_backup_2_model", "backup_base_url", "backup_api_key", "backup_model"},
    }[key]


def _clean_provider_config(key: str, values: dict, current: dict | None = None) -> dict:
    if not isinstance(values, dict):
        raise ValueError("配置内容必须是对象")
    allowed = _provider_allowed_fields(key)
    current = current or {}
    clean = {field: current[field] for field in allowed if field in current}
    clean.update({field: values[field] for field in allowed if field in values})
    if key == "ticktick_config":
        clean["host"] = clean.get("host") or "dida365.com"
        clean["enabled"] = bool(clean.get("enabled", True))
    if key == "atimelogger_config":
        clean["enabled"] = bool(clean.get("token")) if "enabled" not in clean else bool(clean.get("enabled"))
    if key == "s3_backup_config":
        if "access_key_id" in clean:
            clean["access_key"] = clean.pop("access_key_id")
        if "secret_access_key" in clean:
            clean["secret_key"] = clean.pop("secret_access_key")
        if values.get("secret_key") == "" or values.get("secret_access_key") == "":
            clean["secret_key"] = current.get("secret_key", "")
        clean["bucket"] = clean.get("bucket") or "obss3"
        clean["region"] = clean.get("region") or "us-east-1"
        clean["reports_prefix"] = clean.get("reports_prefix") or "reports"
        clean["enabled"] = bool(clean.get("enabled", True))
    if key == "ai_model_config":
        for field in allowed:
            if field.endswith("_api_key") and values.get(field) == "":
                clean[field] = current.get(field, "")
    return clean


def _write_user_provider_config(user_id: int, key: str, clean: dict) -> dict:
    conn = sqlite3.connect(getattr(store, "db_path", None) or time_logger_db.log_path)
    try:
        updated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """
            INSERT INTO server_system_config (user_id, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (user_id, key, json.dumps(clean, ensure_ascii=False), updated_at),
        )
        conn.commit()
    finally:
        conn.close()
    return clean


def _save_user_provider_config(user_id: int, key: str, values: dict):
    current = _load_user_provider_config(user_id, key)
    clean = _clean_provider_config(key, values, current)
    return _write_user_provider_config(user_id, key, clean)


def _mark_atimelogger_auth_required(user_id: int):
    current = _load_user_provider_config(user_id, "atimelogger_config")
    if current:
        _save_user_provider_config(user_id, "atimelogger_config", {"auth_required": True, "auth_verified_at": ""})


def _validate_atimelogger_credentials(values: dict) -> tuple[str, str]:
    username = str(values.get("username") or "").strip()
    password = str(values.get("password") or "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="请输入 aTimeLogger 账号和密码")

    try:
        response = requests.post(
            "https://app.atimelogger.pro/auth/jwt",
            json={"username": username, "password": password},
            headers={"Accept": "application/json", "Origin": "https://app.atimelogger.pro"},
            timeout=30,
            verify=False,
        )
        response.raise_for_status()
        token = response.json().get("token")
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        if getattr(response, "status_code", None) in (401, 403):
            raise HTTPException(status_code=401, detail="aTimeLogger 拒绝了该账号或密码，请检查后重试") from exc
        raise HTTPException(status_code=502, detail="aTimeLogger 登录服务暂不可用，请稍后重试") from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="aTimeLogger 连接失败，请检查网络后重试") from exc
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="aTimeLogger 登录响应异常，请稍后重试") from exc

    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=502, detail="aTimeLogger 登录响应异常，请稍后重试")
    return username, token


def _s3_config_for_user(user: dict, cfg: dict | None = None) -> S3BackupConfig:
    data = {
        "enabled": True,
        "endpoint": "",
        "bucket": "obss3",
        "region": "us-east-1",
        "access_key": "",
        "secret_key": "",
        "reports_prefix": "reports",
    }
    data.update(cfg if cfg is not None else _load_user_provider_config(int(user["id"]), "s3_backup_config"))
    return S3BackupConfig(**{key: data[key] for key in S3BackupConfig.__dataclass_fields__ if key in data})


def _service_manager_s3_config() -> S3BackupConfig:
    user_id = store.get_default_user_id()
    if not user_id:
        return S3BackupConfig(enabled=True)
    return _s3_config_for_user({"id": user_id, "username": _username_for_user_id(user_id)})


def _provider_status(name: str, cfg: dict, configured: bool, summary: dict | None = None) -> dict:
    enabled = bool(cfg.get("enabled", True))
    return {
        "name": name,
        "scope": "personal",
        "enabled": enabled,
        "configured": configured,
        "runnable": enabled and configured,
        "status": "ready" if enabled and configured else "pending_configuration",
        "managed_by": "current_user" if configured else "not_bound",
        "diagnostic": "" if configured else f"当前用户未绑定 {name}",
        **(summary or {}),
    }


def _atimelogger_shared_status(user_id: int, cfg: dict | None = None) -> dict:
    cfg = cfg or _load_user_provider_config(user_id, "atimelogger_config")
    enabled = bool(cfg.get("enabled"))
    configured = bool(cfg.get("token"))
    verified = bool(cfg.get("auth_verified_at"))
    auth_required = bool(cfg.get("auth_required")) or (
        enabled and (not configured or not verified)
    )
    jobs = ATimeLoggerBackupStore(store._connect).status(user_id)
    type_map = cfg.get("type_map") if isinstance(cfg.get("type_map"), dict) else {}
    unmatched = cfg.get("unmatched_categories") if isinstance(cfg.get("unmatched_categories"), list) else []
    latest = jobs["latest"]
    return {
        "enabled": enabled, "configured": configured,
        "authenticated": configured and not auth_required, "auth_required": auth_required,
        "auth_state": "disabled" if not enabled else "auth_required" if auth_required else "ready",
        "username": str(cfg.get("username") or ""), "matched_count": len(type_map),
        "unmatched_count": len(unmatched), "pending_count": jobs["pending_count"],
        "failed_count": jobs["failed_count"], "latest_backup": latest,
        "updated_at": (latest or {}).get("updated_at") or str(cfg.get("auth_verified_at") or ""),
        "capability": "final_only",
        "capability_version": ATIMELOGGER_FINAL_BACKUP_VERSION,
    }


@app.put("/admin/provider-bindings/ticktick")
async def put_ticktick_binding(request: Request, user: dict = Depends(get_current_user)):
    values = await request.json()
    saved = _save_user_provider_config(int(user["id"]), "ticktick_config", values)
    return _provider_status("ticktick", saved, bool(saved.get("access_token")), {"host": saved.get("host", "dida365.com")})


@app.put("/admin/provider-bindings/atimelogger")
async def put_atimelogger_binding(request: Request, user: dict = Depends(get_current_user)):
    values = await request.json()
    username, token = _validate_atimelogger_credentials(values)
    values = {
        "enabled": bool(values.get("enabled", True)),
        "username": username,
        "token": token,
        "auth_required": False,
        "auth_verified_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
    }
    saved = _save_user_provider_config(int(user["id"]), "atimelogger_config", values)
    ATimeLoggerBackupStore(store._connect).retry_user(int(user["id"]))
    return _provider_status(
        "atimelogger", saved, bool(saved.get("token")),
        _atimelogger_shared_status(int(user["id"]), saved),
    )


@app.post("/admin/provider-bindings/atimelogger/retry")
def retry_atimelogger_backups(user: dict = Depends(get_current_user)):
    user_id = int(user["id"])
    released = ATimeLoggerBackupStore(store._connect).retry_user(user_id)
    return {"status": "ok", "released": released, **_atimelogger_shared_status(user_id)}


@app.get("/admin/provider-bindings/atimelogger/failures")
def get_atimelogger_backup_failures(user: dict = Depends(get_current_user)):
    user_id = int(user["id"])
    items = ATimeLoggerBackupStore(store._connect).failed_details(user_id)
    return {"count": len(items), "items": items}


@app.post("/admin/provider-bindings/atimelogger/repair")
async def repair_missing_atimelogger_backups(
    request: Request, user: dict = Depends(get_current_user),
):
    try:
        body = await request.json()
    except Exception:
        body = {}
    session_ids = body.get("session_ids") if isinstance(body, dict) else None
    if session_ids is not None and (
        not isinstance(session_ids, list) or len(session_ids) > 100
    ):
        raise HTTPException(status_code=400, detail="session_ids 必须是最多 100 项的数组")
    user_id = int(user["id"])
    repaired = ATimeLoggerBackupStore(store._connect).reconcile_user(
        user_id,
        cutover=None if session_ids else ATIMELOGGER_FINAL_ONLY_CUTOVER,
        session_ids=session_ids,
    )
    return {
        "status": "ok", "operation": "repair_missing_jobs",
        "repaired": repaired, **_atimelogger_shared_status(user_id),
    }


@app.put("/admin/provider-bindings/ai-model")
async def put_ai_model_binding(request: Request, user: dict = Depends(get_current_user)):
    values = await request.json()
    saved = _save_user_provider_config(int(user["id"]), "ai_model_config", values)
    text_configured = _configured(saved.get("text_base_url"), saved.get("text_api_key"), saved.get("text_model"))
    vision_configured = _configured(saved.get("vision_base_url"), saved.get("vision_api_key"), saved.get("vision_model"))
    return _provider_status("text_model", saved, text_configured and vision_configured, {
        "model": saved.get("text_model", ""),
        "vision_model": saved.get("vision_model", ""),
        "text_configured": text_configured,
        "vision_configured": vision_configured,
    })


@app.put("/admin/provider-bindings/s3")
async def put_user_s3_binding(request: Request, user: dict = Depends(get_current_user)):
    """保存当前用户 S3；服务管理者的配置同时驱动全库容灾。"""
    values = await request.json()
    try:
        saved = _save_user_provider_config(int(user["id"]), "s3_backup_config", values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"S3 配置格式错误：{exc}") from exc
    config = _s3_config_for_user(user, saved)
    return {"name": "s3_backup", **config.public(), "scope": "personal", "managed_by": "current_user"}


@app.get("/admin/provider-bindings/config")
def get_provider_bindings_config(user: dict = Depends(get_current_user)):
    user_id = int(user["id"])
    ticktick_cfg = _load_user_provider_config(user_id, "ticktick_config")
    atimelogger_cfg = _load_user_provider_config(user_id, "atimelogger_config")
    ai_cfg = _load_user_provider_config(user_id, "ai_model_config")
    s3_config = _s3_config_for_user(user)
    s3_cfg = {**s3_config.public(), **s3_config.diagnostics(user.get("username"), user_id)}
    s3_ready = bool(s3_cfg.get("enabled") and s3_cfg.get("configured"))
    return {
        "user": {"username": user.get("username", "")},
        "ticktick": {
            "enabled": bool(ticktick_cfg.get("enabled", True)),
            "configured": bool(ticktick_cfg.get("access_token")),
            "runnable": bool(ticktick_cfg.get("access_token")),
            "status": "ready" if ticktick_cfg.get("access_token") else "pending_configuration",
            "host": ticktick_cfg.get("host", "dida365.com"),
            "sync_interval": ticktick_cfg.get("sync_interval", ""),
            "token_configured": bool(ticktick_cfg.get("access_token")),
        },
        "atimelogger": _atimelogger_shared_status(user_id, atimelogger_cfg),
        "s3_backup": {**s3_cfg, "status": "ready" if s3_ready else "pending_configuration", "scope": "personal", "managed_by": "current_user"},
        "ai_model": {
            "enabled": True,
            "configured": _configured(ai_cfg.get("text_base_url"), ai_cfg.get("text_api_key"), ai_cfg.get("text_model"), ai_cfg.get("vision_base_url"), ai_cfg.get("vision_api_key"), ai_cfg.get("vision_model")),
            "text_base_url": ai_cfg.get("text_base_url", ""),
            "text_model": ai_cfg.get("text_model", ""),
            "text_key_configured": bool(ai_cfg.get("text_api_key")),
            "vision_base_url": ai_cfg.get("vision_base_url", ""),
            "vision_model": ai_cfg.get("vision_model", ""),
            "vision_key_configured": bool(ai_cfg.get("vision_api_key")),
            "backup_base_url": ai_cfg.get("backup_base_url", ""),
            "backup_model": ai_cfg.get("backup_model", ""),
            "backup_key_configured": bool(ai_cfg.get("backup_api_key")),
            "text_backup_1_base_url": ai_cfg.get("text_backup_1_base_url", ""), "text_backup_1_model": ai_cfg.get("text_backup_1_model", ""), "text_backup_1_key_configured": bool(ai_cfg.get("text_backup_1_api_key")),
            "text_backup_2_base_url": ai_cfg.get("text_backup_2_base_url", ""), "text_backup_2_model": ai_cfg.get("text_backup_2_model", ""), "text_backup_2_key_configured": bool(ai_cfg.get("text_backup_2_api_key")),
            "vision_backup_1_base_url": ai_cfg.get("vision_backup_1_base_url", ""), "vision_backup_1_model": ai_cfg.get("vision_backup_1_model", ""), "vision_backup_1_key_configured": bool(ai_cfg.get("vision_backup_1_api_key")),
            "vision_backup_2_base_url": ai_cfg.get("vision_backup_2_base_url", ""), "vision_backup_2_model": ai_cfg.get("vision_backup_2_model", ""), "vision_backup_2_key_configured": bool(ai_cfg.get("vision_backup_2_api_key")),
        },
    }


def _service_config_export_for_user(user: dict) -> dict:
    user_id = int(user["id"])
    return {
        "schema": USER_SERVICE_CONFIG_SCHEMA,
        "exported_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
        "environment": server_config.get_runtime("environment", ""),
        "user": {
            "id": user_id,
            "username": user.get("username", ""),
        },
        "ticktick": _load_user_provider_config(user_id, "ticktick_config"),
        "s3_backup": _load_user_provider_config(user_id, "s3_backup_config"),
        "ai_model": _load_user_provider_config(user_id, "ai_model_config"),
    }


def _require_config_section(payload: dict, name: str) -> dict:
    section = payload.get(name)
    if not isinstance(section, dict):
        raise HTTPException(status_code=400, detail=f"导入配置缺少 {name} 对象")
    return section


def _import_service_config_for_user(user: dict, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="导入配置必须是 JSON 对象")
    if payload.get("schema") != USER_SERVICE_CONFIG_SCHEMA:
        raise HTTPException(status_code=400, detail=f"导入配置 schema 必须是 {USER_SERVICE_CONFIG_SCHEMA}")

    user_id = int(user["id"])
    sections = {
        "ticktick_config": _require_config_section(payload, "ticktick"),
        "s3_backup_config": _require_config_section(payload, "s3_backup"),
        "ai_model_config": _require_config_section(payload, "ai_model"),
    }
    try:
        saved = {key: _clean_provider_config(key, values, {}) for key, values in sections.items()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"导入配置格式错误：{exc}") from exc

    conn = sqlite3.connect(getattr(store, "db_path", None) or time_logger_db.log_path)
    try:
        updated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        with conn:
            for key, clean in saved.items():
                conn.execute(
                    """
                    INSERT INTO server_system_config (user_id, key, value, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                    """,
                    (user_id, key, json.dumps(clean, ensure_ascii=False), updated_at),
                )
    finally:
        conn.close()

    s3_config = _s3_config_for_user(user, saved["s3_backup_config"])
    s3_summary = {**s3_config.public(), **s3_config.diagnostics(user.get("username"), user_id)}

    return {
        "schema": USER_SERVICE_CONFIG_SCHEMA,
        "imported": True,
        "user": {"username": user.get("username", "")},
        "ticktick": _provider_status(
            "ticktick",
            saved["ticktick_config"],
            bool(saved["ticktick_config"].get("access_token")),
            {"host": saved["ticktick_config"].get("host", "dida365.com")},
        ),
        "s3_backup": {**s3_summary, "scope": "personal", "managed_by": "current_user"},
        "ai_model": {
            "text_configured": _configured(
                saved["ai_model_config"].get("text_base_url"),
                saved["ai_model_config"].get("text_api_key"),
                saved["ai_model_config"].get("text_model"),
            ),
            "vision_configured": _configured(
                saved["ai_model_config"].get("vision_base_url"),
                saved["ai_model_config"].get("vision_api_key"),
                saved["ai_model_config"].get("vision_model"),
            ),
            "text_model": saved["ai_model_config"].get("text_model", ""),
            "vision_model": saved["ai_model_config"].get("vision_model", ""),
            "backup_model": saved["ai_model_config"].get("backup_model", ""),
        },
    }


@app.get("/admin/provider-bindings/export")
def export_provider_bindings(user: dict = Depends(get_current_user)):
    filename = f"mytimelogger-service-config-{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')}.json"
    return Response(
        content=json.dumps(_service_config_export_for_user(user), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/admin/provider-bindings/import")
async def import_provider_bindings(request: Request, user: dict = Depends(get_current_user)):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="导入配置不是合法 JSON") from exc
    result = _import_service_config_for_user(user, payload)
    return result


@app.get("/admin/integration-config/status")
def get_integration_config_status(user: dict = Depends(get_current_user)):
    s3_config = _s3_config_for_user(user).diagnostics(user.get("username"), int(user["id"]))
    s3_configured = bool(s3_config.get("configured"))
    atimelogger_cfg = _load_user_provider_config(int(user["id"]), "atimelogger_config")
    ticktick_cfg = _load_user_provider_config(int(user["id"]), "ticktick_config")
    ai_cfg = _load_user_provider_config(int(user["id"]), "ai_model_config")
    type_map = atimelogger_cfg.get("type_map") if isinstance(atimelogger_cfg.get("type_map"), dict) else {}
    atimelogger_configured = bool(atimelogger_cfg.get("token") or (atimelogger_cfg.get("username") and atimelogger_cfg.get("password")))
    atimelogger_authenticated = bool(
        atimelogger_configured
        and atimelogger_cfg.get("auth_verified_at")
        and not atimelogger_cfg.get("auth_required")
    )
    text_configured = _configured(ai_cfg.get("text_base_url"), ai_cfg.get("text_api_key"), ai_cfg.get("text_model"))
    vision_configured = _configured(ai_cfg.get("vision_base_url"), ai_cfg.get("vision_api_key"), ai_cfg.get("vision_model"))
    ticktick_configured = bool(ticktick_cfg.get("access_token"))
    
    response = {
        "environment": server_config.get_runtime("environment", ""),
        "legacy_service_config": _legacy_service_config_diagnostics(),
        "ticktick": {
            "enabled": bool(ticktick_cfg.get("enabled", True)),
            "configured": ticktick_configured,
            "runnable": ticktick_configured,
            "status": "ready" if ticktick_configured else "pending_configuration",
            "scope": "personal",
            "host": ticktick_cfg.get("host", "dida365.com"),
            "diagnostic": "" if ticktick_configured else "当前用户未绑定 ticktick",
        },
        "s3_backup": {
            "scope": "personal",
            "enabled": bool(s3_config.get("enabled")),
            "configured": s3_configured,
            "runnable": bool(s3_configured and s3_config.get("enabled")),
            "status": "ready" if s3_configured and s3_config.get("enabled") else "pending_configuration",
            "diagnostic": "" if s3_configured else "系统容灾已启用，待服务管理者配置",
        },
        "atimelogger": {
            **_atimelogger_shared_status(int(user["id"]), atimelogger_cfg),
            "scope": "personal",
            "diagnostic": "" if atimelogger_configured else "当前用户未绑定 atimelogger",
        },
        "text_model": {
            "scope": "personal",
            "enabled": True,
            "configured": text_configured and vision_configured,
            "runnable": text_configured and vision_configured,
            "status": "ready" if text_configured and vision_configured else "pending_configuration",
            "model": ai_cfg.get("text_model", ""),
            "vision_model": ai_cfg.get("vision_model", ""),
            "endpoint_configured": bool(ai_cfg.get("text_base_url") or ai_cfg.get("vision_base_url")),
            "text_configured": text_configured,
            "vision_configured": vision_configured,
            "diagnostic": "" if (text_configured and vision_configured) else "当前用户未配置大模型",
        },
    }
    return redact_mapping(response)


from pydantic import BaseModel
class ServerConfigUpdate(BaseModel):
    raw_text: str

@app.get("/admin/server-config")
def get_server_config(user: dict = Depends(get_current_user)):
    require_service_manager(user)
    return {"raw_text": server_config.get_raw_text()}

@app.put("/admin/server-config")
def put_server_config(update: ServerConfigUpdate, user: dict = Depends(get_current_user)):
    require_service_manager(user)
    try:
        server_config.save_raw_text(update.raw_text)
        return {"status": "ok", "message": "配置已保存并重载"}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"保存失败：配置不是合法 JSONC，{e.msg}") from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"保存失败：{str(e)}")


@app.get("/admin/logging/config")
def get_logging_config(user: dict = Depends(get_current_user)):
    require_service_manager(user)
    return logging_config_store.load().public()


@app.put("/admin/logging/config")
async def put_logging_config(request: Request, user: dict = Depends(get_current_user)):
    require_service_manager(user)
    try:
        values = await request.json()
        config = logging_config_store.save(values)
        apply_runtime_logging_config(config)
        return config.public()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/sleep", response_class=FileResponse)
def sleep_page():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    return FileResponse(template_path)


@app.get("/config", response_class=FileResponse)
def config_page():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "config.html")
    return FileResponse(template_path)


@app.get("/login", response_class=FileResponse)
def service_login_page():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "login.html")
    return FileResponse(template_path)


@app.get("/exercise", response_class=FileResponse)
def exercise_page():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "exercise.html")
    return FileResponse(template_path)


def _exercise_db_path() -> str:
    db = getattr(sync_hub, "db", None)
    return getattr(db, "log_path", None) or time_logger_db.log_path


def _exercise_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_exercise_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _beijing_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def _beijing_today() -> str:
    return _beijing_now().strftime("%Y-%m-%d")


def _exercise_now_str() -> str:
    return _beijing_now().strftime("%Y-%m-%d %H:%M:%S")


def _exercise_weight_window(date: str, existing_weight=None) -> dict:
    now = _beijing_now()
    today = now.strftime("%Y-%m-%d")
    hour = now.hour
    editable = date == today
    reason = ""
    if date < today:
        reason = "历史日期已锁定"
    elif date > today:
        reason = "未来日期不能录入体重"
    elif hour < 6:
        reason = "当前可记录体重；北京时间 06:00-09:00 计为按时称重"
    elif hour >= 9:
        reason = "已超过北京时间 09:00，仍可补录体重；守时结果保持逾期"
    return {
        "editable": editable,
        "overdue": date == today and hour >= 9 and existing_weight is None,
        "reason": reason,
        "start_hour": 6,
        "end_hour": 9,
    }


def _exercise_day_key(date: str) -> str:
    names = ["周一", "周二", "周三", "周四", "周五", "六", "日"]
    try:
        return names[datetime.strptime(date, "%Y-%m-%d").weekday()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date")


def _exercise_row_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _exercise_active_plan(conn: sqlite3.Connection, user_id: int) -> str:
    row = conn.execute(
        "SELECT value FROM server_system_config WHERE user_id=? AND key='active_exercise_plan_version'",
        (user_id,),
    ).fetchone()
    return (row["value"] if row and row["value"] else "v1")


def _exercise_item_weight(item: dict) -> int:
    try:
        tags = json.loads(item.get("tags_json") or "{}") if isinstance(item.get("tags_json"), str) else (item.get("tags_json") or {})
    except (TypeError, ValueError, json.JSONDecodeError):
        tags = {}
    if tags.get("stairs"):
        return 5
    section, sets = str(item.get("section") or ""), str(item.get("sets") or "")
    if section == "有氧":
        match = re.search(r"\d+", sets)
        minutes = int(match.group(0)) if match else 0
        return 5 if minutes >= 25 else 4 if minutes >= 20 else 3 if minutes >= 15 else 2
    if tags.get("core") or tags.get("hang"):
        return 2
    return 3 if section == "无氧" else 2


def _exercise_item_points(items: list[dict], pool: int) -> list[int]:
    if not items:
        return []
    weights = [_exercise_item_weight(item) for item in items]
    total = sum(weights) or 1
    raw = [pool * weight / total for weight in weights]
    points = [int(value) for value in raw]
    for index in sorted(range(len(items)), key=lambda i: (-(raw[i] - points[i]), i))[:max(0, pool - sum(points))]:
        points[index] += 1
    return points


def _exercise_timing_score(actual: str | None, target: str, maximum: float, late_floor: bool = True) -> float:
    if not actual:
        return 0
    try:
        ah, am = map(int, str(actual)[:5].split(":")); th, tm = map(int, str(target)[:5].split(":"))
    except (TypeError, ValueError):
        return 0
    delta = ah * 60 + am - th * 60 - tm
    if delta <= 0: return round(maximum, 2)
    if delta <= 15: return round(maximum * .6, 2)
    if delta <= 30: return round(maximum * .3, 2)
    return round(maximum * .1, 2) if late_floor else 0


def _exercise_score(items: list[dict], checkins: list[dict], plan_definition: dict, day_key: str, date: str) -> dict:
    done_keys = {str(row.get("item_key") or "") for row in checkins if int(row.get("status") or 0) == 1}
    variant = "rain" if any(key.startswith(f"ex-{date}-r-") for key in done_keys) else "gym"
    selected = sorted([item for item in items if str(item.get("variant") or "gym") == variant], key=lambda item: (int(item.get("sort_order") or 0), str(item.get("id") or "")))
    item_keys = [(item, f"ex-{date}-{'r' if variant == 'rain' else 'g'}-{int(item.get('sort_order') or 0)}") for item in selected]
    exercise_pool = int(plan_definition.get("exercisePoints") or 0)
    is_v4 = str(plan_definition.get("version") or "") == "v4"
    item_points = []
    for item in selected:
        try:
            tags = json.loads(item.get("tags_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            tags = {}
        item_points.append(int(tags.get("scorePoints") or 0) if is_v4 else 0)
    if not is_v4:
        item_points = _exercise_item_points(selected, exercise_pool)
    item_map = {key: (item, item_points[index]) for index, (item, key) in enumerate(item_keys)}
    completed_items = sum(1 for key in item_map if key in done_keys)
    score_rules = plan_definition.get("sundayScore") if day_key == "日" else plan_definition.get("saturdayScore") if day_key == "六" else plan_definition.get("weekdayScore")
    cats: dict[str, dict[str, float]] = {}; total_score = 0.0; schedule_scores: dict[str, dict] = {}
    for rule in [] if is_v4 else score_rules or []:
        if len(rule) < 3: continue
        index, points, category = rule[0], float(rule[1] or 0), rule[2]
        if points <= 0: continue
        key = f"sc-{date}-{index}"
        checkin = next((row for row in checkins if str(row.get("item_key") or "") == key), None)
        earned = _exercise_timing_score(checkin.get("completed_time"), rule[3], points, plan_definition.get("version") == "v2") if len(rule) > 3 and checkin else points if key in done_keys else 0
        cats.setdefault(category, {"s": 0, "m": 0}); cats[category]["s"] += earned; cats[category]["m"] += points; total_score += earned
        item_score = schedule_scores.setdefault(key, {"item_key": key, "earned_points": 0.0, "max_points": 0.0, "difficulty": "normal", "score_rule_version": plan_definition.get("version") or "v1", "score_reason": "not_completed"})
        item_score["earned_points"] = round(item_score["earned_points"] + earned, 2)
        item_score["max_points"] = round(item_score["max_points"] + points, 2)
        if key in done_keys: item_score["score_reason"] = "completed"
    if is_v4 or day_key not in ("六", "日"):
        exercise_points = int(plan_definition.get("exercisePoints") or 0)
        earned = sum(points for key, (_, points) in item_map.items() if key in done_keys)
        category = "运动训练" if is_v4 else "运动"
        cats.setdefault(category, {"s": 0, "m": 0}); cats[category]["s"] += earned; cats[category]["m"] += exercise_points; total_score += earned
    exercise_scores = [{"item_key": key, "earned_points": points if key in done_keys else 0, "max_points": points,
                        "difficulty": "hard" if points >= 6 else "normal" if points >= 4 else "easy", "score_rule_version": plan_definition.get("version") or "v1",
                        "score_reason": "completed" if key in done_keys else "not_completed",
                        "score_scope": "training" if is_v4 else "training"} for key, (_, points) in item_map.items()]
    return {"total": round(total_score, 2), "cats": cats, "completed_items": completed_items, "total_items": len(item_map), "exercise_variant": variant,
            "item_scores": [*schedule_scores.values(), *exercise_scores]}


def _exercise_plan_definition(conn: sqlite3.Connection, user_id: int, plan_version: str) -> dict:
    version = conn.execute(
        "SELECT version, title, source_name, exercise_points FROM server_exercise_plan_versions WHERE user_id=? AND version=?",
        (user_id, plan_version),
    ).fetchone()
    schedules = [dict(row) for row in conn.execute(
        """
        SELECT schedule_type, sort_order, time, item, note, accent
        FROM server_exercise_plan_schedule_items
        WHERE user_id=? AND plan_version=?
        ORDER BY schedule_type, sort_order
        """,
        (user_id, plan_version),
    ).fetchall()]
    removed_schedule_items = {"到达图书馆", "离开图书馆", "到达体育公园", "达到体育公园", "离开体育公园", "结束户外锻炼"}
    schedules = [row for row in schedules if str(row.get("item") or "").strip().split(None, 1)[-1] not in removed_schedule_items]
    diet = [dict(row) for row in conn.execute(
        """
        SELECT rule_key, time, content, note
        FROM server_exercise_plan_diet_rules
        WHERE user_id=? AND plan_version=?
        ORDER BY sort_order
        """,
        (user_id, plan_version),
    ).fetchall()]
    scores = [dict(row) for row in conn.execute(
        """
        SELECT day_type, schedule_index, points, category, target_time
        FROM server_exercise_plan_score_rules
        WHERE user_id=? AND plan_version=?
        ORDER BY day_type, sort_order
        """,
        (user_id, plan_version),
    ).fetchall()]
    categories = [row["category"] for row in conn.execute(
        """
        SELECT category FROM server_exercise_plan_category_rules
        WHERE user_id=? AND plan_version=?
        ORDER BY sort_order
        """,
        (user_id, plan_version),
    ).fetchall()]
    progress = [dict(row) for row in conn.execute(
        """
        SELECT when_text, text FROM server_exercise_plan_progress_items
        WHERE user_id=? AND plan_version=?
        ORDER BY sort_order
        """,
        (user_id, plan_version),
    ).fetchall()]
    def schedule(schedule_type: str) -> list[dict]:
        return [
            {"time": row["time"], "item": row["item"], "note": row.get("note") or "", "accent": row.get("accent") or "default"}
            for row in schedules if row["schedule_type"] == schedule_type
        ]
    def score(day_type: str) -> list[list]:
        result = []
        for row in scores:
            if row["day_type"] != day_type:
                continue
            item = [row["schedule_index"], row["points"], row["category"]]
            if row.get("target_time"):
                item.append(row["target_time"])
            result.append(item)
        return result
    return {
        "version": plan_version,
        "title": version["title"] if version else "每日打卡表",
        "sourceName": version["source_name"] if version else "",
        "exercisePoints": version["exercise_points"] if version and version["exercise_points"] is not None else 0,
        "weekdaySchedule": schedule("weekday"),
        "restSchedule": schedule("rest"),
        "sundayExtra": (schedule("sunday_extra") or [{"time": "", "item": "", "note": "", "accent": "default"}])[0],
        "diet": diet,
        "weekdayScore": score("weekday"),
        "saturdayScore": score("saturday"),
        "sundayScore": score("sunday"),
        "categoryOrder": categories,
        "progress": [{"when": row["when_text"], "text": row["text"]} for row in progress],
    }


def _body_metric_target_in_txn(conn: sqlite3.Connection, user_id: int, date: str, plan_version: str) -> tuple[str, str] | None:
    """返回当天体重/体脂共用打卡项的服务端键，不能信任客户端传入的名称。"""
    schedule_type = "weekday" if _exercise_day_key(date) not in {"六", "日"} else "rest"
    removed = {"到达图书馆", "离开图书馆", "到达体育公园", "达到体育公园", "离开体育公园", "结束户外锻炼"}
    rows = conn.execute(
        """SELECT item FROM server_exercise_plan_schedule_items WHERE user_id=? AND plan_version=? AND schedule_type=?
           ORDER BY sort_order""", (user_id, plan_version, schedule_type),
    ).fetchall()
    visible = [str(row["item"] or "") for row in rows if str(row["item"] or "").strip().split(None, 1)[-1] not in removed]
    for index, name in enumerate(visible):
        if "体重" in name and "体脂" in name:
            return f"sc-{date}-{index}", name
    return None


def _body_metric_lock_in_txn(conn: sqlite3.Connection, user_id: int, date: str, plan_version: str | None = None):
    params: list[object] = [user_id, date]
    where = "user_id=? AND date=? AND locked_at IS NOT NULL"
    if plan_version:
        where += " AND plan_version=?"
        params.append(plan_version)
    return conn.execute(f"SELECT * FROM server_exercise_checkins WHERE {where} ORDER BY locked_at DESC LIMIT 1", params).fetchone()


def _lock_overdue_body_metrics() -> int:
    """09:00 后和服务重启补偿时，锁定未同时填写体重、体脂的唯一计划项。"""
    now = _beijing_now()
    if now.hour < 9:
        return 0
    date, now_text, changed_users = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S"), set()
    with _exercise_conn() as conn:
        for user_row in conn.execute("SELECT id FROM users").fetchall():
            user_id = int(user_row["id"])
            plan_version = _exercise_active_plan(conn, user_id)
            if plan_version == "v4":
                fact = _exercise_v4().settle_body_deadline(conn, user_id, date, now)
                _exercise_v4().settle(conn, user_id, date, now)
                if fact and fact.get("_changed"):
                    changed_users.add(user_id)
                continue
            target = _body_metric_target_in_txn(conn, user_id, date, plan_version)
            if not target or _body_metric_lock_in_txn(conn, user_id, date, plan_version):
                continue
            complete = conn.execute(
                """SELECT 1 FROM server_exercise_daily_logs WHERE user_id=? AND date=?
                   AND weight IS NOT NULL AND body_fat_rate IS NOT NULL LIMIT 1""", (user_id, date),
            ).fetchone()
            if complete:
                continue
            item_key, item_name = target
            log_id = f"server-exercise-{user_id}-{date}-{plan_version}-daily"
            conn.execute("""INSERT OR IGNORE INTO server_exercise_daily_logs
                (id,user_id,date,plan_version,exercise_type,day_name,created_at,updated_at)
                VALUES (?,?,?,?, 'daily',?,?,?)""", (log_id, user_id, date, plan_version, _exercise_day_key(date), now_text, now_text))
            existing = conn.execute("SELECT id FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=? AND item_key=?", (user_id, date, plan_version, item_key)).fetchone()
            checkin_id = existing["id"] if existing else f"body-metric-lock:{user_id}:{date}:{plan_version}"
            penalty_source = f"body-metric-deadline:{date}"
            conn.execute("""INSERT INTO server_exercise_checkins
                (id,user_id,log_id,plan_version,item_key,status,note,item_name,date,locked_at,lock_reason,deadline_penalty_source_id,deadline_penalty_amount,created_at,updated_at)
                VALUES (?,?,?,?,?,-1,?,?,?,?,'body_metrics_missing_at_09:00',?,-50,?,?)
                ON CONFLICT(id) DO UPDATE SET status=-1,note=excluded.note,locked_at=excluded.locked_at,
                  lock_reason=excluded.lock_reason,updated_at=excluded.updated_at""",
                (checkin_id, user_id, log_id, plan_version, item_key, "09:00 超时锁定：体重或体脂率未填写", item_name, date, now_text, penalty_source, now_text, now_text))
            store.reward_wallet_service.append_ledger_in_txn(
                conn, user_id, -50, "body_metric_deadline_penalty", penalty_source,
                "体重体脂逾期未填写（09:00）", date,
                f"body-metric-deadline-penalty:{user_id}:{date}", now_text,
            )
            row = dict(conn.execute("SELECT * FROM server_exercise_checkins WHERE id=?", (checkin_id,)).fetchone())
            _exercise_write_change(conn, user_id, "exercise_checkin", checkin_id, row)
            changed_users.add(user_id)
        conn.commit()
    for user_id in changed_users:
        sync_hub._notify_clients(["exercise_daily_logs", "exercise_deadline_facts", "exercise_item_scores", "exercise_settlements", "reward_ledger", "user_wallets"], user_id)
    return len(changed_users)


def _exercise_write_change(conn: sqlite3.Connection, user_id: int, entity_type: str, entity_id: str, row: dict) -> None:
    writer = getattr(getattr(sync_hub, "db", None), "write_server_change", None)
    if not writer:
        return
    writer(
        user_id,
        entity_type,
        entity_id,
        "upsert",
        row,
        table_name=f"server_{entity_type}s",
        device_id="server-exercise-page",
        conn=conn,
    )


def _exercise_v4_record_change(conn, user_id: int, table: str, record_id: str, operation: str = "upsert") -> None:
    writer = getattr(getattr(sync_hub, "db", None), "write_server_change", None)
    if writer:
        writer(user_id, table.removeprefix("server_"), str(record_id), operation, {"id": record_id},
               table_name=table, device_id="server-exercise-v4", conn=conn)


def _exercise_v4() -> ExerciseV4Service:
    return ExerciseV4Service(store.reward_wallet_service, _exercise_v4_record_change)


def _persist_exercise_item_scores(conn: sqlite3.Connection, user_id: int, date: str, plan_version: str, score: dict, now: str) -> None:
    for item in score.get("item_scores") or []:
        item_key = str(item.get("item_key") or "")
        if not item_key:
            continue
        score_id = f"exercise-item-score:{user_id}:{date}:{plan_version}:{item_key}"
        conn.execute(
            """INSERT INTO server_exercise_item_scores
               (id,user_id,date,plan_version,item_key,earned_points,max_points,difficulty,score_rule_version,score_reason,score_scope,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, ?,?,?)
               ON CONFLICT(user_id,date,plan_version,item_key) DO UPDATE SET
                 earned_points=excluded.earned_points,max_points=excluded.max_points,difficulty=excluded.difficulty,
                 score_rule_version=excluded.score_rule_version,score_reason=excluded.score_reason,score_scope=excluded.score_scope,status=excluded.status,updated_at=excluded.updated_at""",
            (score_id, user_id, date, plan_version, item_key, item.get("earned_points", 0), item.get("max_points", 0),
             item.get("difficulty"), item.get("score_rule_version") or plan_version, item.get("score_reason"),
             item.get("score_scope") or "schedule", "active", now, now),
        )
        row = conn.execute("SELECT * FROM server_exercise_item_scores WHERE user_id=? AND date=? AND plan_version=? AND item_key=?", (user_id, date, plan_version, item_key)).fetchone()
        if row:
            _exercise_write_change(conn, user_id, "exercise_item_score", row["id"], dict(row))


def _exercise_completion_status_in_txn(conn: sqlite3.Connection, user_id: int, date: str, plan_version: str) -> tuple[bool, str]:
    """只读取已持久化的应评分事实；说明项和可选数据不进入分母。"""
    rows = conn.execute(
        """SELECT earned_points,max_points FROM server_exercise_item_scores
           WHERE user_id=? AND date=? AND plan_version=? AND max_points>0
             AND (?!='v4' OR score_scope IN ('training','diet','body'))""",
        (user_id, date, plan_version, plan_version),
    ).fetchall()
    if not rows:
        return False, "无应评分条目"
    if any(float(row["earned_points"] or 0) < float(row["max_points"] or 0) for row in rows):
        return False, "存在未满分应评分条目"
    return True, "全部应评分条目满分"


def _settle_exercise_completion_reward_in_txn(conn: sqlite3.Connection, user_id: int, date: str, plan_version: str, now: str) -> tuple[bool, float, str]:
    is_all_complete, reason = _exercise_completion_status_in_txn(conn, user_id, date, plan_version)
    amount = 100.0 if is_all_complete else 0.0
    ledger_id = f"exercise-completion-reward:{user_id}:{plan_version}:{date}"
    description = f"运动指标全完成奖励：{plan_version}" if is_all_complete else f"运动指标全完成奖励：未获得（{plan_version}）"
    existing = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id)).fetchone()
    if existing is None:
        store.reward_wallet_service.append_ledger_in_txn(
            conn, user_id, amount, "exercise_completion_reward", f"exercise-completion:{plan_version}:{date}",
            description, date, ledger_id, now,
        )
    elif float(existing["amount"]) != amount:
        conn.execute("UPDATE server_reward_ledger SET amount=?,description=?,updated_at=? WHERE user_id=? AND id=?", (amount, description, now, user_id, ledger_id))
        wallet = store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(conn, user_id, _exercise_now_str)
        store._record_server_change(conn, user_id, "server_reward_ledger", ledger_id, "upsert", {"id": ledger_id, "amount": amount, "description": description})
        store._record_server_change(conn, user_id, "server_user_wallets", user_id, "upsert", {"user_id": user_id, "balance": wallet["balance"], "updated_at": now})
    return is_all_complete, amount, reason


def _exercise_history(conn: sqlite3.Connection, user_id: int, plan_version: str, limit: int = 8) -> list[dict]:
    rows = conn.execute(
        """
        SELECT date, plan_version, week_num, day_name, weight, body_fat_rate, completed_items, total_items, updated_at
        FROM server_exercise_daily_logs
        WHERE user_id=? AND plan_version=? AND exercise_type='daily'
          AND (weight IS NOT NULL OR body_fat_rate IS NOT NULL OR score_snapshot IS NOT NULL OR completed_items > 0 OR total_items > 0)
        ORDER BY date DESC, updated_at DESC
        LIMIT ?
        """,
        (user_id, plan_version, limit),
    ).fetchall()
    history = []
    for row in rows:
        total_items = int(row["total_items"] or 0)
        completed_items = int(row["completed_items"] or 0)
        history.append({
            **dict(row),
            "completed_items": completed_items,
            "total_items": total_items,
            "completion_rate": round(completed_items / total_items * 100) if total_items else 0,
        })
    return history


@app.get("/api/exercise/state")
def get_exercise_state(
    date: str | None = None,
    plan_version: str | None = None,
    user: dict = Depends(get_current_user_optional),
):
    date = date or _beijing_today()
    if date == _beijing_today() and _beijing_now().hour >= 9:
        _lock_overdue_body_metrics()
    day_key = _exercise_day_key(date)
    locked = date < _beijing_today()
    v4_score = None
    with _exercise_conn() as conn:
        active_plan = plan_version or _exercise_active_plan(conn, user["id"])
        if active_plan == "v4":
            service, now = _exercise_v4(), _beijing_now()
            service.ensure_diet_rows(conn, user["id"], date, now)
            service.close_diet(conn, user["id"], date, now)
            service.settle_body_deadline(conn, user["id"], date, now)
            v4_score = service.settle(conn, user["id"], date, now)
            conn.commit()
        versions = [dict(row) for row in conn.execute(
            "SELECT version, title, is_active FROM server_exercise_plan_versions WHERE user_id=? ORDER BY version",
            (user["id"],),
        ).fetchall()]
        items = [dict(row) for row in conn.execute(
            """
            SELECT id, day_key, variant, section, sort_order, name, sets, intensity, color, tags_json
            FROM server_exercise_plan_items
            WHERE user_id=? AND plan_version=? AND day_key=? AND is_active=1
            ORDER BY variant, sort_order
            """,
            (user["id"], active_plan, day_key),
        ).fetchall()]
        variant_indexes = {"schedule": 0, "gym": 0, "rain": 0}
        for item in items:
            variant = str(item.get("variant") or "schedule")
            index = variant_indexes.get(variant, 0)
            prefix = "sc" if variant == "schedule" else "ex-" + ("r" if variant == "rain" else "g")
            item["item_key"] = f"{prefix}-{date}-{index}" if variant == "schedule" else f"ex-{date}-{'r' if variant == 'rain' else 'g'}-{index}"
            variant_indexes[variant] = index + 1
        checkins = [dict(row) for row in conn.execute(
            """
            SELECT id, log_id, plan_version, item_key, status, note, completed_time, plan_item_id, item_name, date, locked_at, lock_reason,
                   deadline_penalty_source_id, deadline_penalty_amount
            FROM server_exercise_checkins
            WHERE user_id=? AND date=? AND plan_version=?
            """,
            (user["id"], date, active_plan),
        ).fetchall()]
        log = _exercise_row_dict(conn.execute(
            """
            SELECT * FROM server_exercise_daily_logs
            WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'
            """,
            (user["id"], date, active_plan),
        ).fetchone())
        plan_definition = _exercise_plan_definition(conn, user["id"], active_plan)
        item_scores = [dict(row) for row in conn.execute(
            "SELECT * FROM server_exercise_item_scores WHERE user_id=? AND date=? AND plan_version=? ORDER BY item_key",
            (user["id"], date, active_plan),
        ).fetchall()]
        current_weight = log.get("weight") if log else None
        current_body_fat_rate = log.get("body_fat_rate") if log else None
        body_metric_lock = _body_metric_lock_in_txn(conn, user["id"], date, active_plan)
        diet_checkins = [dict(row) for row in conn.execute(
            "SELECT * FROM server_exercise_diet_checkins WHERE user_id=? AND date=? AND plan_version=? ORDER BY rule_key",
            (user["id"], date, active_plan),
        ).fetchall()] if active_plan == "v4" else []
        deadline_facts = [dict(row) for row in conn.execute(
            "SELECT * FROM server_exercise_deadline_facts WHERE user_id=? AND date=? AND plan_version=? ORDER BY fact_type",
            (user["id"], date, active_plan),
        ).fetchall()] if active_plan == "v4" else []
        history = _exercise_history(conn, user["id"], active_plan)
    score = _exercise_score(items, checkins, plan_definition, day_key, date)
    if v4_score is not None:
        score = v4_score
    if active_plan != "v4" and locked and log and log.get("score_snapshot"):
        try:
            score = {**json.loads(log["score_snapshot"]), "completed_items": log.get("completed_items") or score.get("completed_items", 0), "total_items": log.get("total_items") or score.get("total_items", 0)}
        except (TypeError, ValueError):
            pass
    return {
        "status": "ok",
        "date": date,
        "day_key": day_key,
        "locked": locked,
        "beijing_today": _beijing_today(),
        "now_beijing": _exercise_now_str(),
        "weight_window": {**_exercise_weight_window(date, current_weight), "editable": not bool(body_metric_lock), "overdue": False if body_metric_lock else _exercise_weight_window(date, current_weight)["overdue"]},
        "body_metric_locked": bool(body_metric_lock),
        "plan_version": active_plan,
        "plan_versions": versions,
        "items": items,
        "plan_definition": plan_definition,
        "checkins": checkins,
        "item_scores": item_scores,
        "diet_checkins": diet_checkins,
        "deadline_facts": deadline_facts,
        "daily_log": log,
        "weight": current_weight,
        "body_fat_rate": current_body_fat_rate,
        "history": history,
        "score": score,
    }


@app.post("/api/exercise/checkin")
async def post_exercise_checkin(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date") or _beijing_today()
    if date == _beijing_today() and _beijing_now().hour >= 9:
        _lock_overdue_body_metrics()
    _exercise_day_key(date)
    if date < _beijing_today():
        raise HTTPException(status_code=409, detail="Historical exercise score is locked")
    plan_version = body.get("plan_version") or "v0"
    item_key = body.get("item_key")
    if not item_key:
        raise HTTPException(status_code=400, detail="item_key is required")
    now = _exercise_now_str()
    log_id = f"server-exercise-{user['id']}-{date}-{plan_version}-daily"
    raw_status = int(body.get("status") or 0)
    status_value = 1 if raw_status > 0 else -1 if raw_status < 0 else 0
    completed_time = body.get("completed_time") if status_value == 1 else None
    if status_value == 1 and not completed_time:
        completed_time = now
    with _exercise_conn() as conn:
        locked_row = _body_metric_lock_in_txn(conn, user["id"], date)
        target = _body_metric_target_in_txn(conn, user["id"], date, plan_version)
        if locked_row and target and str(item_key) == target[0]:
            raise HTTPException(status_code=409, detail="体重和体脂率已于北京时间 09:00 超时锁定，不能修改")
        conn.execute(
            """
            INSERT OR IGNORE INTO server_exercise_daily_logs
              (id, user_id, date, plan_version, exercise_type, day_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'daily', ?, ?, ?)
            """,
            (log_id, user["id"], date, plan_version, _exercise_day_key(date), now, now),
        )
        existing = conn.execute(
            "SELECT * FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=? AND item_key=?",
            (user["id"], date, plan_version, item_key),
        ).fetchone()
        checkin_id = existing["id"] if existing else f"server-checkin-{uuid.uuid4().hex}"
        existing_plan_item_id = existing["plan_item_id"] if existing else None
        conn.execute(
            """
            INSERT INTO server_exercise_checkins
              (id, user_id, log_id, plan_version, item_key, status, note, completed_time,
               plan_item_id, item_name, date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              status=excluded.status, note=excluded.note, completed_time=excluded.completed_time,
              plan_item_id=excluded.plan_item_id, item_name=excluded.item_name, updated_at=excluded.updated_at
            """,
            (
                checkin_id,
                user["id"],
                log_id,
                plan_version,
                item_key,
                status_value,
                body.get("note"),
                completed_time,
                body.get("plan_item_id"),
                body.get("item_name"),
                date,
                now,
                now,
            ),
        )
        row = dict(conn.execute("SELECT * FROM server_exercise_checkins WHERE id=?", (checkin_id,)).fetchone())
        items = [dict(item) for item in conn.execute(
            "SELECT id,day_key,variant,section,sort_order,name,sets,intensity,color,tags_json FROM server_exercise_plan_items WHERE user_id=? AND plan_version=? AND day_key=? AND is_active=1 ORDER BY variant,sort_order",
            (user["id"], plan_version, _exercise_day_key(date)),
        ).fetchall()]
        definition = _exercise_plan_definition(conn, user["id"], plan_version)
        score = _exercise_score(items, [dict(item) for item in conn.execute("SELECT * FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=?", (user["id"], date, plan_version)).fetchall()], definition, _exercise_day_key(date), date)
        if plan_version == "v4":
            score = _exercise_v4().settle(conn, user["id"], date, _beijing_now())
        else:
            _persist_exercise_item_scores(conn, user["id"], date, plan_version, score, now)
        _exercise_write_change(conn, user["id"], "exercise_checkin", checkin_id, row)
        conn.commit()
    sync_hub._notify_clients(["exercise_checkins", "exercise_item_scores", "exercise_settlements", "exercise_daily_logs", "reward_ledger", "user_wallets"], user["id"])
    return {"status": "ok", "checkin": row, "score": score}


@app.post("/api/exercise/daily")
async def post_exercise_daily(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date") or _beijing_today()
    if date == _beijing_today() and _beijing_now().hour >= 9:
        _lock_overdue_body_metrics()
    day_name = body.get("day_name") or _exercise_day_key(date)
    if date < _beijing_today():
        raise HTTPException(status_code=409, detail="Historical exercise score is locked")
    plan_version = body.get("plan_version") or "v0"
    now = _exercise_now_str()
    log_id = f"server-exercise-{user['id']}-{date}-{plan_version}-daily"
    weight = body.get("weight")
    if weight is not None:
        if date != _beijing_today():
            raise HTTPException(status_code=409, detail="体重只能在北京时间当天录入")
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="体重必须是有效数字")
        if not 30 <= weight <= 200:
            raise HTTPException(status_code=422, detail="体重必须在 30-200 公斤之间")
    body_fat_rate = body.get("body_fat_rate")
    if body_fat_rate is not None:
        try:
            body_fat_rate = float(body_fat_rate)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="体脂率必须是有效数字")
        if not 3 <= body_fat_rate <= 75:
            raise HTTPException(status_code=422, detail="体脂率必须在 3-75% 之间")
    score_snapshot = body.get("score_snapshot")
    score_json = json.dumps(score_snapshot, ensure_ascii=False, sort_keys=True) if score_snapshot is not None else None
    with _exercise_conn() as conn:
        body_metric_lock = _body_metric_lock_in_txn(conn, user["id"], date, plan_version)
        if body_metric_lock:
            if weight is None and body_fat_rate is None:
                raise HTTPException(status_code=409, detail="体重和体脂率已于北京时间 09:00 超时锁定，只能补录有效身体数据")
            conn.execute(
                """UPDATE server_exercise_daily_logs
                   SET weight=COALESCE(?, weight), body_fat_rate=COALESCE(?, body_fat_rate), updated_at=?
                   WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'""",
                (weight, body_fat_rate, now, user["id"], date, plan_version),
            )
            row = dict(conn.execute(
                """SELECT * FROM server_exercise_daily_logs
                   WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'""",
                (user["id"], date, plan_version),
            ).fetchone())
            _exercise_write_change(conn, user["id"], "exercise_daily_log", row["id"], row)
            if plan_version == "v4":
                _exercise_v4().settle(conn, user["id"], date, _beijing_now())
            conn.commit()
            sync_hub._notify_clients(["exercise_daily_logs", "exercise_deadline_facts", "exercise_item_scores", "exercise_settlements", "reward_ledger", "user_wallets"], user["id"])
            return {"status": "ok", "daily_log": row}
        conn.execute(
            """
            INSERT INTO server_exercise_daily_logs
              (id, user_id, date, plan_version, exercise_type, week_num, day_name, weight, body_fat_rate,
               completed_items, total_items, score_snapshot, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'daily', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date, plan_version, exercise_type) DO UPDATE SET
              day_name=excluded.day_name,
              weight=COALESCE(excluded.weight, server_exercise_daily_logs.weight),
              body_fat_rate=COALESCE(excluded.body_fat_rate, server_exercise_daily_logs.body_fat_rate),
              completed_items=excluded.completed_items,
              total_items=excluded.total_items,
              score_snapshot=COALESCE(excluded.score_snapshot, server_exercise_daily_logs.score_snapshot),
              updated_at=excluded.updated_at
            """,
            (
                log_id,
                user["id"],
                date,
                plan_version,
                int(body.get("week_num") or 1),
                day_name,
                weight,
                body_fat_rate,
                int(body.get("completed_items") or 0),
                int(body.get("total_items") or 0),
                score_json,
                now,
                now,
            ),
        )
        row = dict(conn.execute(
            """
            SELECT * FROM server_exercise_daily_logs
            WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'
            """,
            (user["id"], date, plan_version),
        ).fetchone())
        _exercise_write_change(conn, user["id"], "exercise_daily_log", row["id"], row)
        score = _exercise_v4().settle(conn, user["id"], date, _beijing_now()) if plan_version == "v4" else None
        conn.commit()
    if plan_version == "v4":
        sync_hub._notify_clients(["exercise_daily_logs", "exercise_deadline_facts", "exercise_item_scores", "exercise_settlements", "reward_ledger", "user_wallets"], user["id"])
    return {"status": "ok", "daily_log": row, "score": score}


@app.post("/upload")
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    force: bool = False,
    full: bool = False,
    analyze: bool = True,
    date: str | None = None,
    user: dict = Depends(get_current_user_optional),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are accepted")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large")

    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    _cleanup_stale_temp_upload_images()
    request_id = uuid.uuid4().hex
    safe_name = "".join(c for c in (file.filename or "upload.jpg") if c.isalnum() or c in ".-_")
    # 路径修正：现在 analyzer.py 在 server/ 子目录下，skills 在根目录
    root_dir = os.path.dirname(os.path.dirname(__file__))
    skill_dir = os.path.join(root_dir, "skills", "time-management")
    image_path = os.path.join(ATTACHMENTS_DIR, f"{request_id}_{safe_name}")

    logger.info(f"📤 Upload received: {file.filename} -> {request_id} (User: {user['username']}, Force: {force}, Full: {full}, Analyze: {analyze}, Date: {date})")

    image_hash = _hash_bytes(content)
    if analyze and not force:
        cached_job = store.get_done_job_by_image_hash(image_hash, user["id"])
        if cached_job:
            cached_date = cached_job.get("date")
            if date and cached_date and cached_date != date:
                detail = f"日期不匹配！截图日期是 {cached_date}，而当前处理日期是 {date}。请确认是否选错了图。"
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "date_mismatch",
                        "message": detail,
                        "actual_date": cached_date,
                        "expected_date": date,
                    },
                )
            logger.info(
                "♻️ 上传图片 hash 命中已完成结果: user_id=%s request_id=%s image_hash=%s",
                user["id"],
                cached_job.get("request_id"),
                image_hash,
            )
            return {"status": "ok", "request_id": cached_job["request_id"], "reused": True, "cache_reason": "image_hash"}

    with open(image_path, "wb") as out:
        out.write(content)
    store.create_job(request_id, image_path, user_id=user["id"], date=date, image_hash=image_hash)
    if not analyze:
        logger.info("📎 图片已上传，开始日期校验但不生成报告: user_id=%s request_id=%s date=%s image_path=%s", user["id"], request_id, date, image_path)
        background_tasks.add_task(_run_upload_validation, request_id, image_path, user_id=user["id"])
        return {"status": "ok", "request_id": request_id, "uploaded": True, "analyze": False, "date": date}
    background_tasks.add_task(_run_analysis, request_id, image_path, user_id=user["id"], full=full, force_refresh=force)
    return {"status": "ok", "request_id": request_id, "analyze": True}


@app.get("/status/{request_id}")
def get_job_status(request_id: str, user: dict = Depends(get_current_user_optional)):
    job = store.get_job(request_id, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="request_id not found")
    public = _public_job(job)
    latest = progress_latest.get(request_id)
    if latest:
        public["msg"] = latest.get("msg") or public.get("error") or ""
        public["progress"] = latest
    return public


@app.get("/status_by_date/{date}")
def get_job_by_date(date: str, user: dict = Depends(get_current_user_optional)):
    job = store.get_job_by_date(date, user_id=user["id"])
    if not job:
        # 降级容错：如果 job 表未查到当前用户的 job，但底层 SQLite/MySQL 中存在该日期的睡眠核心记录，
        # 则构造虚拟已完成 job，防止多端同步/刷新后因 job 隔离而错误锁定日记
        if store:
            try:
                db_data = store.get_huawei_sleep_data(user["id"], date)
                if db_data:
                    virtual_job = {
                        "request_id": f"virtual_{date}",
                        "date": date,
                        "status": "done",
                        "updated_at": db_data.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "error": None,
                        "sleep_data": db_data
                    }
                    return _public_job(virtual_job)
            except Exception as e:
                logger.error(f"从底层数据库回填虚拟 job 失败: {e}")
        raise HTTPException(status_code=404, detail="date not found")
    return _public_job(job)


@app.get("/events/{request_id}")
async def events(request_id: str, request: Request, user: dict = Depends(get_current_user_optional)):
    if not store.get_job(request_id, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="request_id not found")
    q = _queue_for(request_id)

    async def event_stream():
        while True:
            if await request.is_disconnected():
                break
            try:
                item = q.get_nowait()
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get("status") in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: :heartbeat\n\n"
                await asyncio.sleep(10)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/sync_data")
def sync_data(since: str = "", user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "data": store.list_done_since(since or None, user_id=user["id"])}


@app.get("/api/sleep/field_mapping")
def get_sleep_field_mapping(user: dict = Depends(get_current_user_optional)):
    return {
        "status": "ok",
        "fields": sleep_field_mapping(),
        "core_fields": [
            "sleep_score", "total_sleep_min", "deep_sleep_min", "light_sleep_min",
            "rem_sleep_min", "awake_count", "sleep_start", "sleep_end",
            "deep_sleep_ratio", "light_sleep_ratio", "rem_sleep_ratio",
            "sleep_continuity", "breathing_score",
        ],
        "source_fields": ["source", "synced_at", "sync_status", "sync_error"],
    }


@app.post("/api/sleep/structured")
async def import_structured_sleep_data(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    payload = body.get("payload") or body.get("data")
    source = body.get("source") or SleepDataSource.HUAWEI_USER_IMPORT.value
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload is required")

    try:
        normalized = normalize_structured_sleep_payload(payload, date_str=date, source=source)
        valid, reason = SleepAnalyzer.validate_data(normalized)
        if not valid:
            store.mark_huawei_sleep_sync_error(
                user["id"], normalized.get("date") or date, normalized.get("source"), reason
            )
            raise HTTPException(status_code=400, detail=reason)
        store.save_huawei_sleep_data(user["id"], normalized["date"], normalized)
        return {"status": "ok", "date": normalized["date"], "data": normalized}
    except HTTPException:
        raise
    except ValueError as exc:
        if date:
            store.mark_huawei_sleep_sync_error(user["id"], date, source, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ack_sync")
async def ack_sync(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    request_ids = body.get("request_ids", [])
    return {"status": "ok", "acked": store.ack_sync(request_ids, user_id=user["id"])}


@app.get("/recent")
def recent(limit: int = 10, user: dict = Depends(get_current_user_optional)):
    """
    获取当前用户最近 N 条已完成的睡眠分析记录。

    Query params:
        limit: 返回条数，默认 10

    Returns:
        {"status": "ok", "data": [...]}，每条记录经 _public_job() 格式化
    """
    logger.info(f"📜 Fetching recent {limit} records for user: {user['username']}")
    # 通过 store.list_recent() 获取 request_id 列表，再逐条查询完整 job 数据
    # 这样可以复用 _public_job() 的格式化逻辑，避免在路由层直接操作数据库
    items = store.list_recent(limit=limit, user_id=user["id"])
    results = []
    for item in items:
        job = store.get_job(item["request_id"], user_id=user["id"])
        if job:
            results.append(_public_job(job))
    return {"status": "ok", "data": results}


@app.post("/morning_diary")
async def save_morning_diary(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    text = body.get("text", "")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    if not store.save_morning_diary(date, text, user_id=user["id"]):
        logger.warning(f"⚠️ Failed to save morning diary for {user['username']} on {date}")
        raise HTTPException(status_code=500, detail="Failed to save morning diary")
    sync_hub._notify_clients(["huawei_sleep_data"], user["id"])
    logger.info(f"📝 Morning diary saved for {user['username']} on {date}")
    return {"status": "ok"}


@app.post("/evening_diary")
async def save_evening_diary(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    text = body.get("text", "")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    if not store.save_evening_diary(date, text, user_id=user["id"]):
        logger.warning(f"⚠️ Failed to save evening diary for {user['username']} on {date}")
        raise HTTPException(status_code=500, detail="Failed to save evening diary")
    sync_hub._notify_clients(["huawei_sleep_data"], user["id"])
    logger.info(f"🌙 Evening diary saved for {user['username']} on {date}")
    return {"status": "ok"}


@app.post("/generate_report")
async def generate_report(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    full = body.get("full", True)
    force = body.get("force", False)
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"📄 {'Full' if full else 'Quick'} report generation requested for {user['username']} on {date} (Force: {force})")
    logger.info(
        "[sleep-report] generate_report request user_id=%s username=%s date=%s full=%s force=%s",
        user["id"],
        user.get("username"),
        date,
        full,
        force,
    )

    # 查找当天的任务（如果有）
    job = store.get_job_by_date(date, user_id=user["id"])
    image_path = job.get("image_path") if job else None
    request_id = uuid.uuid4().hex if force else (job.get("request_id") if job else uuid.uuid4().hex)
    structured_data = store.get_huawei_sleep_data(user["id"], date)
    has_valid_structured_data = False
    if structured_data and structured_data.get("source") != SleepDataSource.SCREENSHOT_OCR.value:
        has_valid_structured_data = SleepAnalyzer.validate_data(structured_data)[0]
    logger.info(
        "[sleep-report] generate_report source check user_id=%s date=%s has_job=%s has_image=%s structured=%s structured_valid=%s",
        user["id"],
        date,
        bool(job),
        bool(image_path and os.path.exists(image_path)),
        bool(structured_data),
        has_valid_structured_data,
    )

    # 强制刷新表示重新拉取 aTimeLogger 并重建报告；已有结构化睡眠数据时不强迫重新 OCR。
    if not has_valid_structured_data and (not image_path or not os.path.exists(image_path)):
        backup_name = f"sleep_{date}.jpg"
        backup_path = os.path.join(ATTACHMENTS_DIR, backup_name)
        if os.path.exists(backup_path):
            image_path = backup_path
            # 更新已存在 job 里的图片路径
            if job:
                try:
                    conn = store._connect()
                    conn.execute(
                        "UPDATE server_sleep_jobs SET image_path=? WHERE request_id=?",
                        (backup_path, job["request_id"])
                    )
                    conn.commit()
                    conn.close()
                    logger.info(f"🔄 已将备份图片关联至现有 Job: {backup_path}")
                except Exception as se:
                    logger.error(f"更新 job 图片路径失败: {se}")
        else:
            logger.warning(
                "[sleep-report] generate_report missing_source user_id=%s date=%s request_id=%s",
                user["id"],
                date,
                request_id,
            )
            raise HTTPException(
                status_code=400,
                detail="未找到该日期的结构化睡眠数据或睡眠备份截图，请先同步数据或重新上传图片进行分析。"
            )

    can_reuse_report = _can_reuse_sleep_report(job, full=full, force=force)
    if can_reuse_report:
        logger.info(
            "♻️ 复用同日完整睡眠报告: user_id=%s date=%s request_id=%s",
            user["id"],
            date,
            job.get("request_id"),
        )
        logger.info("[sleep-report] generate_report reused user_id=%s date=%s request_id=%s", user["id"], date, job.get("request_id"))
        return {"status": "ok", "msg": "Reused existing analysis report", "request_id": job["request_id"], "reused": True, "cache_reason": "date_report"}

    if not job or force:
        # 如果没有任务，或者需要强制刷新，则重置/创建该任务并关联图片路径
        store.create_job(request_id, image_path, user_id=user["id"], date=date)

    # 在独立线程中运行同步分析函数，避免阻塞 asyncio 事件循环
    # _run_analysis 是同步函数（含阻塞 IO），必须通过 to_thread 卸载到线程池
    asyncio.create_task(asyncio.to_thread(_run_analysis, request_id, image_path, user["id"], full, force))
    logger.info(
        "[sleep-report] generate_report queued user_id=%s date=%s request_id=%s full=%s force=%s image_path=%s",
        user["id"],
        date,
        request_id,
        full,
        force,
        image_path,
    )

    return {"status": "ok", "msg": "Analysis started in background", "request_id": request_id}


# --- 1. 分类管理 (Categories) ---
@app.get("/api/categories")
def get_categories(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "categories": store.list_categories(user["id"])}

@app.post("/api/categories")
async def create_category(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    name = body.get("name")
    group_name = body.get("group_name")
    icon = body.get("icon")
    color = body.get("color")
    if not name or not group_name:
        raise HTTPException(status_code=400, detail="name and group_name are required")

    cid = store.create_category(user["id"], name, group_name, icon, color)
    if cid is None:
        raise HTTPException(status_code=400, detail="Category name already exists for this user")
    time_logger_db.reload_category_cache()
    return {"status": "ok", "category_id": cid}

@app.put("/api/categories/{category_id}")
async def update_category(category_id: int, request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    name = body.get("name")
    group_name = body.get("group_name")
    icon = body.get("icon")
    color = body.get("color")

    success = store.update_category(user["id"], category_id, name, group_name, icon, color)
    if not success:
        raise HTTPException(status_code=404, detail="Category not found or update conflict")
    time_logger_db.reload_category_cache()
    return {"status": "ok"}

@app.delete("/api/categories/{category_id}")
def delete_category(category_id: int, user: dict = Depends(get_current_user_optional)):
    success = store.delete_category(user["id"], category_id)
    if not success:
        raise HTTPException(status_code=404, detail="Category not found")
    time_logger_db.reload_category_cache()
    return {"status": "ok"}


# --- 2. 专注会话管理 (Sessions) ---
@app.get("/api/sessions")
def get_sessions(
    date: str | None = None,
    since: str | None = None,
    limit: int | None = None,
    user: dict = Depends(get_current_user_optional)
):
    sessions = store.list_study_sessions(user["id"], date_str=date, since=since, limit=limit)
    return {"status": "ok", "sessions": sessions}

@app.post("/api/sessions")
async def create_session(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    start_time = body.get("start_time")
    end_time = body.get("end_time")
    net_duration_minutes = body.get("net_duration_minutes")
    date_val = body.get("date")
    day_of_week = body.get("day_of_week")
    pause_count = body.get("pause_count", 0)
    pause_reasons = body.get("pause_reasons")
    session_summary = body.get("session_summary")
    category_id = body.get("category_id")

    if not start_time or not end_time or net_duration_minutes is None or not date_val:
        raise HTTPException(status_code=400, detail="start_time, end_time, net_duration_minutes, and date are required")

    conn = store._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        sid = store.create_study_session(
            user["id"], start_time, end_time, net_duration_minutes, date_val,
            day_of_week=day_of_week, pause_count=pause_count,
            pause_reasons=pause_reasons, session_summary=session_summary,
            category_id=category_id, conn=conn,
        )
        _write_study_session_change(conn, int(user["id"]), sid, "upsert")
        conn.commit()
        return {"status": "ok", "session_id": sid}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _write_study_session_change(conn: sqlite3.Connection, user_id: int, session_id: str, operation: str) -> None:
    ServerDBWrapper(store.db_path).write_server_change(
        user_id, "study_session", str(session_id), operation, {"id": str(session_id)},
        change_id=f"server-api:study-session:{session_id}:{operation}",
        device_id="server-api", table_name="server_study_sessions", conn=conn,
    )


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, user: dict = Depends(get_current_user_optional)):
    conn = store._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT 1 FROM server_study_sessions WHERE user_id=? AND id=?",
            (int(user["id"]), session_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        ATimeLoggerBackupStore.delete_in_tx(
            conn, int(user["id"]), session_id, beijing_text()
        )
        conn.execute(
            "DELETE FROM server_study_sessions WHERE user_id=? AND id=?",
            (int(user["id"]), session_id),
        )
        _write_study_session_change(conn, int(user["id"]), session_id, "delete")
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@app.get("/api/sessions/today_summary")
def get_today_summary(date: str, user: dict = Depends(get_current_user_optional)):
    summary = store.get_today_group_summary(user["id"], date)
    return {"status": "ok", "summary": summary}

# --- 3. 习惯管理 (Habits) ---
@app.get("/api/habits")
def get_habits(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "habits": store.list_habits(user["id"])}

@app.post("/api/habits")
async def create_habit(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    name = body.get("name")
    icon = body.get("icon")
    difficulty = body.get("difficulty", "medium")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    hid = store.create_habit(user["id"], name, icon, difficulty)
    if hid is None:
        raise HTTPException(status_code=400, detail="Habit name already exists for this user")
    return {"status": "ok", "habit_id": hid}

@app.put("/api/habits/{habit_id}")
async def update_habit(habit_id: str, request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    name = body.get("name")
    icon = body.get("icon")
    difficulty = body.get("difficulty")
    is_active = body.get("is_active")
    success = store.update_habit(user["id"], habit_id, name, icon, difficulty, is_active)
    if not success:
        raise HTTPException(status_code=404, detail="Habit not found or update conflict")
    return {"status": "ok"}

@app.get("/api/habits/today_checkins")
def get_today_checkins(date: str, user: dict = Depends(get_current_user_optional)):
    checkins = store.list_today_checkins(user["id"], date)
    return {"status": "ok", "checkins": checkins}


async def _execute_habit_checkin_command(user_id: int, body: dict) -> dict:
    habit_id = str(body.get("habit_id") or "").strip()
    checkin_date = str(body.get("date") or "").strip()
    idempotency_key = str(body.get("idempotency_key") or "").strip()
    desired_status = body.get("desired_status")
    if not habit_id or not checkin_date or not idempotency_key or not isinstance(desired_status, int) or desired_status not in {0, 1, 2}:
        return {"status": "failed", "error_code": "validation_error", "idempotency_key": idempotency_key}
    if habit_id.startswith("local_"):
        result = await habit_checkin_command_service.execute(
            user_id, idempotency_key, habit_id, checkin_date, desired_status
        )
    else:
        settings = _ticktick_task_settings(user_id)
        if not settings.enabled:
            result = await habit_checkin_command_service.execute(
                user_id, idempotency_key, habit_id, checkin_date, desired_status
            )
        else:
            async with TickTickClient(
                settings.access_token, settings.host, settings.verify_tls, settings.timeout_seconds, request_id=idempotency_key
            ) as client:
                result = await habit_checkin_command_service.execute(
                    user_id, idempotency_key, habit_id, checkin_date, desired_status, client
                )
    if result and result.get("status") == "confirmed":
        sync_hub._notify_clients(["habit_checkins", "reward_fragments", "reward_ledger", "user_wallets", "rewards"], user_id)
    return result or {"status": "failed", "error_code": "command_not_found", "idempotency_key": idempotency_key}


@app.post("/api/habits/checkin-commands")
async def command_habit_checkin(request: Request, user: dict = Depends(get_current_user)):
    return await _execute_habit_checkin_command(int(user["id"]), await request.json())


@app.get("/api/habits/checkin-commands/{idempotency_key}")
def get_habit_checkin_command(idempotency_key: str, user: dict = Depends(get_current_user)):
    command = habit_checkin_command_store.get(int(user["id"]), idempotency_key)
    if not command:
        raise HTTPException(status_code=404, detail="习惯打卡命令不存在")
    return command


@app.post("/api/habits/checkin-commands/{idempotency_key}/retry")
async def retry_habit_checkin_command(idempotency_key: str, user: dict = Depends(get_current_user)):
    command = habit_checkin_command_store.get(int(user["id"]), idempotency_key)
    if not command:
        raise HTTPException(status_code=404, detail="习惯打卡命令不存在")
    return await _execute_habit_checkin_command(int(user["id"]), {
        "habit_id": command["habit_id"],
        "date": command["checkin_date"],
        "desired_status": int(command["desired_status"]),
        "idempotency_key": idempotency_key,
    })

@app.post("/api/habits/{habit_id}/checkin")
async def checkin_habit(habit_id: str, request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    success = store.checkin_habit(user["id"], habit_id, date)
    if not success:
        raise HTTPException(status_code=400, detail="Habit checkin failed or already checked in")
    sync_hub._notify_clients(["habit_checkins", "reward_fragments", "reward_ledger", "user_wallets", "rewards"], user["id"])
    return {"status": "ok"}

@app.delete("/api/habits/{habit_id}/checkin")
def cancel_checkin_habit(habit_id: str, date: str, user: dict = Depends(get_current_user_optional)):
    try:
        success = store.cancel_checkin_habit(user["id"], habit_id, date)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not success:
        raise HTTPException(status_code=400, detail="Cancel checkin failed (checkin not found)")
    sync_hub._notify_clients(["habit_checkins", "reward_fragments", "reward_ledger", "user_wallets", "rewards"], user["id"])
    return {"status": "ok"}

# --- 4. 目标挑战 (Goals) ---
@app.get("/api/goals")
def get_goals(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "goals": store.list_goals(user["id"])}

@app.post("/api/goals")
async def create_goal(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    title = body.get("title")
    category_id = body.get("category_id")
    category_ids = body.get("category_ids")
    metric = body.get("metric")
    target_value = body.get("target_value")
    period = body.get("period")
    reward_coins = body.get("reward_coins")
    operator = body.get("operator", ">=")
    penalty_coins = body.get("penalty_coins")

    if not title or metric not in {"duration", "count"} or period not in {"daily", "weekly", "monthly", "per_session"}:
        raise HTTPException(status_code=400, detail="title, metric, and period are invalid")
    if operator not in {">=", "<="} or target_value is None or reward_coins is None:
        raise HTTPException(status_code=400, detail="title, metric, target_value, period, and reward_coins are required")
    if category_ids is None:
        category_ids = [] if category_id is None else [category_id]
    if not isinstance(category_ids, list) or len({str(value) for value in category_ids}) != len(category_ids):
        raise HTTPException(status_code=400, detail="分类必须为不重复的列表")
    try:
        if float(target_value) <= 0 or float(reward_coins) < 0 or (penalty_coins is not None and float(penalty_coins) < 0):
            raise ValueError
        gid = store.create_goal(
            user["id"], title.strip(), category_id, metric, float(target_value), period,
            float(reward_coins), operator=operator, penalty_coins=penalty_coins, category_ids=category_ids
        )
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="目标数值必须有效且奖励/惩罚不可为负")
    sync_hub._notify_clients(["goals", "goal_category_bindings"], user["id"])
    return {"status": "ok", "goal_id": gid}

@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: str, user: dict = Depends(get_current_user_optional)):
    success = store.delete_goal(user["id"], goal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Goal not found")
    sync_hub._notify_clients(["goals", "goal_category_bindings"], user["id"])
    return {"status": "ok"}

@app.put("/api/goals/{goal_id}")
async def update_goal(goal_id: str, request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    body.pop("reward_id", None)
    if "category_ids" in body:
        category_ids = body["category_ids"]
        if not isinstance(category_ids, list) or len({str(value) for value in category_ids}) != len(category_ids):
            raise HTTPException(status_code=400, detail="分类必须为不重复的列表")
    if "metric" in body and body["metric"] not in {"duration", "count"}:
        raise HTTPException(status_code=400, detail="metric is invalid")
    if "period" in body and body["period"] not in {"daily", "weekly", "monthly", "per_session"}:
        raise HTTPException(status_code=400, detail="period is invalid")
    if "operator" in body and body["operator"] not in {">=", "<="}:
        raise HTTPException(status_code=400, detail="operator is invalid")
    success = store.update_goal(user["id"], goal_id, **body)
    if not success:
        raise HTTPException(status_code=404, detail="Goal not found")
    sync_hub._notify_clients(["goals", "goal_category_bindings"], user["id"])
    return {"status": "ok"}


@app.post("/api/goals/auto_settle")
def auto_settle_goals(user: dict = Depends(get_current_user_optional)):
    settled = store.auto_settle_goals(user["id"])
    if settled:
        sync_hub._notify_clients(["goals", "external_rewards", "reward_ledger", "user_wallets"], user["id"])
    return {"status": "ok", "settled": settled}

# --- 5. 奖励商品与商店 (Rewards) ---
@app.get("/api/rewards")
def get_rewards(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "rewards": store.list_rewards(user["id"])}


@app.get("/api/rewards/source/{source_type}/{source_id}")
def get_source_reward(source_type: str, source_id: str, user: dict = Depends(get_current_user_optional)):
    try:
        return {"status": "ok", **source_reward_service.summary(user["id"], source_type, source_id)}
    except SourceRewardError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@app.post("/api/rewards/source/{source_type}/{source_id}/bindings/{reward_id}")
def bind_source_reward(source_type: str, source_id: str, reward_id: str, user: dict = Depends(get_current_user_optional)):
    try:
        store.bind_reward_source(user["id"], reward_id, source_type, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sync_hub._notify_clients(["rewards", "reward_source_bindings"], user["id"])
    return {"status": "ok"}


@app.delete("/api/rewards/source/{source_type}/{source_id}/bindings/{reward_id}")
def unbind_source_reward(source_type: str, source_id: str, reward_id: str, user: dict = Depends(get_current_user_optional)):
    try:
        success = store.unbind_reward_source(user["id"], reward_id, source_type, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="来源奖励绑定不存在")
    sync_hub._notify_clients(["reward_source_bindings"], user["id"])
    return {"status": "ok"}

@app.post("/api/rewards")
async def create_reward(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    title = body.get("title")
    icon = body.get("icon", "🎁")
    price = body.get("price")
    description = body.get("description")
    unlock_task_id = body.get("unlock_task_id")
    unlock_task_title = body.get("unlock_task_title")
    unlock_source_type = body.get("unlock_source_type")
    unlock_source_id = body.get("unlock_source_id")
    inventory_mode = body.get("inventory_mode", "unlimited")
    inventory_limit = body.get("inventory_limit")
    unlock_required_count = body.get("unlock_required_count", 1)
    redemption_mode = body.get("redemption_mode", "coins")
    fulfillment_mode = body.get("fulfillment_mode")
    fragment_target_count = body.get("fragment_target_count")

    if not title or price is None:
        raise HTTPException(status_code=400, detail="title and price are required")
    try:
        if unlock_task_id or unlock_source_type or unlock_source_id:
            raise ValueError("商品页不再设置来源绑定，请在任务、习惯或学习目标的奖励界面操作")
        price = float(price)
        if price < 0 or ((unlock_task_id or unlock_source_type or unlock_source_id) and price != 0):
            raise ValueError
        rid = store.create_reward(user["id"], title.strip(), icon, price, description, unlock_task_id, unlock_task_title, unlock_source_type, unlock_source_id, inventory_mode, inventory_limit, unlock_required_count, redemption_mode, fulfillment_mode, fragment_target_count)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "奖励配置无效")
    sync_hub._notify_clients(["rewards"], user["id"])
    return {"status": "ok", "reward_id": rid}

@app.put("/api/rewards/{reward_id}")
async def update_reward(reward_id: str, request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    title = body.get("title")
    icon = body.get("icon")
    price = body.get("price")
    description = body.get("description")
    is_active = body.get("is_active")
    unlock_fields = {}
    if "unlock_task_id" in body:
        unlock_fields["unlock_task_id"] = body["unlock_task_id"]
    if "unlock_task_title" in body:
        unlock_fields["unlock_task_title"] = body["unlock_task_title"]
    if "unlock_source_type" in body:
        unlock_fields["unlock_source_type"] = body["unlock_source_type"]
    if "unlock_source_id" in body:
        unlock_fields["unlock_source_id"] = body["unlock_source_id"]
    for field in ("inventory_mode", "inventory_limit", "unlock_required_count", "fulfillment_mode", "fragment_target_count"):
        if field in body:
            unlock_fields[field] = body[field]
    if "redemption_mode" in body:
        unlock_fields["redemption_mode"] = body["redemption_mode"]
    try:
        if any(key in unlock_fields for key in ("unlock_task_id", "unlock_source_type", "unlock_source_id")):
            raise ValueError("商品页不再设置来源绑定，请在任务、习惯或学习目标的奖励界面操作")
        if price is not None:
            price = float(price)
            if price < 0 or (any(key in unlock_fields for key in ("unlock_task_id", "unlock_source_type", "unlock_source_id")) and price != 0):
                raise ValueError("解锁型奖励价格必须为 0")
        success = store.update_reward(user["id"], reward_id, title, icon, price, description, is_active, **unlock_fields)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "奖励配置无效")
    if not success:
        raise HTTPException(status_code=404, detail="Reward item not found")
    sync_hub._notify_clients(["rewards"], user["id"])
    return {"status": "ok"}

@app.delete("/api/rewards/{reward_id}")
def delete_reward(reward_id: str, user: dict = Depends(get_current_user_optional)):
    success = store.delete_reward(user["id"], reward_id)
    if not success:
        raise HTTPException(status_code=404, detail="Reward item not found")
    sync_hub._notify_clients(["rewards"], user["id"])
    return {"status": "ok"}

@app.get("/api/rewards/balance")
def get_reward_balance(user: dict = Depends(get_current_user_optional)):
    balance = store.get_gold_balance(user["id"])
    return {"status": "ok", "balance": balance}

@app.get("/api/rewards/ledger")
def get_reward_ledger(limit: int = 30, user: dict = Depends(get_current_user_optional)):
    ledger = store.list_ledger(user["id"], limit)
    return {"status": "ok", "ledger": ledger}

@app.post("/api/rewards/buy/{reward_id}")
async def buy_reward(reward_id: str, request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json() if request.headers.get("content-length") not in (None, "0") else {}
    success, msg = store.buy_reward(user["id"], reward_id, body.get("amount"), body.get("note"))
    if not success:
        raise HTTPException(status_code=409 if msg == "商品库存已用完" else 400, detail=msg)
    sync_hub._notify_clients(["reward_ledger", "user_wallets"], user["id"])
    return {"status": "ok", "msg": msg}

@app.get("/api/rewards/unclaimed")
def get_unclaimed_rewards(user: dict = Depends(get_current_user_optional)):
    unclaimed = store.list_unclaimed_rewards(user["id"])
    return {"status": "ok", "unclaimed": unclaimed}

@app.post("/api/rewards/claim")
async def claim_rewards(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    ids = body.get("ids", [])
    total_claimed = store.claim_rewards(user["id"], ids)
    if total_claimed:
        sync_hub._notify_clients(["external_rewards", "reward_ledger", "user_wallets"], user["id"])
    return {"status": "ok", "total_claimed": total_claimed}

@app.get("/api/rewards/backpack")
def get_backpack(user: dict = Depends(get_current_user_optional)):
    backpack = store.list_backpack(user["id"])
    fragments = store.reward_wallet_service.list_backpack_fragments(user["id"])
    return {"status": "ok", "backpack": backpack, "fragments": fragments}

@app.get("/api/rewards/backpack/events")
def get_backpack_events(limit: int = 50, offset: int = 0, user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "events": store.list_backpack_events(user["id"], limit, offset)}

@app.get("/api/rewards/backpack/audit-preview")
def preview_backpack_audit(user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "preview": store.preview_invalid_backpack_items(user["id"])}

@app.post("/api/rewards/backpack/audit-confirm")
async def confirm_backpack_audit(request: Request, user: dict = Depends(get_current_user_optional)):
    summary_hash = (await request.json()).get("summary_hash", "")
    try:
        removed = store.clean_invalid_backpack_items(user["id"], summary_hash)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    sync_hub._notify_clients(["reward_ledger", "user_wallets"], user["id"])
    return {"status": "ok", "removed": removed}

@app.post("/api/rewards/use_item/{ledger_id}")
def use_backpack_item(ledger_id: str, user: dict = Depends(get_current_user_optional)):
    success, msg = store.use_backpack_item(user["id"], ledger_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    sync_hub._notify_clients(["reward_ledger", "user_wallets"], user["id"])
    return {"status": "ok", "msg": msg}

@app.post("/api/rewards/backpack/{ledger_id}/discard")
def discard_backpack_item(ledger_id: str, user: dict = Depends(get_current_user_optional)):
    success, msg = store.discard_backpack_item(user["id"], ledger_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    sync_hub._notify_clients(["reward_ledger", "user_wallets"], user["id"])
    return {"status": "ok", "msg": msg}

@app.post("/api/rewards/reset")
def reset_rewards(user: dict = Depends(get_current_user_optional)):
    store.reset_coins(user["id"])
    return {"status": "ok"}

@app.post("/api/rewards/ledger")
async def add_ledger_entry(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    amount = body.get("amount")
    source_type = body.get("source_type")
    source_id = body.get("source_id")
    description = body.get("description", "")
    if amount is None or not source_type:
        raise HTTPException(status_code=400, detail="amount and source_type are required")
    success = store.add_ledger_entry(user["id"], amount, source_type, source_id, description)
    return {"status": "ok" if success else "error"}

@app.post("/api/rewards/external")
async def add_external_reward(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    ext_id = body.get("ext_id")
    item_type = body.get("item_type")
    item_name = body.get("item_name")
    coins = body.get("coins")
    status = body.get("status", 0)
    if not ext_id or not item_type or not item_name or coins is None:
        raise HTTPException(status_code=400, detail="ext_id, item_type, item_name, and coins are required")
    success = store.add_external_reward(user["id"], ext_id, item_type, item_name, coins, status)
    return {"status": "ok" if success else "error"}

@app.get("/api/rewards/config/{item_type}/{item_id}")
def get_item_reward_config(item_type: str, item_id: str, user: dict = Depends(get_current_user_optional)):
    res = store.get_item_reward(user["id"], item_type, item_id)
    if not res:
        raise HTTPException(status_code=404, detail={"code": "reward_config_missing", "message": "奖励配置不存在"})
    return {"status": "ok", "coins": res["coins"], "penalty": res["penalty"]}

@app.post("/api/rewards/config")
async def set_item_reward_config(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    item_type = body.get("item_type")
    item_id = body.get("item_id")
    coins = body.get("coins")
    penalty = body.get("penalty")
    if not item_type or not item_id or coins is None:
        raise HTTPException(status_code=400, detail="item_type, item_id, and coins are required")
    success = store.set_item_reward(user["id"], item_type, item_id, coins, penalty)
    return {"status": "ok" if success else "error"}


# --- 6. 睡眠数据管理 (Sleep Data) ---
@app.get("/api/sleep/data/{date}")
def get_sleep_data(date: str, user: dict = Depends(get_current_user_optional)):
    data = store.get_huawei_sleep_data(user["id"], date)
    if not data:
        raise HTTPException(status_code=404, detail="Sleep data not found for date")
    return {"status": "ok", "sleep_data": data}

@app.post("/api/sleep/data")
async def save_sleep_data(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    data = body.get("data", {})
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    store.save_huawei_sleep_data(user["id"], date, data)
    return {"status": "ok"}

@app.get("/api/sleep/history")
def get_sleep_history(limit: int = 14, user: dict = Depends(get_current_user_optional)):
    history = store.get_sleep_history(user["id"], limit)
    return {"status": "ok", "history": history}


# --- 7. 任务清单管理 (Tasks) ---
@app.get("/api/tasks")
def get_active_tasks(user: dict = Depends(get_current_user_optional)):
    tasks = store.list_active_tasks(user["id"])
    return {"status": "ok", "tasks": tasks}

@app.post("/api/tasks")
async def upsert_task(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    task_dict = body.get("task")
    if not task_dict:
        raise HTTPException(status_code=400, detail="task object is required")
    success = store.upsert_task(user["id"], task_dict)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to upsert task")
    return {"status": "ok"}

@app.put("/api/tasks/{task_id}/status")
async def update_task_status(task_id: str, request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    status = body.get("status", 0)
    success = store.update_task_status(user["id"], task_id, status)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok"}


# --- 8. aTimeLogger 数据管理 (ATM Data) ---
@app.get("/api/atm/data/{date}")
def get_atm_data(date: str, user: dict = Depends(get_current_user_optional)):
    data = store.get_atm_data(user["id"], date)
    if not data:
        raise HTTPException(status_code=404, detail="ATM data not found")
    return {"status": "ok", "atm_data": data}

@app.post("/api/atm/data")
async def save_atm_data(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    data = body.get("data")
    if not date or data is None:
        raise HTTPException(status_code=400, detail="date and data are required")
    store.save_atm_data(user["id"], date, data)
    return {"status": "ok"}


# 旧版 sync/pull 路由（已被下方 async 版本取代，此处移除以避免重复定义报错）


@app.post("/api/sync/push")
async def sync_push(request: Request, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user_optional)):
    """客户端批量推送变更 → SyncHub LWW 仲裁 → 写入 SQLite"""
    request_id = (
        getattr(getattr(request, "state", None), "request_id", None)
        or request.headers.get("x-sync-run-id")
        or request.headers.get("x-request-id")
        or uuid.uuid4().hex
    )
    started = time.perf_counter()
    body = await request.json()
    operations = body.get("operations", [])
    sync_scope = "checklist" if body.get("sync_scope") == "checklist" else "core"
    operation_counts: dict[str, int] = {}
    for operation in operations:
        table = operation.get("table") or "unknown"
        records = operation.get("records")
        operation_counts[table] = operation_counts.get(table, 0) + (
            len(records) if isinstance(records, list) else 1
        )
    logger.info(
        "[sync_push] start request_id=%s user_id=%s scope=%s operations=%s operation_counts=%s",
        request_id,
        user.get("id"),
        sync_scope,
        len(operations),
        operation_counts,
    )
    try:
        if not operations:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info("[sync_push] finish request_id=%s accepted=0 changed_tables=[] elapsed_ms=%s", request_id, elapsed_ms)
            return {"status": "ok", "accepted": 0, "server_time": _now_str(), "diagnostics": {
                "scope": sync_scope, "provider_requested": False, "provider_executed": False,
            }}
        result = await sync_hub.handle_push(operations, user_id=user["id"], sync_scope=sync_scope)
        for card_id in result.get("analysis_claims", []):
            background_tasks.add_task(_process_synced_flash_card, int(user["id"]), card_id)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "[sync_push] finish request_id=%s accepted=%s rejected=%s changed_tables=%s elapsed_ms=%s",
            request_id,
            result.get("accepted"),
            len(result.get("rejected", [])),
            result.get("changed_tables", []),
            elapsed_ms,
        )
        return {
            "status": "ok",
            "accepted": result["accepted"],
            "server_time": result["server_time"],
            "changed_tables": result.get("changed_tables", []),
            "rejected": result.get("rejected", []),
            "operation_results": result.get("operation_results", []),
            "diagnostics": {
                "scope": sync_scope,
                "provider_requested": result.get("provider_requested", False),
                "provider_executed": result.get("provider_executed", False),
                "provider_blocked": result.get("provider_blocked", 0),
            },
        }
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception("[sync_push] failed request_id=%s elapsed_ms=%s", request_id, elapsed_ms)
        raise


@app.get("/api/sync/pull")
async def sync_pull(
    request: Request,
    since: str = None,
    refresh: bool = False,
    provider_manual: bool = False,
    sync_scope: str = "core",
    since_version: int | None = None,
    limit: int = 500,
    ledger_snapshot: bool = False,
    include_diagnostics: bool = True,
    user: dict = Depends(get_current_user_optional),
):
    """客户端增量拉取 → SyncHub 返回 since 以来变更"""
    request_id = (
        getattr(getattr(request, "state", None), "request_id", None)
        or request.headers.get("x-sync-run-id")
        or request.headers.get("x-request-id")
        or uuid.uuid4().hex
    )
    started = time.perf_counter()
    scope = "checklist" if sync_scope == "checklist" else "core"
    provider_requested = bool(refresh)
    provider_executed = False
    auth_header = request.headers.get("authorization") or ""
    token_value = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    logger.info(
        "[sync_pull] start request_id=%s user_id=%s scope=%s refresh=%s since_version=%s since=%s limit=%s include_diagnostics=%s token_present=%s token_length=%s",
        request_id,
        user.get("id"),
        scope,
        refresh,
        since_version,
        since,
        limit,
        include_diagnostics,
        bool(token_value),
        len(token_value),
    )
    diagnostics = None
    try:
        if refresh and scope == "checklist":
            provider_executed = True
            if provider_manual:
                diagnostics = await sync_hub.force_pull_ticktick(user_id=user["id"], request_id=request_id, manual=True)
            else:
                diagnostics = await sync_hub.force_pull_ticktick(user_id=user["id"], request_id=request_id)
            since = None
        if since_version is not None:
            if ledger_snapshot:
                result = await sync_hub.handle_pull_by_version(
                    since_version, user_id=user["id"], limit=limit, request_id=request_id,
                    include_ledger_snapshot=True,
                )
            else:
                result = await sync_hub.handle_pull_by_version(since_version, user_id=user["id"], limit=limit, request_id=request_id)
            merged_diagnostics = result.get("diagnostics") or {}
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            merged_diagnostics["request_id"] = request_id
            merged_diagnostics["elapsed_ms"] = elapsed_ms
            merged_diagnostics.update({
                "scope": scope, "provider_requested": provider_requested,
                "provider_executed": provider_executed,
                "provider_blocked": int(provider_requested and not provider_executed),
            })
            if diagnostics:
                merged_diagnostics["provider_refresh"] = diagnostics
            logger.info(
                "[sync_pull] finish request_id=%s protocol=server_version from_version=%s to_version=%s has_more=%s table_counts=%s elapsed_ms=%s",
                request_id,
                result.get("from_version"),
                result.get("to_version"),
                result.get("has_more"),
                _sync_table_counts(result.get("tables")),
                elapsed_ms,
            )
            return {
                "status": "ok",
                "changes": result["changes"],
                "tables": result.get("tables", {}),
                "from_version": result["from_version"],
                "to_version": result["to_version"],
                "has_more": result["has_more"],
                "server_time": result["server_time"],
                "wallet": result.get("wallet"),
                "ledger_snapshot": result.get("ledger_snapshot"),
                "diagnostics": merged_diagnostics if include_diagnostics else None,
                "sync_state": result.get("sync_state"),
            }
        result = await sync_hub.handle_pull(since, user_id=user["id"], request_id=request_id)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        legacy_diagnostics = {
            "protocol": "legacy_timestamp",
            "reason": "timestamp_since_compatibility",
            "request_id": request_id,
            "elapsed_ms": elapsed_ms,
            "scope": scope,
            "provider_requested": provider_requested,
            "provider_executed": provider_executed,
            "provider_blocked": int(provider_requested and not provider_executed),
        }
        if diagnostics:
            legacy_diagnostics["provider_refresh"] = diagnostics
        logger.info(
            "[sync_pull] finish request_id=%s protocol=legacy_timestamp table_counts=%s elapsed_ms=%s",
            request_id,
            _sync_table_counts(result.get("tables")),
            elapsed_ms,
        )
        return {
            "status": "ok",
            "tables": result["tables"],
            "wallet": result.get("wallet"),
            "server_time": result["server_time"],
            "diagnostics": legacy_diagnostics if include_diagnostics else diagnostics,
            "sync_state": result.get("sync_state"),
        }
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception("[sync_pull] failed request_id=%s elapsed_ms=%s", request_id, elapsed_ms)
        raise


# 保留旧端点兼容性
@app.get("/api/sync")
async def sync_all_data_legacy(request: Request, since: str = None, user: dict = Depends(get_current_user_optional)):
    return await sync_pull(request=request, since=since, user=user)


# ======================== SSE 实时推送 ========================

@app.get("/api/timer/current/capability")
async def timer_state_capability(user: dict = Depends(get_current_user_optional)):
    return {
        "status": "ok",
        "capability": TIMER_STATE_CAPABILITY,
        "enforced": True,
        "minimum_client": TIMER_STATE_CAPABILITY,
    }


@app.get("/api/timer/current")
async def read_timer_state(request: Request, user: dict = Depends(get_current_user_optional)):
    _require_timer_state_capability(request)
    return _live_timer_service().read(int(user["id"]))


@app.post("/api/timer/current/{operation}")
async def update_timer_state(operation: str, request: Request, user: dict = Depends(get_current_user_optional)):
    _require_timer_state_capability(request)
    if operation not in {"start", "switch", "note", "pause", "resume", "stop"}:
        raise HTTPException(status_code=404, detail="未知计时操作")
    body = await request.json()
    required = ("device_id", "observed_revision", "idempotency_key", "user_intent_id")
    if any(key not in body or (key != "observed_revision" and not str(body.get(key, "")).strip()) for key in required):
        raise HTTPException(status_code=400, detail="缺少当前计时字段")
    if operation in {"start", "switch"} and not str(body.get("category_name", "")).strip():
        raise HTTPException(status_code=400, detail="缺少计时分类")
    if operation == "note" and "current_note" not in body:
        raise HTTPException(status_code=400, detail="缺少当前计时备注")
    payload = {key: body.get(key) for key in (
        "session_id", "device_id", "observed_revision", "idempotency_key", "user_intent_id",
        "command_seq", "category_id", "category_name", "timer_mode", "duration_ms",
        "session_summary", "current_note",
    )}
    result = _live_timer_service().command(int(user["id"]), operation, payload)
    if result.get("status") == "accepted":
        sync_hub.notify_timer_state(int(user["id"]), result["revision"])
        if result.get("completed_session_id"):
            sync_hub.notify_completed_session(int(user["id"]))
    logger.info("timer_state %s", redact_timer_lease_event({
        "user": int(user["id"]), "session": (result.get("state") or {}).get("session_id"),
        "completed_session": result.get("completed_session_id"),
        "intent": payload["user_intent_id"], "operation": operation,
        "revision": result.get("revision"),
        "result": result.get("status"), "errorCode": result.get("error_code"),
    }))
    return _lease_response(result)


# 旧 owner-lease 协议明确要求升级，避免旧客户端继续渲染只读卡。
@app.api_route("/api/timer/lease/{path:path}", methods=["GET", "POST"])
async def retired_timer_lease(path: str):
    raise HTTPException(status_code=426, detail=f"timer-lease-v1 已停用，请升级到 {TIMER_STATE_CAPABILITY}")


@app.get("/api/sync/events")
async def sync_events(request: Request, user: dict = Depends(get_current_user_optional)):
    """SSE 端点：服务端主动推送变更通知给客户端"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=32)
    sync_hub.subscribe(queue, int(user["id"]))

    async def event_stream():
        try:
            yield "data: connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_INTERVAL_SEC)
                    yield f"event: {msg['event']}\ndata: {msg['data']}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            sync_hub.unsubscribe(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ======================== 锁管理机制 ========================

LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.lock")

def release_lock():
    """释放互斥锁"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("🗑️ Server lock file released.")
    except Exception as e:
        logger.error(f"Failed to release lock file: {e}")

def acquire_lock():
    """获取锁，防止多实例并发导致端口冲突或数据库损坏"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.readline().strip())

            if psutil.pid_exists(old_pid):
                logger.error(f"❌ 启动失败: 服务端已在运行 (PID: {old_pid})")
                sys.exit(1)
            else:
                logger.warning(f"⚠️ 发现残留的锁文件 (旧进程 PID {old_pid} 已死亡)，正在清理...")
                os.remove(LOCK_FILE)
        except Exception as e:
            logger.warning(f"⚠️ 无法读取或清理旧锁文件: {e}，尝试强制覆盖。")

    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(f"{os.getpid()}\npython\nSERVER\n{uuid.uuid4()}\n")
        logger.info(f"🔒 Server lock acquired (PID: {os.getpid()}).")
    except Exception as e:
        logger.error(f"Failed to write lock file: {e}")
        sys.exit(1)

    atexit.register(release_lock)
    try:
        signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))
        signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    except Exception as e:
        logger.warning(f"Failed to register signal handlers: {e}")


if __name__ == "__main__":
    acquire_lock()
    # 直接运行时的本地启动逻辑
    port = int(server_config.get_runtime("port", 8000) or 8000)
    print(f"🚀 MyTimeLogger Server 启动中...")
    print(f"🔗 访问地址: http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
