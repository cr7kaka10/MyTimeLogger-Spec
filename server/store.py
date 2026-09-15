# -*- coding: utf-8 -*-
"""SQLite buffer store for server sleep analysis jobs."""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


try:
    from .atm_versioning import save_versioned_atm_data
    from .security_utils import hash_bearer_token
    from .sync_sql_allowlist import SYNC_TABLES, SERVER_TABLES, client_table_for_server, ensure_server_table, server_table_for
    from .time_utils import normalize_task_record_for_db, now_bj
    from .domain.habit_service import HabitDomainService
    from .domain.reward_rule_service import RewardRuleService
    from .domain.reward_config_service import RewardConfigService
    from .domain.reward_settlement_service import RewardSettlementService
    from .domain.reward_wallet_service import RewardWalletService
    from .domain.sleep_reward_service import SleepRewardService
    from .statistics_start_date import get_user_statistics_start_date, is_statistics_date_eligible
except (ImportError, ValueError):
    from atm_versioning import save_versioned_atm_data
    from security_utils import hash_bearer_token
    from sync_sql_allowlist import SYNC_TABLES, SERVER_TABLES, client_table_for_server, ensure_server_table, server_table_for
    from time_utils import normalize_task_record_for_db, now_bj
    from domain.habit_service import HabitDomainService
    from domain.reward_rule_service import RewardRuleService
    from domain.reward_config_service import RewardConfigService
    from domain.reward_settlement_service import RewardSettlementService
    from domain.reward_wallet_service import RewardWalletService
    from domain.sleep_reward_service import SleepRewardService
    from statistics_start_date import get_user_statistics_start_date, is_statistics_date_eligible


DONE_STATUSES = {"done"}
UNSET = object()


import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta



def now_str():
    return now_bj()


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}:{pw_hash}"


def verify_password(password, stored_hash):
    if ":" not in stored_hash:
        return False
    salt, _ = stored_hash.split(":", 1)
    return hash_password(password, salt) == stored_hash


def resolve_server_db_path(db_path=None):
    """Return the canonical absolute server database path."""
    if db_path:
        candidate = os.fspath(db_path)
        source = "db_path"
    else:
        candidate = os.getenv("SERVER_SLEEP_DB_PATH")
        source = "SERVER_SLEEP_DB_PATH"
        # Ignore a Docker-only path inherited by a native Windows process.
        if candidate and os.name == "nt" and candidate.startswith("/app"):
            candidate = None

    if candidate:
        if not os.path.isabs(candidate):
            raise ValueError(f"{source} must be an absolute path")
        return os.path.abspath(candidate)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "mtl_server.db"))


class ServerSleepStore:
    _TABLE_MAP = {table: server_table_for(table) for table in SYNC_TABLES}

    def __init__(self, db_path=None):
        self.db_path = resolve_server_db_path(db_path)
        self._initialize()
        # 调用链路：server.py 路由/SyncHub -> ServerSleepStore 旧门面 -> domain service -> SQLite。
        # 这些 service 先承接金币、钱包、习惯取消等高风险业务，剩余 CRUD 后续再逐步迁移。
        self.reward_wallet_service = RewardWalletService(
            self._connect, self._transact, now_str, self._update_wallet_in_txn, self._record_server_change
        )
        self.reward_settlement_service = RewardSettlementService(
            self._transact, now_str, self.reward_wallet_service, self._record_server_change
        )
        self.reward_rule_service = RewardRuleService(now_str, self.get_item_reward)
        self.sleep_reward_service = SleepRewardService(
            self._transact, now_str, self.reward_wallet_service, self._record_server_change,
        )
        self.sleep_reward_service.migrate_effective_date_diary_rewards()
        self.sleep_reward_service.reconcile_unreported_scores()
        self.habit_domain_service = HabitDomainService(
            self._transact, now_str, self.reward_wallet_service, self.reward_settlement_service,
            self.reward_rule_service, self._record_server_change,
        )

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _transact(self):
        """银行级事务管理器：保证业务操作+流水+钱包快照的原子性。
        用法：
            with self._transact() as conn:
                conn.execute(...)  # 业务操作
                conn.execute(...)  # 流水记录
                self._update_wallet_in_txn(conn, user_id, amount)  # 钱包更新
            # 自动 commit；异常时自动 rollback
        """
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _update_wallet_in_txn(self, conn, user_id, amount_change, ledger_uuid=None, amount_already_in_ledger=True):
        """在已有事务连接内更新钱包快照余额（不开新连接、不自行 commit）。
        由调用方的 _transact() 统一 commit/rollback。
        """
        row = conn.execute(
            "SELECT balance FROM server_user_wallets WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        now_ts = now_str()
        if row:
            new_balance = float(row["balance"]) + amount_change
            conn.execute(
                "UPDATE server_user_wallets SET balance = ?, last_ledger_uuid = ?, updated_at = ? WHERE user_id = ?",
                (new_balance, ledger_uuid, now_ts, user_id)
            )
        else:
            # 首次写入：先聚合历史流水再加上本次变动
            ledger_sum = conn.execute(
                "SELECT SUM(amount) as total FROM server_reward_ledger WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            total = float(ledger_sum["total"]) if ledger_sum and ledger_sum["total"] is not None else 0.0
            # 调用链路：业务 service 通常先 INSERT reward_ledger，再调用本函数更新 wallet 快照。
            # 此时 SUM(reward_ledger) 已包含本次 amount，首次建钱包不能再加一遍；兼容旧的直接加余额调用时才补加。
            new_balance = total if amount_already_in_ledger else total + amount_change
            conn.execute(
                "INSERT INTO server_user_wallets (user_id, balance, last_ledger_uuid, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, new_balance, ledger_uuid, now_ts)
            )


    def _initialize(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = self._connect()
        try:
            from server.models.server_schema import ensure_server_schema

            # 检查旧版中的 server_tasks 表是否含有 ticktick_id 列以进行平滑升级
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='server_tasks'")
            table_exists = cursor.fetchone()
            if table_exists:
                info_cur = conn.execute("PRAGMA table_info(server_tasks)")
                cols = {row["name"] for row in info_cur.fetchall()}
                if "ticktick_id" in cols:
                    logger.info("⚙️ Upgrading server_tasks table: removing ticktick_id column...")
                    conn.execute("PRAGMA foreign_keys = OFF")
                    try:
                        conn.execute("ALTER TABLE server_tasks RENAME TO old_server_tasks")
                        ensure_server_schema(conn)
                        # 数据迁移，排除 ticktick_id 列
                        new_cols = [
                            "id", "user_id", "title", "priority", "status", "category_id",
                            "due_date", "tags", "raw_json", "updated_at", "pushed_at"
                        ]
                        col_str = ", ".join(new_cols)
                        conn.execute(f"INSERT INTO server_tasks ({col_str}) SELECT {col_str} FROM old_server_tasks")
                        conn.execute("DROP TABLE old_server_tasks")
                    except Exception:
                        logger.exception("Migration for server_tasks ticktick_id removal failed")
                        raise
                    finally:
                        conn.execute("PRAGMA foreign_keys = ON")

            # Check server_habits for title column
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='server_habits'")
            habits_exists = cursor.fetchone()
            if habits_exists:
                info_cur = conn.execute("PRAGMA table_info(server_habits)")
                cols = {row["name"] for row in info_cur.fetchall()}
                if "title" in cols:
                    logger.info("⚙️ Upgrading server_habits table: removing title column...")
                    conn.execute("PRAGMA foreign_keys = OFF")
                    try:
                        conn.execute("ALTER TABLE server_habits RENAME TO old_server_habits")
                        ensure_server_schema(conn)
                        new_cols = [
                            "id", "user_id", "name", "icon", "color",
                            "sort_order", "category_id", "difficulty", "is_active",
                            "created_at", "updated_at", "pushed_at"
                        ]
                        col_str = ", ".join(new_cols)
                        conn.execute(f"INSERT INTO server_habits ({col_str}) SELECT {col_str} FROM old_server_habits")
                        conn.execute("DROP TABLE old_server_habits")
                    except Exception:
                        logger.exception("Migration for server_habits title removal failed")
                        raise
                    finally:
                        conn.execute("PRAGMA foreign_keys = ON")

            # 初始化所有表结构
            ensure_server_schema(conn)
            conn.commit()
        except Exception:
            logger.exception("Database initialization failed")
            raise
        finally:
            conn.close()


    # --- 用户管理 ---

    def create_user(self, username, password):
        conn = self._connect()
        try:
            pw_hash = hash_password(password)
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, pw_hash, now_str()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def verify_user(self, username, password):
        conn = self._connect()
        try:
            row = conn.execute("SELECT id, password_hash FROM users WHERE username=?", (username,)).fetchone()
            if row and verify_password(password, row["password_hash"]):
                return row["id"]
            return None
        finally:
            conn.close()

    def create_session(self, user_id):
        token = secrets.token_urlsafe(32)
        token_hash = hash_bearer_token(token)
        ts = now_str()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token_hash, user_id, ts, None),
            )
            conn.commit()
            return token
        finally:
            conn.close()

    def get_user_by_session(self, token):
        conn = self._connect()
        try:
            token_hash = hash_bearer_token(token)
            row = conn.execute(
                """
                SELECT u.id, u.username FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND (s.expires_at IS NULL OR s.expires_at > ?)
                """,
                (token_hash, now_str()),
            ).fetchone()
            if not row:
                row = conn.execute(
                    """
                    SELECT u.id, u.username FROM users u
                    JOIN sessions s ON u.id = s.user_id
                    WHERE s.token = ? AND (s.expires_at IS NULL OR s.expires_at > ?)
                    """,
                    (token, now_str()),
                ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def revoke_session(self, token):
        conn = self._connect()
        try:
            token_hash = hash_bearer_token(token)
            conn.execute("DELETE FROM sessions WHERE token IN (?, ?)", (token_hash, token))
            conn.commit()
        finally:
            conn.close()

    def cleanup_expired_sessions(self):
        conn = self._connect()
        try:
            conn.execute("DELETE FROM sessions WHERE expires_at IS NOT NULL AND expires_at <= ?", (now_str(),))
            conn.commit()
        finally:
            conn.close()

    def get_default_user_id(self):
        """获取第一个用户，用于 Legacy 模式"""
        conn = self._connect()
        try:
            row = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
            return row["id"] if row else None
        finally:
            conn.close()

    # --- 钱包金币资产管理 ---

    def get_user_wallet_balance(self, user_id: int) -> float:
        # 调用链路：REST/内部任务 -> store 门面 -> RewardWalletService -> wallet 快照；缺失快照时由 ledger 重建。
        return self.reward_wallet_service.get_user_wallet_balance(user_id)

    def update_user_wallet_balance(self, user_id: int, amount_change: float, ledger_uuid: str = None) -> float:
        # 调用链路：兼容旧调用 -> RewardWalletService -> 同事务更新 server_user_wallets。
        return self.reward_wallet_service.update_user_wallet_balance(user_id, amount_change, ledger_uuid)

    def rebuild_wallet_snapshot(self, user_id: int) -> dict:
        # 调用链路：诊断/测试 -> store 门面 -> RewardWalletService -> SUM(reward_ledger) -> UPSERT(wallet)。
        return self.reward_wallet_service.rebuild_wallet_snapshot(user_id)

    def verify_wallet_consistency(self, user_id: int) -> dict:
        # 调用链路：诊断/测试 -> store 门面 -> RewardWalletService -> 对比 ledger 汇总与 wallet 快照。
        return self.reward_wallet_service.verify_wallet_consistency(user_id)

    # --- 任务管理 ---

    def create_job(self, request_id, image_path, user_id=None, date=None, image_hash=None):
        """
        创建一条新的睡眠分析 job 记录，初始状态为 'queued'。

        Args:
            request_id: 唯一标识符（uuid4().hex 生成的 32 位十六进制字符串）
            image_path: 上传图片的本地存储路径
            user_id: 关联用户 ID，Legacy 模式下可为 None
            date: 可选的日期字符串（YYYY-MM-DD），由 /generate_report 端点传入；
                  /upload 端点不传此参数，日期由分析完成后的 mark_done() 写入
            image_hash: 上传图片内容的 SHA-256，用于同用户同图复用
        """
        ts = now_str()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO server_sleep_jobs
                (request_id, user_id, date, status, image_path, image_hash, result_json, analysis_report, error, created_at, updated_at, sync_count, acked_at)
                VALUES (?, ?, ?, 'queued', ?, ?, NULL, NULL, NULL, ?, ?, 0, NULL)
                """,
                (request_id, user_id, date, image_path, image_hash, ts, ts),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_running(self, request_id):
        """
        将指定 job 的状态更新为 'running'，清空 error 字段。

        Args:
            request_id: 要更新的 job 唯一标识符

        操作表：server_sleep_jobs，按 request_id 匹配
        """
        self._update_status(request_id, "running", error=None)

    def mark_error(self, request_id, error):
        """
        将指定 job 的状态更新为 'error'，并记录错误信息。

        Args:
            request_id: 要更新的 job 唯一标识符
            error: 错误描述字符串，会被转换为 str 后存入 error 字段

        操作表：server_sleep_jobs，按 request_id 匹配
        """
        self._update_status(request_id, "error", error=str(error))

    def mark_done(self, request_id, date, result_json, analysis_report):
        """
        将指定 job 标记为完成，写入分析结果和日期。

        Args:
            request_id: 要更新的 job 唯一标识符
            date: 分析得出的睡眠日期字符串（YYYY-MM-DD），由 analyzer 解析图片后确定
            result_json: 睡眠数据字典或 JSON 字符串；若为 dict 则自动序列化
            analysis_report: 完整分析报告的 Markdown 文本；快速分析时传空字符串

        操作表：server_sleep_jobs，按 request_id 匹配，同时更新 date、result_json、
                analysis_report、error（清空）、updated_at 字段
        """
        final_data = result_json if isinstance(result_json, dict) else None
        if not isinstance(result_json, str):
            result_json = json.dumps(result_json or {}, ensure_ascii=False)
        conn = self._connect()
        try:
            if final_data and analysis_report and final_data.get("analysis_html") and int(final_data.get("report_status") or 0) >= 2:
                owner = conn.execute("SELECT user_id FROM server_sleep_jobs WHERE request_id=?", (request_id,)).fetchone()
                row = conn.execute(
                    "SELECT id FROM server_huawei_sleep_data WHERE user_id=? AND date=?",
                    (owner["user_id"], date),
                ).fetchone() if owner and owner["user_id"] is not None else None
                if not row:
                    raise RuntimeError("final_report_sync_row_missing")
                conn.execute(
                    "UPDATE server_huawei_sleep_data SET analysis_report=?, analysis_html=?, updated_at=? WHERE id=?",
                    (analysis_report, final_data["analysis_html"], now_str(), row["id"]),
                )
                self._record_server_change(conn, owner["user_id"], "huawei_sleep_data", row["id"], "upsert", {"date": date})
            conn.execute(
                """
                UPDATE server_sleep_jobs
                SET status='done', date=?, result_json=?, analysis_report=?, error=NULL, updated_at=?
                WHERE request_id=?
                """,
                (date, result_json, analysis_report or "", now_str(), request_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _update_status(self, request_id, status, error=None):
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE server_sleep_jobs SET status=?, error=?, updated_at=? WHERE request_id=?",
                (status, error, now_str(), request_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_job(self, request_id, user_id=None):
        """
        按 request_id 查询单条 job 记录。

        Args:
            request_id: job 的唯一标识符
            user_id: 用户 ID 过滤。外部 HTTP 请求必须传入，确保数据隔离；
                     内部调用（如 _run_analysis 线程）可传 None，此时走 Legacy 模式
                     不做用户过滤（仅限服务内部可信调用路径）。

        Returns:
            包含完整字段的 dict（含解析后的 sleep_data），未找到时返回 None

        操作表：server_sleep_jobs，按 request_id（+ 可选 user_id）匹配

        安全说明：
            所有来自外部 HTTP 路由的调用必须传入 user_id（server.py 中已全部传入）。
            user_id=None 仅允许服务内部可信调用路径使用，不得暴露给外部请求。
        """
        if user_id is None:
            import traceback
            caller = ''.join(traceback.format_stack(limit=3)[-2:-1]).strip()
            logger.warning(f"get_job called without user_id (Legacy mode). caller={caller[:120]}")
        conn = self._connect()
        try:
            if user_id is not None:
                row = conn.execute("SELECT * FROM server_sleep_jobs WHERE request_id=? AND user_id=?", (request_id, user_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM server_sleep_jobs WHERE request_id=?", (request_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def get_job_by_date(self, date, user_id):
        """
        按日期查询指定用户最新的已完成 job 记录。

        Args:
            date: 睡眠日期字符串（YYYY-MM-DD）
            user_id: 用户 ID，必填，用于数据隔离

        Returns:
            包含完整字段的 dict（含解析后的 sleep_data），未找到时返回 None

        操作表：server_sleep_jobs，按 date + user_id 过滤，取 updated_at 最新的一条
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM server_sleep_jobs WHERE date=? AND user_id=? AND status='done' ORDER BY updated_at DESC LIMIT 1",
                (date, user_id),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def get_done_job_by_image_hash(self, image_hash, user_id):
        """
        按同用户同图片 hash 查询最近完成 job。只返回 done，避免复用失败或运行中结果。
        """
        if not image_hash or user_id is None:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM server_sleep_jobs
                WHERE image_hash=? AND user_id=? AND status='done'
                ORDER BY updated_at DESC LIMIT 1
                """,
                (image_hash, user_id),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def mark_reused_from_job(self, request_id, source_job, image_path=None, image_hash=None):
        """
        将当前 job 标记为复用已有完成结果，保留本次上传 hash/path 便于审计。
        """
        result_json = json.dumps(source_job.get("sleep_data") or {}, ensure_ascii=False)
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE server_sleep_jobs
                SET status='reused', date=?, image_path=COALESCE(?, image_path),
                    image_hash=COALESCE(?, image_hash), result_json=?,
                    analysis_report=?, error=NULL, updated_at=?
                WHERE request_id=?
                """,
                (
                    source_job.get("date"),
                    image_path,
                    image_hash,
                    result_json,
                    source_job.get("analysis_report") or "",
                    now_str(),
                    request_id,
                ),
            )
            if image_hash and source_job.get("request_id"):
                conn.execute(
                    """
                    UPDATE server_sleep_jobs
                    SET image_hash=COALESCE(image_hash, ?), image_path=COALESCE(image_path, ?)
                    WHERE request_id=?
                    """,
                    (image_hash, image_path, source_job["request_id"]),
                )
            conn.commit()
        finally:
            conn.close()

    def list_done_since(self, since=None, user_id=None):
        """
        增量拉取已完成的 job 记录，用于客户端数据同步。

        Args:
            since: 可选的时间戳字符串（YYYY-MM-DD HH:MM:SS）；传入时只返回
                   updated_at 晚于该时间的记录，不传则返回全部已完成记录
            user_id: 可选的用户 ID 过滤；传入时只返回属于该用户的记录

        Returns:
            list of dict，每条记录为 _row_to_sync_item 格式（含 request_id、date、
            updated_at、sleep_data、analysis_report），按 updated_at 升序排列

        操作表：server_sleep_jobs，status='done'，可选 updated_at > since 和 user_id 过滤
        """
        conn = self._connect()
        try:
            query = "SELECT * FROM server_sleep_jobs WHERE status='done'"
            params = []
            if since:
                query += " AND updated_at > ?"
                params.append(since)
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY updated_at ASC"
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_sync_item(row) for row in rows]
        finally:
            conn.close()

    def ack_sync(self, request_ids, user_id=None):
        """
        确认客户端已同步的记录，递增 sync_count。

        Args:
            request_ids: 已同步的 request_id 列表
            user_id: 当前用户 ID。传入时只更新属于该用户的记录，
                     防止恶意用户通过猜测 request_id 污染其他用户的 sync_count。

        Returns:
            实际更新的记录数
        """
        if not request_ids:
            return 0
        ts = now_str()
        conn = self._connect()
        try:
            count = 0
            for request_id in request_ids:
                if user_id is not None:
                    # 带 user_id 过滤，防止跨用户数据污染
                    cur = conn.execute(
                        """
                        UPDATE server_sleep_jobs
                        SET sync_count=COALESCE(sync_count, 0) + 1, acked_at=?, updated_at=updated_at
                        WHERE request_id=? AND user_id=?
                        """,
                        (ts, request_id, user_id),
                    )
                else:
                    # Legacy 模式（无用户认证）：不过滤 user_id
                    cur = conn.execute(
                        """
                        UPDATE server_sleep_jobs
                        SET sync_count=COALESCE(sync_count, 0) + 1, acked_at=?, updated_at=updated_at
                        WHERE request_id=?
                        """,
                        (ts, request_id),
                    )
                count += cur.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def list_recent(self, limit=10, user_id=None):
        """
        获取最近 N 条已完成的 job 记录，按日期和更新时间倒序排列。

        Args:
            limit: 返回的最大记录数，默认 10
            user_id: 可选的用户 ID 过滤；传入时只返回属于该用户的记录

        Returns:
            list of dict，每条记录为 _row_to_sync_item 格式（含 request_id、date、
            updated_at、sleep_data、analysis_report），按 date DESC, updated_at DESC 排列

        操作表：server_sleep_jobs，status='done'，可选 user_id 过滤，LIMIT 限制条数
        """
        conn = self._connect()
        try:
            query = "SELECT * FROM server_sleep_jobs WHERE status='done'"
            params = []
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY date DESC, updated_at DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_sync_item(row) for row in rows]
        finally:
            conn.close()

    def save_reflection(self, date, reflection, user_id=None):
        """
        保存晨间日记到指定日期的 job 记录中。

        日记内容以 sleep_reflection 键存入 result_json 字段（JSON 合并更新）。

        Args:
            date: 目标日期字符串（YYYY-MM-DD）
            reflection: 晨间日记文本内容
            user_id: 可选的用户 ID 过滤；传入时只更新属于该用户的记录

        Returns:
            True 表示保存成功，False 表示未找到对应日期的已完成记录

        操作表：server_sleep_jobs，status='done' + date（+ 可选 user_id）过滤，
                更新 result_json 和 updated_at 字段
        """
    def save_morning_diary(self, date, diary_text, user_id=None):
        """
        保存晨间日记到指定日期的 job 记录中。

        日记内容以 morning_diary 键存入 result_json 字段（JSON 合并更新）。

        Args:
            date: 目标日期字符串（YYYY-MM-DD）
            diary_text: 晨间日记文本内容
            user_id: 可选的用户 ID 过滤；传入时只更新属于该用户的记录

        Returns:
            True 表示保存成功，False 表示操作失败
        """
        conn = self._connect()
        try:
            query = "SELECT * FROM server_sleep_jobs WHERE status='done' AND date=?"
            params = [date]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY updated_at DESC LIMIT 1"
            row = conn.execute(query, tuple(params)).fetchone()

            if not row:
                import uuid
                request_id = uuid.uuid4().hex
                data = {"morning_diary": diary_text, "date": date}
                conn.execute(
                    """
                    INSERT INTO server_sleep_jobs
                    (request_id, user_id, date, status, image_path, result_json, analysis_report, error, created_at, updated_at, sync_count, acked_at)
                    VALUES (?, ?, ?, 'done', NULL, ?, NULL, NULL, ?, ?, 0, NULL)
                    """,
                    (request_id, user_id, date, json.dumps(data, ensure_ascii=False), now_str(), now_str()),
                )
                conn.commit()
                if user_id is not None:
                    self.save_huawei_sleep_data(user_id, date, {
                        "morning_diary": diary_text, "morning_diary_written_at": now_str(),
                    })
                return True

            data = json.loads(row["result_json"] or "{}")
            if "sleep_reflection" in data:
                data["morning_diary"] = data.pop("sleep_reflection")
            data["morning_diary"] = diary_text

            conn.execute(
                """
                UPDATE server_sleep_jobs
                SET result_json=?, updated_at=?
                WHERE request_id=?
                """,
                (json.dumps(data, ensure_ascii=False), now_str(), row["request_id"]),
            )
            conn.commit()
            if user_id is not None:
                self.save_huawei_sleep_data(user_id, date, {
                    "morning_diary": diary_text, "morning_diary_written_at": now_str(),
                })
            return True
        finally:
            conn.close()

    def save_evening_diary(self, date, diary_text, user_id=None):
        """
        保存晚间日记到指定日期的 job 记录中。

        日记内容以 evening_diary 键存入 result_json 字段（JSON 合并更新）。

        Args:
            date: 目标日期字符串（YYYY-MM-DD）
            diary_text: 晚间日记文本内容
            user_id: 可选的用户 ID 过滤；传入时只更新属于该用户的记录

        Returns:
            True 表示保存成功，False 表示操作失败
        """
        conn = self._connect()
        try:
            query = "SELECT * FROM server_sleep_jobs WHERE status='done' AND date=?"
            params = [date]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY updated_at DESC LIMIT 1"
            row = conn.execute(query, tuple(params)).fetchone()

            if not row:
                import uuid
                request_id = uuid.uuid4().hex
                data = {"evening_diary": diary_text, "date": date}
                conn.execute(
                    """
                    INSERT INTO server_sleep_jobs
                    (request_id, user_id, date, status, image_path, result_json, analysis_report, error, created_at, updated_at, sync_count, acked_at)
                    VALUES (?, ?, ?, 'done', NULL, ?, NULL, NULL, ?, ?, 0, NULL)
                    """,
                    (request_id, user_id, date, json.dumps(data, ensure_ascii=False), now_str(), now_str()),
                )
                conn.commit()
                if user_id is not None:
                    self.save_huawei_sleep_data(user_id, date, {
                        "evening_diary": diary_text, "evening_diary_written_at": now_str(),
                    })
                return True

            data = json.loads(row["result_json"] or "{}")
            data["evening_diary"] = diary_text

            conn.execute(
                """
                UPDATE server_sleep_jobs
                SET result_json=?, updated_at=?
                WHERE request_id=?
                """,
                (json.dumps(data, ensure_ascii=False), now_str(), row["request_id"]),
            )
            conn.commit()
            if user_id is not None:
                self.save_huawei_sleep_data(user_id, date, {
                    "evening_diary": diary_text, "evening_diary_written_at": now_str(),
                })
            return True
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row):
        data = dict(row)
        if data.get("result_json"):
            try:
                data["sleep_data"] = json.loads(data["result_json"])
            except Exception:
                data["sleep_data"] = {}
        else:
            data["sleep_data"] = {}
        return data

    def _row_to_sync_item(self, row):
        data = self._row_to_dict(row)
        return {
            "request_id": data["request_id"],
            "date": data["date"],
            "updated_at": data["updated_at"],
            "sleep_data": data["sleep_data"],
            "analysis_report": data.get("analysis_report") or "",
        }

    # ======================== 客户端 API 化与云端数据库迁移新增方法 ========================

    # --- 1. 分类管理 (Categories) ---
    def list_categories(self, user_id):
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM server_categories WHERE user_id=? ORDER BY sort_order ASC", (user_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_category(self, user_id, name, group_name, icon=None, color=None):
        conn = self._connect()
        try:
            # 获取该用户当前最大的 sort_order
            row = conn.execute("SELECT MAX(sort_order) FROM server_categories WHERE user_id = ?", (user_id,)).fetchone()
            next_order = (row[0] or 0) + 1
            
            cursor = conn.execute(
                "INSERT INTO server_categories (user_id, name, group_name, icon, color, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name, group_name, icon, color, next_order)
            )
            self.ensure_management_object_key(conn, user_id, "category", cursor.lastrowid)
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    def update_category(self, user_id, category_id, name=None, group_name=None, icon=None, color=None):
        conn = self._connect()
        try:
            row = conn.execute("SELECT 1 FROM server_categories WHERE id=? AND user_id=?", (category_id, user_id)).fetchone()
            if not row:
                return False

            fields = []
            params = []
            if name is not None:
                fields.append("name=?")
                params.append(name)
            if group_name is not None:
                fields.append("group_name=?")
                params.append(group_name)
            if icon is not None:
                fields.append("icon=?")
                params.append(icon)
            if color is not None:
                fields.append("color=?")
                params.append(color)

            if not fields:
                return True

            query = f"UPDATE server_categories SET {', '.join(fields)} WHERE id=? AND user_id=?"
            params.extend([category_id, user_id])
            conn.execute(query, tuple(params))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def delete_category(self, user_id, category_id):
        conn = self._connect()
        try:
            row = conn.execute("SELECT 1 FROM server_categories WHERE id=? AND user_id=?", (category_id, user_id)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM server_categories WHERE id=? AND user_id=?", (category_id, user_id))
            conn.commit()
            return True
        finally:
            conn.close()

    # --- 2. 专注会话管理 (Sessions) ---
    def list_study_sessions(self, user_id, date_str=None, since=None, limit=None):
        conn = self._connect()
        try:
            query = "SELECT * FROM server_study_sessions WHERE user_id=?"
            params = [user_id]
            if date_str:
                query += " AND date=?"
                params.append(date_str)
            if since:
                query += " AND start_time>=?"
                params.append(since)
            query += " ORDER BY start_time DESC"
            if limit:
                query += " LIMIT ?"
                params.append(int(limit))

            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_study_session(self, user_id, start_time, end_time, net_duration_minutes, date, day_of_week=None, pause_count=0, pause_reasons=None, session_summary=None, category_id=None, conn=None):
        owns_conn = conn is None
        if conn is None:
            conn = self._connect()
        try:
            if category_id is not None:
                cat = conn.execute("SELECT 1 FROM server_categories WHERE id=? AND user_id=?", (category_id, user_id)).fetchone()
                if not cat:
                    raise ValueError("分类不存在或不属于当前账号")

            session_id = uuid.uuid4().hex
            cursor = conn.execute(
                """
                INSERT INTO server_study_sessions
                (id, user_id, start_time, end_time, net_duration_minutes, date, day_of_week, pause_count, pause_reasons, session_summary, category_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, start_time, end_time, net_duration_minutes, date, day_of_week, pause_count, pause_reasons, session_summary, category_id, now_str())
            )
            if owns_conn:
                conn.commit()
            return session_id
        finally:
            if owns_conn:
                conn.close()

    def get_today_group_summary(self, user_id, date_str):
        summary = {"输入": 0, "输出": 0, "生活": 0, "未分类": 0}
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT c.group_name, SUM(s.net_duration_minutes)
                FROM server_study_sessions s
                LEFT JOIN server_categories c ON s.category_id = c.id
                WHERE s.user_id = ? AND s.date = ?
                GROUP BY c.group_name
                """,
                (user_id, date_str),
            )
            rows = cursor.fetchall()
            for row in rows:
                grp = row[0] if row[0] else "未分类"
                mins = int(row[1]) if row[1] else 0
                if grp in summary:
                    summary[grp] = mins
                else:
                    summary["未分类"] += mins
        except Exception as e:
            logger.warning(f"server get_today_group_summary failed: {e}")
        finally:
            conn.close()
        return summary

    # --- 3. 任务清单 (Tasks) ---
    def list_active_tasks(self, user_id):
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM server_tasks WHERE user_id=? AND status=0 ORDER BY priority DESC, updated_at DESC", (user_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def upsert_task(self, user_id, task_dict):
        conn = self._connect()
        try:
            task_id = task_dict.get("id") or task_dict.get("ticktick_id")
            title = task_dict.get("title", "")
            priority = task_dict.get("priority", 0)
            status = task_dict.get("status", 0)
            category_id = task_dict.get("category_id")
            normalized_task = normalize_task_record_for_db(task_dict)
            due_date = normalized_task.get("due_date")
            raw_json = json.dumps(normalized_task, ensure_ascii=False)
            updated_at = now_str()

            # Verify category_id ownership
            if category_id is not None:
                cat = conn.execute("SELECT 1 FROM server_categories WHERE id=? AND user_id=?", (category_id, user_id)).fetchone()
                if not cat:
                    category_id = None

            conn.execute(
                """
                INSERT OR REPLACE INTO server_tasks
                (id, user_id, title, priority, status, category_id, due_date, raw_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, user_id, title, priority, status, category_id, due_date, raw_json, updated_at)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def update_task_status(self, user_id, task_id, status):
        conn = self._connect()
        try:
            row = conn.execute("SELECT 1 FROM server_tasks WHERE id=? AND user_id=?", (task_id, user_id)).fetchone()
            if not row:
                return False
            conn.execute("UPDATE server_tasks SET status=?, updated_at=? WHERE id=? AND user_id=?", (status, now_str(), task_id, user_id))
            conn.commit()
            return True
        finally:
            conn.close()

    # --- 4. 习惯管理 (Habits) ---
    def list_habits(self, user_id):
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM server_habits WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_habit(self, user_id, name, icon=None, difficulty='medium', repeat_rule=None):
        conn = self._connect()
        try:
            habit_id = uuid.uuid4().hex
            cursor = conn.execute(
                "INSERT INTO server_habits (id, user_id, name, icon, difficulty, repeat_rule, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (habit_id, user_id, name, icon, difficulty, repeat_rule, now_str(), now_str())
            )
            RewardConfigService().ensure_item(conn, user_id, "habit", habit_id, difficulty=difficulty)
            conn.commit()
            return habit_id
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    def update_habit(self, user_id, habit_id, name=None, icon=None, difficulty=None, is_active=None, repeat_rule=None):
        conn = self._connect()
        try:
            row = conn.execute("SELECT 1 FROM server_habits WHERE id=? AND user_id=?", (habit_id, user_id)).fetchone()
            if not row:
                return False

            fields = []
            params = []
            if name is not None:
                fields.append("name=?")
                params.append(name)
            if icon is not None:
                fields.append("icon=?")
                params.append(icon)
            if difficulty is not None:
                fields.append("difficulty=?")
                params.append(difficulty)
            if is_active is not None:
                fields.append("is_active=?")
                params.append(is_active)
            if repeat_rule is not None:
                fields.append("repeat_rule=?")
                params.append(repeat_rule)

            if not fields:
                return True

            query = f"UPDATE server_habits SET {', '.join(fields)} WHERE id=? AND user_id=?"
            params.extend([habit_id, user_id])
            conn.execute(query, tuple(params))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()


    def list_today_checkins(self, user_id, date_str):
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM server_habit_checkins WHERE user_id=? AND date=?", (user_id, date_str)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def checkin_habit(self, user_id, habit_id, date_str):
        # 调用链路：POST /api/habits/{id}/checkin -> store 门面 -> HabitDomainService -> checkins/ledger/wallet。
        return self.habit_domain_service.checkin_habit(user_id, habit_id, date_str)

    def cancel_checkin_habit(self, user_id, habit_id, date_str):
        # 调用链路：DELETE /api/habits/{id}/checkin -> store 门面 -> HabitDomainService -> 目标日期撤销。
        return self.habit_domain_service.cancel_checkin_habit(user_id, habit_id, date_str)

    # --- 5. 目标挑战 (Goals) ---
    def list_goals(self, user_id):
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM server_goals WHERE user_id=? AND is_active=1 ORDER BY created_at DESC", (user_id,)).fetchall()
            goals = [dict(r) for r in rows]
            if not goals:
                return goals
            binding_rows = conn.execute(
                "SELECT goal_id, category_id FROM server_goal_category_bindings WHERE user_id=?",
                (user_id,),
            ).fetchall()
            bindings = {}
            for binding in binding_rows:
                bindings.setdefault(binding["goal_id"], []).append(binding["category_id"])
            for goal in goals:
                goal["category_ids"] = bindings.get(goal["id"], [goal["category_id"]] if goal["category_id"] is not None else [])
            return goals
        finally:
            conn.close()

    def _validate_goal_category_ids_in_txn(self, conn, user_id, category_ids, legacy_category_id=None):
        if category_ids is None:
            category_ids = [] if legacy_category_id is None else [legacy_category_id]
        if not isinstance(category_ids, (list, tuple)):
            raise ValueError("分类必须是列表")
        normalized = []
        for category_id in category_ids:
            try:
                value = int(category_id)
            except (TypeError, ValueError):
                raise ValueError("分类无效")
            if value not in normalized:
                normalized.append(value)
        if len(normalized) != len(category_ids):
            raise ValueError("分类不可重复")
        for category_id in normalized:
            if not conn.execute(
                "SELECT 1 FROM server_categories WHERE id=? AND user_id=?", (category_id, user_id)
            ).fetchone():
                raise ValueError("分类不存在或不属于当前账号")
        return normalized

    def _replace_goal_category_bindings_in_txn(self, conn, user_id, goal_id, category_ids, now_ts):
        existing = conn.execute(
            "SELECT id FROM server_goal_category_bindings WHERE user_id=? AND goal_id=?", (user_id, goal_id)
        ).fetchall()
        for row in existing:
            self._record_server_change(conn, user_id, "server_goal_category_bindings", row["id"], "delete", {"id": row["id"]})
        conn.execute("DELETE FROM server_goal_category_bindings WHERE user_id=? AND goal_id=?", (user_id, goal_id))
        for category_id in category_ids:
            binding_id = f"goal-category:{goal_id}:{category_id}"
            conn.execute(
                """
                INSERT INTO server_goal_category_bindings
                    (id, user_id, goal_id, category_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (binding_id, user_id, goal_id, category_id, now_ts, now_ts),
            )
            self._record_server_change(conn, user_id, "server_goal_category_bindings", binding_id, "upsert", {"id": binding_id})

    def create_goal(self, user_id, title, category_id, metric, target_value, period, reward_coins, reward_id=None, operator='>=', penalty_coins=None, category_ids=None):
        with self._transact() as conn:
            if penalty_coins is None:
                penalty_coins = reward_coins
            selected_category_ids = self._validate_goal_category_ids_in_txn(
                conn, user_id, category_ids, category_id
            )
            category_id = selected_category_ids[0] if selected_category_ids else None

            goal_id = uuid.uuid4().hex
            now_ts = now_str()
            conn.execute(
                """
                INSERT INTO server_goals
                (id, user_id, title, category_id, metric, target_value, period, operator, reward_coins, reward_id, penalty_coins, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (goal_id, user_id, title, category_id, metric, target_value, period, operator, reward_coins, None, penalty_coins, now_ts, now_ts)
            )
            self._record_server_change(conn, user_id, "server_goals", goal_id, "upsert", {"id": goal_id})
            self._replace_goal_category_bindings_in_txn(conn, user_id, goal_id, selected_category_ids, now_ts)
            return goal_id
    def delete_goal(self, user_id, goal_id):
        with self._transact() as conn:
            row = conn.execute("SELECT 1 FROM server_goals WHERE id=? AND user_id=?", (goal_id, user_id)).fetchone()
            if not row:
                return False
            conn.execute("UPDATE server_goals SET is_active=0, updated_at=? WHERE id=? AND user_id=?", (now_str(), goal_id, user_id))
            self._record_server_change(conn, user_id, "server_goals", goal_id, "upsert", {"id": goal_id, "is_active": 0})
            return True
    def update_goal(self, user_id, goal_id, **kwargs):
        category_ids = kwargs.pop("category_ids", UNSET)
        kwargs.pop("reward_id", None)
        allowed = {"title", "category_id", "metric", "target_value", "period", "operator", "reward_coins", "penalty_coins"}
        kwargs = {key: value for key, value in kwargs.items() if key in allowed}
        with self._transact() as conn:
            row = conn.execute("SELECT 1 FROM server_goals WHERE id=? AND user_id=?", (goal_id, user_id)).fetchone()
            if not row:
                return False
            if category_ids is not UNSET:
                selected_category_ids = self._validate_goal_category_ids_in_txn(conn, user_id, category_ids)
                kwargs["category_id"] = selected_category_ids[0] if selected_category_ids else None
            elif "category_id" in kwargs:
                selected_category_ids = self._validate_goal_category_ids_in_txn(conn, user_id, [kwargs["category_id"]] if kwargs["category_id"] is not None else [])
            else:
                selected_category_ids = None
            now_ts = now_str()
            if kwargs:
                fields = ", ".join([f"{k} = ?" for k in kwargs.keys()] + ["updated_at = ?"])
                values = list(kwargs.values())
                values.append(now_ts)
                values.extend([goal_id, user_id])
                conn.execute(f"UPDATE server_goals SET {fields} WHERE id = ? AND user_id=?", values)
            self._record_server_change(conn, user_id, "server_goals", goal_id, "upsert", {"id": goal_id})
            if selected_category_ids is not None:
                self._replace_goal_category_bindings_in_txn(conn, user_id, goal_id, selected_category_ids, now_ts)
            return True

    def _completed_goal_windows(self, period, created_at, today):
        """枚举从目标生效日起所有已完整结束的北京时间自然周期。"""
        earliest = date.fromisoformat(str(created_at or "2000-01-01")[:10])
        if period == "daily":
            current = earliest
            while current < today:
                yield current, current
                current += timedelta(days=1)
        elif period == "weekly":
            current = earliest + timedelta(days=(7 - earliest.weekday()) % 7)
            while current + timedelta(days=6) < today:
                yield current, current + timedelta(days=6)
                current += timedelta(days=7)
        elif period == "monthly":
            current = earliest.replace(day=1)
            if current < earliest:
                current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
            while True:
                next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
                end = next_month - timedelta(days=1)
                if end >= today:
                    return
                yield current, end
                current = next_month

    def _remove_goal_claim_in_txn(self, conn, user_id, claim_id):
        """撤销同一目标周期的奖励、入包及其使用流水，供历史会话更正后重建。"""
        purchases = [row["id"] for row in conn.execute(
            "SELECT id FROM server_reward_ledger WHERE user_id=? AND source_type='reward_buy' AND source_id LIKE ?",
            (user_id, f"%:goal:{claim_id}"),
        ).fetchall()]
        uses = [row["id"] for row in conn.execute(
            "SELECT id FROM server_reward_ledger WHERE user_id=? AND source_type='backpack_use' AND source_id IN (" + ",".join("?" for _ in purchases) + ")",
            [user_id, *purchases],
        ).fetchall()] if purchases else []
        ledgers = [row["id"] for row in conn.execute(
            "SELECT id FROM server_reward_ledger WHERE user_id=? AND source_id=?", (user_id, claim_id)
        ).fetchall()]
        self.reward_wallet_service.remove_ledger_entries_in_txn(conn, user_id, uses + purchases + ledgers)
        rewards = conn.execute("SELECT id FROM server_external_rewards WHERE user_id=? AND ext_id=?", (user_id, claim_id)).fetchall()
        conn.execute("DELETE FROM server_external_rewards WHERE user_id=? AND ext_id=?", (user_id, claim_id))
        for row in rewards:
            self._record_server_change(conn, user_id, "server_external_rewards", row["id"], "delete", {"id": row["id"]})

    def auto_settle_goals(self, user_id, rebuild_dates=None):
        """按北京时间补齐已结束周期；指定周期可先撤销后基于当前会话重建。"""
        today = date.fromisoformat(now_str()[:10])
        now_ts = now_str()
        rebuild_dates = {str(value)[:10] for value in (rebuild_dates or [])}

        with self._transact() as conn:
            statistics_start = get_user_statistics_start_date(conn, user_id).date
            goals = conn.execute("SELECT * FROM server_goals WHERE user_id=? AND is_active=1", (user_id,)).fetchall()

            settled_details = []
            for g in goals:
                g_id = g['id']
                title = g['title']
                cat_id = g['category_id']
                category_ids = [row["category_id"] for row in conn.execute(
                    "SELECT category_id FROM server_goal_category_bindings WHERE user_id=? AND goal_id=? ORDER BY category_id",
                    (user_id, g_id),
                ).fetchall()]
                if not category_ids and cat_id is not None:
                    category_ids = [cat_id]
                period = g['period']
                metric = g['metric']
                target = g['target_value']
                operator = g['operator'] or '>='
                reward_coins = g['reward_coins']
                penalty_coins = g['penalty_coins'] if g['penalty_coins'] is not None else reward_coins
                created_at_goal = g['created_at'] or '2000-01-01 00:00:00'

                def _issue_goal(claim_id, is_met, val, target_val, operator_str, date_str, fail_if_not_met=False):
                    if not is_statistics_date_eligible(str(date_str)[:10], statistics_start):
                        return
                    row = conn.execute("SELECT 1 FROM server_external_rewards WHERE ext_id=? AND user_id=?", (claim_id, user_id)).fetchone()
                    if row:
                        return

                    unit = "m" if metric == 'duration' else "次"
                    status_text = "达成" if is_met else "未达标"
                    compat_desc = f"目标{status_text}[{date_str}]: {title} ({int(val)}{unit} / {operator_str}{int(target_val)}{unit})"

                    amount = 0.0
                    if is_met:
                        amount = reward_coins
                    elif fail_if_not_met:
                        amount = -abs(penalty_coins)
                    else:
                        return

                    bound_rewards = []
                    if is_met:
                        bound_rewards = conn.execute(
                            """SELECT id FROM server_rewards
                               WHERE user_id=? AND is_active=1
                                 AND unlock_source_type='goal' AND unlock_source_id=?
                               ORDER BY id""",
                            (user_id, g_id),
                        ).fetchall()

                    if amount != 0 or bound_rewards:
                        r_id = uuid.uuid4().hex
                        conn.execute(
                            """
                            INSERT INTO server_external_rewards (id, ext_id, user_id, item_type, item_name, coins, status, created_at, updated_at)
                            VALUES (?, ?, ?, 'goal', ?, ?, 1, ?, ?)
                            """,
                            (r_id, claim_id, user_id, compat_desc, amount, now_ts, now_ts)
                        )
                        self._record_server_change(conn, user_id, "server_external_rewards", claim_id, "upsert", {"ext_id": claim_id})
                        for reward in bound_rewards:
                            reward_id = str(reward["id"])
                            ledger_id = f"reward_unlock_{reward_id}_{claim_id}"[:180]
                            self.reward_wallet_service.append_ledger_in_txn(
                                conn, user_id, 0, "reward_buy", f"{reward_id}:goal:{claim_id}",
                                f"目标自动解锁兑换: {title}", date_str, ledger_id,
                            )
                            settled_details.append({"claim_id": claim_id, "ledger_id": ledger_id, "description": compat_desc, "amount": 0.0})
                    if amount != 0:
                        source_type = "goal_reward" if amount >= 0 else "goal_penalty"
                        ledger_id = self.reward_settlement_service.settle_in_txn(
                            conn,
                            user_id,
                            amount,
                            "goal",
                            title,
                            source_type,
                            source_id=claim_id,
                            target_date=date_str,
                            success=amount >= 0,
                            occurred_at=f"{date_str} 00:00:00",
                        )
                        self._record_server_change(conn, user_id, "server_reward_ledger", ledger_id, "upsert", {"id": ledger_id})
                        self._record_server_change(conn, user_id, "server_user_wallets", user_id, "upsert", {"user_id": user_id})
                        settled_details.append({"claim_id": claim_id, "ledger_id": ledger_id, "description": compat_desc, "amount": amount})

                last_reset_str = "2026-05-01 00:00:00"

                category_sql = " AND category_id IS NULL" if not category_ids else f" AND category_id IN ({','.join('?' for _ in category_ids)})"

                if period == 'per_session':
                    sessions = conn.execute(
                        """SELECT id, net_duration_minutes, start_time, end_time FROM server_study_sessions
                           WHERE user_id=? AND end_time IS NOT NULL
                             AND substr(end_time,1,10)>=? AND substr(end_time,1,10)<=? AND start_time>?""" + category_sql,
                        (user_id, statistics_start, today.strftime('%Y-%m-%d'), last_reset_str, *category_ids)
                    ).fetchall()

                    for s in sessions:
                        if s["start_time"] < created_at_goal:
                            continue
                        is_met = (s["net_duration_minutes"] >= target) if operator == '>=' else (s["net_duration_minutes"] <= target)
                        _issue_goal(
                            f"goal_{g_id}_session_{s['id']}",
                            is_met, s["net_duration_minutes"], target, operator, s["end_time"][:10],
                            fail_if_not_met=True
                        )

                elif period in {'daily', 'weekly', 'monthly'}:
                    effective_start = max(created_at_goal[:10], last_reset_str[:10])
                    for start, end in self._completed_goal_windows(period, effective_start, today):
                        start_str, end_str = start.isoformat(), end.isoformat()
                        if start_str < statistics_start:
                            continue
                        # 日目标归属当日，周/月目标归属完整周期的最后一天。
                        period_end_date = end_str

                        if metric == 'duration':
                            val = conn.execute(
                                "SELECT SUM(net_duration_minutes) FROM server_study_sessions WHERE user_id=? AND date BETWEEN ? AND ?" + category_sql,
                                (user_id, start_str, end_str, *category_ids)
                            ).fetchone()[0] or 0.0
                        else:
                            val = conn.execute(
                                "SELECT COUNT(*) FROM server_study_sessions WHERE user_id=? AND date BETWEEN ? AND ?" + category_sql,
                                (user_id, start_str, end_str, *category_ids)
                            ).fetchone()[0] or 0

                        is_met = (val >= target) if operator == '>=' else (val <= target)
                        claim_id = (
                            f"goal_{g_id}_{end_str.replace('-', '')}" if period == "daily"
                            else f"goal_{g_id}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
                        )
                        if rebuild_dates and any(start_str <= value <= end_str for value in rebuild_dates):
                            self._remove_goal_claim_in_txn(conn, user_id, claim_id)
                        _issue_goal(claim_id, is_met, val, target, operator, period_end_date, fail_if_not_met=True)

            return settled_details

    def inspect_goal_period_facts(self, user_id, period_end_dates):
        """只读汇总指定周期结束日的目标事实，不返回目标标题或其它业务内容。"""
        dates = sorted({str(value)[:10] for value in period_end_dates if str(value)[:10]})
        if not dates:
            return []
        placeholders = ','.join('?' for _ in dates)
        suffixes = {value.replace('-', '') for value in dates}
        with self._connect() as conn:
            claims = [str(row['ext_id']) for row in conn.execute(
                "SELECT ext_id FROM server_external_rewards WHERE user_id=? AND item_type='goal' AND ext_id LIKE 'goal_%'",
                (user_id,),
            ).fetchall()]
            ledger_rows = conn.execute(
                f"""SELECT id,source_id,amount,target_date FROM server_reward_ledger
                    WHERE user_id=? AND target_date IN ({placeholders})
                      AND (source_type IN ('goal_reward','goal_penalty') OR source_id LIKE '%:goal:goal_%')""",
                (user_id, *dates),
            ).fetchall()
        result = []
        for target_date in dates:
            rows = [row for row in ledger_rows if row['target_date'] == target_date]
            claim_ids = sorted(claim for claim in claims if claim.endswith(target_date.replace('-', '')))
            result.append({
                'target_date': target_date,
                'claim_ids': claim_ids,
                'ledger_ids': sorted(str(row['id']) for row in rows),
                'ledger_count': len(rows),
                'ledger_amount': sum(float(row['amount']) for row in rows),
                'has_server_fact': bool(claim_ids),
            })
        return result

    def recalculate_goal_periods(self, user_id, dates):
        """仅重建受同步会话影响且已经结束的目标周期。"""
        closed_dates = [str(value)[:10] for value in dates if str(value)[:10] < now_str()[:10]]
        return self.auto_settle_goals(user_id, rebuild_dates=closed_dates) if closed_dates else []

    # --- 6. 奖励商店与金币流水 (Rewards & Ledger) ---
    def get_gold_balance(self, user_id):
        # 调用链路：GET /api/rewards/balance -> store 门面 -> RewardWalletService -> SUM(server_reward_ledger)。
        return self.reward_wallet_service.get_gold_balance(user_id)

    def list_rewards(self, user_id):
        self.auto_unlock_rewards(user_id)
        self._ensure_custom_spend_templates(user_id)
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM server_rewards WHERE user_id=? AND is_active=1 ORDER BY id ASC", (user_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _ensure_custom_spend_templates(self, user_id):
        with self._transact() as conn:
            existing = {
                row["title"] for row in conn.execute(
                    "SELECT title FROM server_rewards WHERE user_id=? AND redemption_mode='custom_spend' AND is_active=1",
                    (user_id,),
                ).fetchall()
            }
            stamp = now_str()
            for title, icon in (("零食", "🍿"), ("网购", "🛍️")):
                if title in existing:
                    continue
                reward_id = uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO server_rewards
                    (id, user_id, title, icon, price, redemption_mode, description, inventory_mode,
                     unlock_required_count, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 0, 'custom_spend', '每次兑换时填写实际消费金额', 'unlimited', 1, 1, ?, ?)""",
                    (reward_id, user_id, title, icon, stamp, stamp),
                )
                self._record_server_change(conn, user_id, "server_rewards", reward_id, "upsert", {"id": reward_id})

    def _resolve_unlock_source(self, conn, user_id, unlock_source_type=None, unlock_source_id=None, unlock_task_id=None, allow_legacy_exercise=False):
        source = str(unlock_source_id or "")
        source_type = unlock_source_type
        if not source_type and unlock_task_id:
            legacy = str(unlock_task_id)
            source_type = "goal" if legacy.startswith("goal_") else "checklist_task"
            source = legacy[5:] if source_type == "goal" else legacy
        if not source_type and not source:
            return None
        allowed_sources = {"checklist_task", "habit", "learning_task", "learning_objective", "goal"}
        if allow_legacy_exercise:
            allowed_sources.add("exercise_checkin")
        if source_type not in allowed_sources or not source:
            raise ValueError("解锁来源无效")
        if source_type == "goal":
            row = conn.execute(
                "SELECT title FROM server_goals WHERE id=? AND user_id=? AND is_active=1",
                (source, user_id),
            ).fetchone()
        elif source_type == "checklist_task":
            row = conn.execute(
                "SELECT title FROM server_tasks WHERE id=? AND user_id=? AND status=0 AND deleted_at IS NULL",
                (source, user_id),
            ).fetchone()
        elif source_type == "habit":
            row = conn.execute(
                "SELECT name AS title FROM server_habits WHERE id=? AND user_id=? AND is_active=0",
                (source, user_id),
            ).fetchone()
        elif source_type == "learning_task":
            row = conn.execute(
                "SELECT title FROM server_learning_tasks WHERE id=? AND user_id=? AND status<>2",
                (source, user_id),
            ).fetchone()
        elif source_type == "learning_objective":
            row = conn.execute(
                "SELECT title FROM server_learning_objectives WHERE id=? AND user_id=? AND status<>2",
                (source, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT name AS title FROM server_exercise_plan_items WHERE id=? AND user_id=? AND is_active=1",
                (source, user_id),
            ).fetchone()
        if not row:
            raise ValueError("解锁来源不存在或不属于当前账号")
        legacy_id = f"goal_{source}" if source_type == "goal" else source if source_type == "checklist_task" else None
        return {"type": source_type, "id": source, "title": row["title"], "legacy_id": legacy_id}

    @staticmethod
    def _validate_reward_rules(inventory_mode="unlimited", inventory_limit=None, unlock_source_type=None, unlock_required_count=1):
        mode = str(inventory_mode or "unlimited")
        if mode == "weekly":
            raise ValueError("每周库存已取消，请选不限量、每天或每月")
        if mode not in {"unlimited", "daily", "monthly"}:
            raise ValueError("库存周期只能选不限量、每天或每月")
        if mode == "unlimited":
            inventory_limit = None
        else:
            try:
                inventory_limit = int(inventory_limit)
            except (TypeError, ValueError):
                raise ValueError("限量商品必须设置正整数数量")
            if inventory_limit <= 0:
                raise ValueError("限量商品必须设置正整数数量")
        try:
            required = int(unlock_required_count or 1)
        except (TypeError, ValueError):
            raise ValueError("累计打卡次数必须为正整数")
        if required <= 0:
            raise ValueError("碎片目标数必须是正整数")
        return mode, inventory_limit, required

    @staticmethod
    def _validate_fragment_rules(source_type, fulfillment_mode, fragment_target_count):
        mode = str(fulfillment_mode or "immediate")
        if mode not in {"immediate", "fragment"}:
            raise ValueError("物品发放方式无效")
        try:
            target = int(fragment_target_count or 1)
        except (TypeError, ValueError):
            raise ValueError("碎片目标数必须是正整数")
        if target < 1:
            raise ValueError("碎片目标数必须是正整数")
        return mode, target

    def bind_reward_source(self, user_id, reward_id, source_type, source_id, drop_mode="fixed", drop_min_units=None, drop_max_units=None):
        """在来源侧建立完成奖励商品绑定；一个商品可绑定任意多个来源。"""
        with self._transact() as conn:
            source = self._resolve_unlock_source(conn, user_id, source_type, source_id)
            reward = conn.execute("SELECT * FROM server_rewards WHERE id=? AND user_id=? AND is_active=1", (reward_id, user_id)).fetchone()
            if not reward:
                raise ValueError("商品不存在或已下架")
            if str(reward["redemption_mode"] or "coins") in {"coins", "custom_spend", "pending_binding"}:
                raise ValueError("只有完成奖励型商品可以绑定到任务、习惯或学习目标")
            if str(reward["fulfillment_mode"] or "immediate") != "fragment":
                raise ValueError("完成奖励型商品必须使用碎片合成")
            if drop_mode not in {"fixed", "random"}:
                raise ValueError("掉落规则无效")
            if drop_min_units is not None:
                drop_min_units = int(drop_min_units)
                drop_max_units = int(drop_max_units if drop_max_units is not None else drop_min_units)
                if drop_min_units < 1 or drop_max_units < drop_min_units or drop_max_units > 100:
                    raise ValueError("掉落进度必须在 1–100 之间")
            binding_id = f"reward-source:{reward_id}:{source['type']}:{source['id']}"
            stamp = now_str()
            conn.execute(
                """INSERT INTO server_reward_source_bindings
                   (id,user_id,reward_id,source_type,source_id,drop_mode,drop_min_units,drop_max_units,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,reward_id,source_type,source_id) DO UPDATE SET
                   drop_mode=excluded.drop_mode,drop_min_units=excluded.drop_min_units,drop_max_units=excluded.drop_max_units,updated_at=excluded.updated_at""",
                (binding_id, user_id, reward_id, source["type"], source["id"], drop_mode, drop_min_units, drop_max_units, stamp, stamp),
            )
            self._record_server_change(conn, user_id, "server_reward_source_bindings", binding_id, "upsert", {"id": binding_id})
            return binding_id

    def unbind_reward_source(self, user_id, reward_id, source_type, source_id):
        with self._transact() as conn:
            source = self._resolve_unlock_source(conn, user_id, source_type, source_id)
            row = conn.execute(
                "SELECT id FROM server_reward_source_bindings WHERE user_id=? AND reward_id=? AND source_type=? AND source_id=?",
                (user_id, reward_id, source["type"], source["id"]),
            ).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM server_reward_source_bindings WHERE id=?", (row["id"],))
            self._record_server_change(conn, user_id, "server_reward_source_bindings", row["id"], "delete", {"id": row["id"]})
            return True

    def _detach_source_reward(self, conn, user_id, source_type, source_id, except_id=None):
        if source_type == "learning_objective":
            return
        rows = conn.execute(
            """SELECT id FROM server_rewards WHERE user_id=? AND is_active=1
               AND unlock_source_type=? AND unlock_source_id=? AND id<>?""",
            (user_id, source_type, source_id, str(except_id or "")),
        ).fetchall()
        stamp = now_str()
        for row in rows:
            conn.execute(
                """UPDATE server_rewards SET unlock_task_id=NULL,unlock_task_title=NULL,
                   unlock_source_type=NULL,unlock_source_id=NULL,unlock_required_count=1,
                   unlock_threshold_started_at=NULL,fulfillment_mode='immediate',fragment_target_count=1,
                   fragment_rule_version=fragment_rule_version+1,updated_at=? WHERE id=? AND user_id=?""",
                (stamp, row["id"], user_id),
            )
            self._record_server_change(conn, user_id, "server_rewards", row["id"], "upsert", {"id": row["id"]})

    def create_reward(self, user_id, title, icon='🎁', price=10.0, description=None, unlock_task_id=None, unlock_task_title=None, unlock_source_type=None, unlock_source_id=None, inventory_mode="unlimited", inventory_limit=None, unlock_required_count=1, redemption_mode="coins", fulfillment_mode=None, fragment_target_count=None):
        with self._transact() as conn:
            if redemption_mode not in {"coins", "task", "goal", "pending_binding", "custom_spend"}:
                raise ValueError("兑换类型无效")
            source = self._resolve_unlock_source(conn, user_id, unlock_source_type, unlock_source_id, unlock_task_id)
            if source:
                if float(price) != 0:
                    raise ValueError("解锁型奖励价格必须为 0")
                unlock_source_type = source["type"]
                unlock_source_id = source["id"]
                unlock_task_id = source["legacy_id"]
                unlock_task_title = source["title"]
                redemption_mode = "goal" if source["type"] == "goal" else "task"
            if redemption_mode in {"task", "goal", "pending_binding", "custom_spend"}:
                price = 0
            inventory_mode, inventory_limit, unlock_required_count = self._validate_reward_rules(
                inventory_mode, inventory_limit, unlock_source_type, unlock_required_count
            )
            fulfillment_mode, fragment_target_count = self._validate_fragment_rules(
                unlock_source_type,
                fulfillment_mode or ("fragment" if source and source["type"] in {"habit", "checklist_task", "learning_task", "learning_objective", "exercise_checkin"} else "immediate"),
                fragment_target_count if fragment_target_count is not None else unlock_required_count,
            )
            reward_id = uuid.uuid4().hex
            now_ts = now_str()
            if source and source["type"] != "learning_objective":
                self._detach_source_reward(conn, user_id, source["type"], source["id"])
            conn.execute(
                """
                INSERT INTO server_rewards (id, user_id, title, icon, price, redemption_mode, description, unlock_task_id, unlock_task_title, unlock_source_type, unlock_source_id, inventory_mode, inventory_limit, unlock_required_count, unlock_threshold_started_at, fulfillment_mode, fragment_target_count, fragment_rule_version, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (reward_id, user_id, title, icon, price, redemption_mode, description, unlock_task_id, unlock_task_title, unlock_source_type, unlock_source_id, inventory_mode, inventory_limit, unlock_required_count, now_ts if unlock_source_type == "habit" else None, fulfillment_mode, fragment_target_count, now_ts, now_ts)
            )
            if source:
                binding_id = f"reward-source:{reward_id}:{source['type']}:{source['id']}"
                conn.execute(
                    """INSERT OR IGNORE INTO server_reward_source_bindings
                       (id,user_id,reward_id,source_type,source_id,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (binding_id, user_id, reward_id, source["type"], source["id"], now_ts, now_ts),
                )
                self._record_server_change(conn, user_id, "server_reward_source_bindings", binding_id, "upsert", {"id": binding_id})
            self._record_server_change(conn, user_id, "server_rewards", reward_id, "upsert", {"id": reward_id})
            return reward_id

    def update_reward(self, user_id, reward_id, title=None, icon=None, price=None, description=None, is_active=None, unlock_task_id=UNSET, unlock_task_title=UNSET, unlock_source_type=UNSET, unlock_source_id=UNSET, inventory_mode=UNSET, inventory_limit=UNSET, unlock_required_count=UNSET, redemption_mode=UNSET, fulfillment_mode=UNSET, fragment_target_count=UNSET):
        with self._transact() as conn:
            row = conn.execute("SELECT * FROM server_rewards WHERE id=? AND user_id=?", (reward_id, user_id)).fetchone()
            if not row:
                return False

            fields = []
            params = []
            if title is not None:
                fields.append("title=?")
                params.append(title)
            if icon is not None:
                fields.append("icon=?")
                params.append(icon)
            if price is not None:
                fields.append("price=?")
                params.append(price)
            if description is not None:
                fields.append("description=?")
                params.append(description)
            if is_active is not None:
                fields.append("is_active=?")
                params.append(is_active)
            requested_redemption_mode = row["redemption_mode"] if redemption_mode is UNSET else redemption_mode
            if requested_redemption_mode not in {"coins", "task", "goal", "pending_binding", "custom_spend"}:
                raise ValueError("兑换类型无效")
            source_changed = unlock_source_type is not UNSET or unlock_source_id is not UNSET or unlock_task_id is not UNSET
            if source_changed:
                requested_type = row["unlock_source_type"] if unlock_source_type is UNSET else unlock_source_type
                requested_id = row["unlock_source_id"] if unlock_source_id is UNSET else unlock_source_id
                legacy_id = row["unlock_task_id"] if unlock_task_id is UNSET else unlock_task_id
                allow_legacy_exercise = (
                    requested_type == "exercise_checkin"
                    and row["unlock_source_type"] == "exercise_checkin"
                    and str(requested_id or "") == str(row["unlock_source_id"] or "")
                )
                source = self._resolve_unlock_source(conn, user_id, requested_type, requested_id, legacy_id, allow_legacy_exercise)
                if source and float(price if price is not None else row["price"]) != 0:
                    raise ValueError("解锁型奖励价格必须为 0")
                fields.extend(["unlock_source_type=?", "unlock_source_id=?", "unlock_task_id=?", "unlock_task_title=?"])
                params.extend([
                    source["type"] if source else None,
                    source["id"] if source else None,
                    source["legacy_id"] if source else None,
                    source["title"] if source else None,
                ])
                if source and source["type"] != "learning_objective" and int(row["is_active"] if is_active is None else is_active) == 1:
                    self._detach_source_reward(conn, user_id, source["type"], source["id"], reward_id)
                requested_redemption_mode = "goal" if source and source["type"] == "goal" else "task" if source else requested_redemption_mode
            elif is_active == 1 and row["unlock_source_type"] != "learning_objective" and row["unlock_source_type"] and row["unlock_source_id"]:
                self._detach_source_reward(
                    conn, user_id, row["unlock_source_type"], row["unlock_source_id"], reward_id
                )
            effective_type = source["type"] if source_changed and source else None if source_changed else row["unlock_source_type"]
            legacy_weekly = str(row["inventory_mode"] or "") == "weekly"
            requested_mode = row["inventory_mode"] if inventory_mode is UNSET else inventory_mode
            if str(requested_mode or "") == "weekly" and legacy_weekly:
                requested_mode = "unlimited"
            requested_limit = row["inventory_limit"] if inventory_limit is UNSET else inventory_limit
            requested_count = 1 if source_changed and source is None else row["unlock_required_count"] if unlock_required_count is UNSET else unlock_required_count
            mode, limit, required = self._validate_reward_rules(requested_mode, requested_limit, effective_type, requested_count)
            requested_fulfillment = row["fulfillment_mode"] if fulfillment_mode is UNSET else fulfillment_mode
            requested_target = row["fragment_target_count"] if fragment_target_count is UNSET else fragment_target_count
            if source_changed and source is None:
                requested_fulfillment, requested_target = "immediate", 1
            requested_fulfillment, requested_target = self._validate_fragment_rules(
                effective_type, requested_fulfillment, requested_target,
            )
            if inventory_mode is not UNSET or inventory_limit is not UNSET or legacy_weekly:
                fields.extend(["inventory_mode=?", "inventory_limit=?"])
                params.extend([mode, limit])
            if unlock_required_count is not UNSET or (source_changed and effective_type != row["unlock_source_type"]):
                fields.extend(["unlock_required_count=?", "unlock_threshold_started_at=?"])
                params.extend([required, now_str() if effective_type == "habit" else None])
            rule_changed = requested_fulfillment != row["fulfillment_mode"] or int(requested_target) != int(row["fragment_target_count"] or 1) or source_changed
            if fulfillment_mode is not UNSET or fragment_target_count is not UNSET or source_changed:
                fields.extend(["fulfillment_mode=?", "fragment_target_count=?"])
                params.extend([requested_fulfillment, requested_target])
            if rule_changed:
                fields.append("fragment_rule_version=?")
                params.append(int(row["fragment_rule_version"] or 1) + 1)
            if redemption_mode is not UNSET or source_changed:
                fields.append("redemption_mode=?")
                params.append(requested_redemption_mode)
            if requested_redemption_mode in {"pending_binding", "custom_spend"}:
                fields.append("price=?")
                params.append(0)

            if not fields:
                return True

            fields.append("updated_at=?")
            params.append(now_str())
            query = f"UPDATE server_rewards SET {', '.join(fields)} WHERE id=? AND user_id=?"
            params.extend([reward_id, user_id])
            conn.execute(query, tuple(params))
            self._record_server_change(conn, user_id, "server_rewards", reward_id, "upsert", {"id": reward_id})
            return True

    def delete_reward(self, user_id, reward_id):
        return self.update_reward(user_id, reward_id, is_active=0)

    def auto_unlock_rewards(self, user_id):
        """将服务端已完成来源写成按事件幂等的零价背包入库事实。"""
        with self._transact() as conn:
            self._settle_linked_learning_tasks_in_txn(conn, user_id)
            rewards = conn.execute(
                """SELECT r.id, r.title, b.source_type, b.source_id
                   FROM server_reward_source_bindings b JOIN server_rewards r ON r.id=b.reward_id
                   WHERE b.user_id=? AND r.is_active=1""",
                (user_id,),
            ).fetchall()
            for reward in rewards:
                source_type = reward["source_type"]
                source_id = reward["source_id"]
                if not source_id or source_type == "goal":
                    continue
                event_key = None
                target_date = now_str()[:10]
                source_title = reward["title"]
                if source_type == "checklist_task":
                    row = conn.execute("SELECT title, updated_at FROM server_tasks WHERE user_id=? AND id=? AND status=2 AND deleted_at IS NULL", (user_id, source_id)).fetchone()
                    if row:
                        target_date = str(row["updated_at"] or target_date)[:10]
                        event_key = self.reward_settlement_service.completion_event_key(source_type, source_id, target_date, row["updated_at"])
                        source_title = row["title"]
                elif source_type == "habit":
                    row = conn.execute("SELECT checkin_date, date FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND status=2 ORDER BY checkin_date DESC, date DESC LIMIT 1", (user_id, source_id)).fetchone()
                    if row:
                        target_date = str(row["checkin_date"] or row["date"] or target_date)[:10]
                        event_key = self.reward_settlement_service.completion_event_key(source_type, source_id, target_date)
                elif source_type == "learning_task":
                    row = conn.execute("SELECT title, updated_at FROM server_learning_tasks WHERE user_id=? AND id=? AND status=2", (user_id, source_id)).fetchone()
                    if row:
                        target_date = str(row["updated_at"] or target_date)[:10]
                        event_key = self.reward_settlement_service.completion_event_key(source_type, source_id, target_date, row["updated_at"])
                        source_title = row["title"]
                elif source_type == "learning_objective":
                    row = conn.execute("SELECT title, updated_at FROM server_learning_objectives WHERE user_id=? AND id=? AND status=2", (user_id, source_id)).fetchone()
                    if row and self._objective_links_completed_in_txn(conn, user_id, source_id):
                        target_date = str(row["updated_at"] or target_date)[:10]
                        event_key = self.reward_settlement_service.completion_event_key(source_type, source_id, target_date, row["updated_at"])
                        source_title = row["title"]
                elif source_type == "exercise_checkin":
                    row = conn.execute("SELECT plan_version, date, item_key, item_name FROM server_exercise_checkins WHERE user_id=? AND plan_item_id=? AND status=1 ORDER BY updated_at DESC LIMIT 1", (user_id, source_id)).fetchone()
                    if row:
                        target_date = str(row["date"] or target_date)[:10]
                        event_key = self.reward_settlement_service.completion_event_key(source_type, source_id, target_date, plan_version=row["plan_version"], item_key=row["item_key"])
                        source_title = row["item_name"] or source_title
                if not event_key:
                    continue
                self.reward_settlement_service.grant_task_unlocks_in_txn(
                    conn, user_id, source_type, source_id, event_key, source_title, target_date
                )

    def link_learning_checklist_task(self, user_id, learning_task_id, checklist_task_id):
        with self._transact() as conn:
            self._remove_deleted_learning_checklist_links_in_txn(conn, user_id)
            link_created = conn.execute(
                "INSERT OR IGNORE INTO server_learning_checklist_links(user_id,learning_task_id,checklist_task_id,created_at) VALUES(?,?,?,?)",
                (user_id, learning_task_id, checklist_task_id, now_str()),
            ).rowcount > 0
            if link_created:
                conn.execute(
                    """INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(user_id,item_type,item_id) DO UPDATE SET
                         coins=excluded.coins, penalty=excluded.penalty, updated_at=excluded.updated_at""",
                    (user_id, "task", checklist_task_id, 10, 10, now_str()),
                )
                task = conn.execute(
                    "SELECT kr_id,status FROM server_learning_tasks WHERE user_id=? AND id=?",
                    (user_id, learning_task_id),
                ).fetchone()
                if task and int(task["status"] or 0) != 2:
                    conn.execute("UPDATE server_learning_tasks SET status=2,updated_at=? WHERE user_id=? AND id=?", (now_str(), user_id, learning_task_id))
                    conn.execute("UPDATE server_learning_krs SET current_value=current_value+1,updated_at=? WHERE user_id=? AND id=?", (now_str(), user_id, task["kr_id"]))
                    self._record_server_change(conn, user_id, "server_learning_tasks", learning_task_id, "upsert", {"id": learning_task_id, "status": 2})
                    self._record_server_change(conn, user_id, "server_learning_krs", task["kr_id"], "upsert", {"id": task["kr_id"]})
                    self._refresh_learning_objectives_in_txn(conn, user_id)

    def get_learning_checklist_cancellation(self, user_id, learning_task_id):
        """Return the still-pending external checklist task that can be safely cancelled."""
        with self._transact() as conn:
            row = conn.execute(
                """SELECT link.checklist_task_id, link.completed_at, checklist.status AS checklist_status,
                          checklist.raw_json
                   FROM server_learning_checklist_links link
                   LEFT JOIN server_tasks checklist
                     ON checklist.user_id=link.user_id AND checklist.id=link.checklist_task_id
                   WHERE link.user_id=? AND link.learning_task_id=?
                   ORDER BY link.created_at DESC LIMIT 1""",
                (user_id, learning_task_id),
            ).fetchone()
            if not row:
                return None
            if row["checklist_status"] is not None and int(row["checklist_status"] or 0) == 0 and row["completed_at"] is not None:
                conn.execute(
                    "UPDATE server_learning_checklist_links SET completed_at=NULL WHERE user_id=? AND learning_task_id=? AND checklist_task_id=?",
                    (user_id, learning_task_id, row["checklist_task_id"]),
                )
            if row["checklist_status"] is not None and int(row["checklist_status"] or 0) != 0:
                raise ValueError("关联清单任务已完成，不能取消")
            if row["checklist_status"] is None:
                return {"checklist_task_id": str(row["checklist_task_id"]), "provider_missing": True}
            try:
                snapshot = json.loads(row["raw_json"] or "{}")
            except (TypeError, ValueError):
                snapshot = {}
            project_id = str(snapshot.get("project_id") or snapshot.get("projectId") or "").strip()
            if not project_id:
                raise ValueError("关联清单任务缺少项目，无法安全取消")
            return {"checklist_task_id": str(row["checklist_task_id"]), "project_id": project_id, "provider_missing": False}

    def cancel_learning_checklist_task(self, user_id, learning_task_id, checklist_task_id):
        """Remove a pending association and restore only the affected learning progress."""
        with self._transact() as conn:
            row = conn.execute(
                """SELECT link.completed_at, learn.status AS learning_status, learn.kr_id,
                          kr.objective_id, objective.status AS objective_status
                   FROM server_learning_checklist_links link
                   JOIN server_learning_tasks learn
                     ON learn.user_id=link.user_id AND learn.id=link.learning_task_id
                   JOIN server_learning_krs kr ON kr.user_id=learn.user_id AND kr.id=learn.kr_id
                   JOIN server_learning_objectives objective
                     ON objective.user_id=kr.user_id AND objective.id=kr.objective_id
                   WHERE link.user_id=? AND link.learning_task_id=? AND link.checklist_task_id=?""",
                (user_id, learning_task_id, checklist_task_id),
            ).fetchone()
            if not row:
                return False
            if row["completed_at"] is not None:
                raise ValueError("关联清单任务已完成，不能取消")
            now = now_str()
            conn.execute(
                "DELETE FROM server_learning_checklist_links WHERE user_id=? AND learning_task_id=? AND checklist_task_id=?",
                (user_id, learning_task_id, checklist_task_id),
            )
            conn.execute(
                "DELETE FROM server_reward_config WHERE user_id=? AND item_type='task' AND item_id=?",
                (user_id, checklist_task_id),
            )
            if int(row["learning_status"] or 0) == 2:
                conn.execute("UPDATE server_learning_tasks SET status=0,updated_at=? WHERE user_id=? AND id=?", (now, user_id, learning_task_id))
                conn.execute("UPDATE server_learning_krs SET current_value=MAX(current_value-1,0),updated_at=? WHERE user_id=? AND id=?", (now, user_id, row["kr_id"]))
                self._record_server_change(conn, user_id, "server_learning_tasks", learning_task_id, "upsert", {"id": learning_task_id, "status": 0})
                self._record_server_change(conn, user_id, "server_learning_krs", row["kr_id"], "upsert", {"id": row["kr_id"]})
            pending = conn.execute(
                "SELECT 1 FROM server_learning_krs WHERE user_id=? AND objective_id=? AND current_value<target_value LIMIT 1",
                (user_id, row["objective_id"]),
            ).fetchone()
            if pending and int(row["objective_status"] or 0) == 2:
                conn.execute("UPDATE server_learning_objectives SET status=0,updated_at=? WHERE user_id=? AND id=?", (now, user_id, row["objective_id"]))
                self._record_server_change(conn, user_id, "server_learning_objectives", row["objective_id"], "upsert", {"id": row["objective_id"], "status": 0})
            return True

    def _settle_linked_learning_tasks_in_txn(self, conn, user_id):
        self._remove_deleted_learning_checklist_links_in_txn(conn, user_id)
        conn.execute(
            """UPDATE server_learning_checklist_links AS link SET completed_at=NULL
               WHERE link.user_id=? AND link.completed_at IS NOT NULL
                 AND EXISTS (SELECT 1 FROM server_tasks task
                             WHERE task.user_id=link.user_id AND task.id=link.checklist_task_id
                               AND task.status=0 AND task.deleted_at IS NULL)""",
            (user_id,),
        )
        rows = conn.execute(
            """SELECT link.learning_task_id, link.checklist_task_id, task.updated_at, learn.kr_id
               FROM server_learning_checklist_links link
               JOIN server_tasks task ON task.user_id=link.user_id AND task.id=link.checklist_task_id
               JOIN server_learning_tasks learn ON learn.user_id=link.user_id AND learn.id=link.learning_task_id
               WHERE link.user_id=? AND link.completed_at IS NULL AND task.status=2 AND task.deleted_at IS NULL""",
            (user_id,),
        ).fetchall()
        for row in rows:
            conn.execute("UPDATE server_learning_checklist_links SET completed_at=? WHERE user_id=? AND learning_task_id=? AND checklist_task_id=?", (now_str(), user_id, row["learning_task_id"], row["checklist_task_id"]))
        self._refresh_learning_objectives_in_txn(conn, user_id)
        self._settle_learning_objective_coins_in_txn(conn, user_id)

    def _remove_deleted_learning_checklist_links_in_txn(self, conn, user_id):
        learning_task_ids = conn.execute(
            """SELECT DISTINCT link.learning_task_id FROM server_learning_checklist_links link
               JOIN server_tasks task ON task.user_id=link.user_id AND task.id=link.checklist_task_id
               WHERE link.user_id=? AND task.deleted_at IS NOT NULL""",
            (user_id,),
        ).fetchall()
        for item in learning_task_ids:
            learning_task_id = item["learning_task_id"]
            stale_task_ids = [row["checklist_task_id"] for row in conn.execute(
                """SELECT link.checklist_task_id FROM server_learning_checklist_links link
                   JOIN server_tasks task ON task.user_id=link.user_id AND task.id=link.checklist_task_id
                   WHERE link.user_id=? AND link.learning_task_id=? AND task.deleted_at IS NOT NULL""",
                (user_id, learning_task_id),
            ).fetchall()]
            conn.executemany("DELETE FROM server_learning_checklist_links WHERE user_id=? AND learning_task_id=? AND checklist_task_id=?", [(user_id, learning_task_id, task_id) for task_id in stale_task_ids])
            conn.executemany("DELETE FROM server_reward_config WHERE user_id=? AND item_type='task' AND item_id=?", [(user_id, task_id) for task_id in stale_task_ids])
            has_active_link = conn.execute(
                """SELECT 1 FROM server_learning_checklist_links link
                   JOIN server_tasks task ON task.user_id=link.user_id AND task.id=link.checklist_task_id
                   WHERE link.user_id=? AND link.learning_task_id=? AND task.deleted_at IS NULL LIMIT 1""",
                (user_id, learning_task_id),
            ).fetchone()
            if has_active_link:
                continue
            row = conn.execute(
                """SELECT learn.status AS learning_status, learn.kr_id, kr.objective_id, objective.status AS objective_status
                   FROM server_learning_tasks learn
                   JOIN server_learning_krs kr ON kr.user_id=learn.user_id AND kr.id=learn.kr_id
                   JOIN server_learning_objectives objective ON objective.user_id=kr.user_id AND objective.id=kr.objective_id
                   WHERE learn.user_id=? AND learn.id=?""",
                (user_id, learning_task_id),
            ).fetchone()
            if not row or int(row["learning_status"] or 0) != 2:
                continue
            now = now_str()
            conn.execute("UPDATE server_learning_tasks SET status=0,updated_at=? WHERE user_id=? AND id=?", (now, user_id, learning_task_id))
            conn.execute("UPDATE server_learning_krs SET current_value=MAX(current_value-1,0),updated_at=? WHERE user_id=? AND id=?", (now, user_id, row["kr_id"]))
            self._record_server_change(conn, user_id, "server_learning_tasks", learning_task_id, "upsert", {"id": learning_task_id, "status": 0})
            self._record_server_change(conn, user_id, "server_learning_krs", row["kr_id"], "upsert", {"id": row["kr_id"]})
            pending = conn.execute("SELECT 1 FROM server_learning_krs WHERE user_id=? AND objective_id=? AND current_value<target_value LIMIT 1", (user_id, row["objective_id"])).fetchone()
            if pending and int(row["objective_status"] or 0) == 2:
                conn.execute("UPDATE server_learning_objectives SET status=0,updated_at=? WHERE user_id=? AND id=?", (now, user_id, row["objective_id"]))
                self._record_server_change(conn, user_id, "server_learning_objectives", row["objective_id"], "upsert", {"id": row["objective_id"], "status": 0})

    def _refresh_learning_objectives_in_txn(self, conn, user_id):
        objectives = conn.execute("SELECT id,title FROM server_learning_objectives WHERE user_id=? AND status<>2", (user_id,)).fetchall()
        for objective in objectives:
            has_kr = conn.execute("SELECT 1 FROM server_learning_krs WHERE user_id=? AND objective_id=?", (user_id, objective["id"])).fetchone()
            if not has_kr:
                continue
            pending = conn.execute("SELECT 1 FROM server_learning_krs WHERE user_id=? AND objective_id=? AND current_value < target_value", (user_id, objective["id"])).fetchone()
            if pending:
                continue
            conn.execute("UPDATE server_learning_objectives SET status=2,updated_at=? WHERE user_id=? AND id=?", (now_str(), user_id, objective["id"]))
            self._record_server_change(conn, user_id, "server_learning_objectives", objective["id"], "upsert", {"id": objective["id"], "status": 2})

    def _objective_links_completed_in_txn(self, conn, user_id, objective_id):
        return not conn.execute(
            """SELECT 1 FROM server_learning_checklist_links link
               JOIN server_learning_tasks task ON task.user_id=link.user_id AND task.id=link.learning_task_id
               JOIN server_learning_krs kr ON kr.user_id=task.user_id AND kr.id=task.kr_id
               WHERE link.user_id=? AND kr.objective_id=? AND link.completed_at IS NULL LIMIT 1""",
            (user_id, objective_id),
        ).fetchone()

    def _settle_learning_objective_coins_in_txn(self, conn, user_id):
        objectives = conn.execute("SELECT id,title FROM server_learning_objectives WHERE user_id=? AND status=2", (user_id,)).fetchall()
        for objective in objectives:
            if not self._objective_links_completed_in_txn(conn, user_id, objective["id"]):
                continue
            completed = conn.execute(
                """SELECT MAX(link.completed_at) completed_at FROM server_learning_checklist_links link
                   JOIN server_learning_tasks task ON task.user_id=link.user_id AND task.id=link.learning_task_id
                   JOIN server_learning_krs kr ON kr.user_id=task.user_id AND kr.id=task.kr_id
                   WHERE link.user_id=? AND kr.objective_id=?""", (user_id, objective["id"]),
            ).fetchone()
            occurred_at = completed["completed_at"] if completed else None
            if not occurred_at:
                continue
            reward = conn.execute("SELECT coins FROM server_reward_config WHERE user_id=? AND item_type='learning_objective' AND item_id=?", (user_id, objective["id"])).fetchone()
            if reward and float(reward["coins"] or 0) > 0:
                source_id = f"learning_objective:{objective['id']}"
                exists = conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=? AND source_type='learning_objective_complete' AND source_id=?", (user_id, source_id)).fetchone()
                if not exists:
                    self.reward_wallet_service.append_ledger_in_txn(
                        conn, user_id, float(reward["coins"]), "learning_objective_complete", source_id,
                        f"学习目标完成: {objective['title']}", str(occurred_at)[:10], source_id, str(occurred_at),
                    )
    def buy_reward(self, user_id, reward_id, amount=None, note=None):
        # 调用链路：POST /api/rewards/buy/{id} -> store 门面 -> RewardWalletService。
        with self._transact() as conn:
            reward = conn.execute(
                "SELECT * FROM server_rewards WHERE id=? AND user_id=? AND is_active=1",
                (reward_id, user_id),
            ).fetchone()
            if not reward:
                return False, "未找到该商品"
            mode = reward["redemption_mode"] or "coins"
            if mode == "pending_binding":
                return False, "该商品暂未绑定任务，暂不能兑换"
            if mode in {"task", "goal"}:
                return False, "完成奖励型商品只能在来源完成后自动合成"
            if mode == "custom_spend":
                note = str(note or "").strip()
                if not note:
                    return False, "请填写购买内容"
                if len(note) > 120:
                    return False, "购买内容不能超过120个字"

            if not self.reward_settlement_service.inventory_available_in_txn(conn, user_id, reward, now_str()[:10]):
                return False, "商品库存已用完"

            try:
                price = float(amount) if mode == "custom_spend" else float(reward["price"])
            except (TypeError, ValueError):
                return False, "请输入消费金额"
            if price <= 0 or round(price, 2) != price:
                return False, "消费金额必须是至多两位小数的正数"
            balance_row = conn.execute(
                "SELECT SUM(amount) AS total FROM server_reward_ledger WHERE user_id=?",
                (user_id,),
            ).fetchone()
            balance = float(balance_row["total"]) if balance_row and balance_row["total"] is not None else 0.0
            if balance < price:
                return False, "金币余额不足"

            purchase_id = f"{reward_id}:{uuid.uuid4().hex}"
            occurred_at = now_str()
            ledger_id = f"{mode}_{purchase_id}"[:180]
            self.reward_wallet_service.append_ledger_in_txn(
                conn,
                user_id,
                -price,
                "store_custom_spend" if mode == "custom_spend" else "reward_buy",
                purchase_id,
                f"{'消费' if mode == 'custom_spend' else '兑换商品成功'}: {reward['icon']}{reward['title']}（{price:g} 金币）" + (f" · {note}" if mode == "custom_spend" else ""),
                occurred_at.split(" ")[0],
                ledger_id,
                occurred_at,
            )
            self.reward_wallet_service.record_action_event_in_txn(
                conn, user_id, f"action:{ledger_id}",
                "custom_spend" if mode == "custom_spend" else "reward_purchase",
                -price, occurred_at, reward_id,
                {"ledger_id": ledger_id, "note": note or "", "title": reward["title"],
                 "description": f"{'消费' if mode == 'custom_spend' else '兑换商品成功'}: {reward['icon']}{reward['title']}（{price:g} 金币）" + (f" · {note}" if mode == "custom_spend" else ""),
                 "source_id": purchase_id, "source_type": "store_custom_spend" if mode == "custom_spend" else "reward_buy"},
            )
        return True, "购买成功"

    def list_ledger(self, user_id, limit=30):
        # 调用链路：GET /api/rewards/ledger -> store 门面 -> RewardWalletService -> SELECT ledger。
        return self.reward_wallet_service.list_ledger(user_id, limit)

    def add_ledger_entry(self, user_id, amount, source_type, source_id=None, description=''):
        # 调用链路：POST /api/rewards/ledger -> store 门面 -> RewardWalletService.add_ledger_entry。
        return self.reward_wallet_service.add_ledger_entry(user_id, amount, source_type, source_id, description)

    def list_unclaimed_rewards(self, user_id):
        # 调用链路：GET /api/rewards/unclaimed -> store 门面 -> RewardWalletService -> SELECT external_rewards。
        return self.reward_wallet_service.list_unclaimed_rewards(user_id)

    def claim_rewards(self, user_id, ids):
        # 调用链路：POST /api/rewards/claim -> store 门面 -> RewardWalletService.claim_rewards。
        return self.reward_wallet_service.claim_rewards(user_id, ids)

    def add_external_reward(self, user_id, ext_id, item_type, item_name, coins, status=0):
        # 调用链路：SyncHub/REST -> store 门面 -> RewardWalletService.add_external_reward；幂等键为 user_id + ext_id。
        return self.reward_wallet_service.add_external_reward(user_id, ext_id, item_type, item_name, coins, status)

    def list_backpack(self, user_id):
        # 调用链路：GET /api/rewards/backpack -> store 门面 -> RewardWalletService.list_backpack。
        return self.reward_wallet_service.list_backpack(user_id)

    def list_backpack_events(self, user_id, limit=50, offset=0):
        return self.reward_wallet_service.list_backpack_events(user_id, limit, offset)

    def preview_invalid_backpack_items(self, user_id):
        return self.reward_settlement_service.preview_invalid_habit_unlocks(user_id)

    def clean_invalid_backpack_items(self, user_id, summary_hash):
        return self.reward_settlement_service.remove_invalid_habit_unlocks(user_id, summary_hash)

    def use_backpack_item(self, user_id, ledger_id):
        # 调用链路：POST /api/rewards/use_item/{ledger_id} -> store 门面 -> RewardWalletService.use_backpack_item。
        return self.reward_wallet_service.use_backpack_item(user_id, ledger_id)

    def discard_backpack_item(self, user_id, ledger_id):
        return self.reward_wallet_service.discard_backpack_item(user_id, ledger_id)

    def reset_coins(self, user_id):
        # 调用链路：POST /api/rewards/reset -> store 门面 -> RewardWalletService.reset_coins。
        return self.reward_wallet_service.reset_coins(user_id)

    def get_system_config_val(self, user_id, key, default_val):
        conn = self._connect()
        try:
            row = conn.execute("SELECT value FROM server_system_config WHERE user_id=? AND key=?", (user_id, key)).fetchone()
            return row[0] if row else default_val
        finally:
            conn.close()

    def _format_description(self, template, icon, title):
        res = template.replace("{icon}", icon if icon else "")
        res = res.replace("{title}", title if title else "")
        return res

    def clear_user_data(self, user_id):
        with self._transact() as conn:
            conn.execute("DELETE FROM server_reward_ledger WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM server_external_rewards WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM server_goals WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM server_tasks WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM server_habit_checkins WHERE user_id=?", (user_id,))
            conn.execute("UPDATE server_user_wallets SET balance=0.0 WHERE user_id=?", (user_id,))
        return True

    def get_item_reward(self, user_id, item_type, item_id):
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT coins, penalty FROM server_reward_config WHERE user_id=? AND item_type=? AND item_id=?",
                (user_id, item_type, item_id)
            ).fetchone()
            if row:
                return {"coins": row["coins"], "penalty": row["penalty"]}
            return None
        finally:
            conn.close()

    def set_item_reward(self, user_id, item_type, item_id, coins, penalty=None):
        conn = self._connect()
        try:
            if penalty is None:
                penalty = coins
            conn.execute(
                """
                INSERT OR REPLACE INTO server_reward_config (user_id, item_type, item_id, coins, penalty)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, item_type, item_id, coins, penalty)
            )
            conn.commit()
            return True
        finally:
            conn.close()


    # --- 7. 睡眠数据管理 (Sleep Data) ---
    def get_huawei_sleep_data(self, user_id, date_str):
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM server_huawei_sleep_data WHERE user_id=? AND date=?", (user_id, date_str)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _allocate_server_version(self, conn, user_id):
        now = now_str()
        conn.execute(
            """
            INSERT INTO server_version_counters (user_id, current_version, updated_at)
            VALUES (?, 0, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, now),
        )
        conn.execute(
            """
            UPDATE server_version_counters
            SET current_version = current_version + 1, updated_at = ?
            WHERE user_id = ?
            """,
            (now, user_id),
        )
        row = conn.execute(
            "SELECT current_version FROM server_version_counters WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["current_version"])

    def _record_server_change(self, conn, user_id, table_name, record_id, operation, changed_fields):
        server_version = self._allocate_server_version(conn, user_id)
        now = now_str()
        change_id = f"server:{user_id}:{server_version}"
        entity_type = table_name[:-1] if table_name.endswith("s") else table_name
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
                None,
                table_name,
                str(record_id),
                entity_type,
                str(record_id),
                operation,
                json.dumps(changed_fields or {}, ensure_ascii=False, default=str),
                "applied",
                None,
                now,
                now,
            ),
        )
        return server_version

    def save_huawei_sleep_data(self, user_id, date_str, data, settle_score=False, report_completed_at=None):
        conn = self._connect()
        try:
            fields = [
                'sleep_score', 'total_sleep_min', 'deep_sleep_min', 'light_sleep_min',
                'rem_sleep_min', 'awake_count', 'sleep_start', 'sleep_end',
                'deep_sleep_ratio', 'light_sleep_ratio', 'rem_sleep_ratio',
                  'sleep_continuity', 'breathing_score', 'sleep_cycles',
                  'awake_min', 'fall_asleep_min', 'wake_up_min',
                  'atm_sleep_start', 'atm_sleep_end', 'calc_trace', 'analysis_report', 'analysis_html', 'official_advice',
                  'morning_diary', 'evening_diary',
                  'morning_diary_written_at', 'evening_diary_written_at',
                  'report_status', 'full_report_state', 'tracked_duration_seconds',
                  'source', 'synced_at', 'sync_status', 'sync_error'
              ]

            now = now_str()
            values_by_field = {}
            for field in fields:
                value = data.get(field)
                if field == 'morning_diary' and value is None:
                    value = data.get('sleep_reflection')
                if field == 'calc_trace' and value is not None and not isinstance(value, str):
                    value = json.dumps(value, ensure_ascii=False, default=str)
                values_by_field[field] = value

            existing = conn.execute(
                "SELECT id FROM server_huawei_sleep_data WHERE user_id=? AND date=?",
                (user_id, date_str),
            ).fetchone()
            if existing:
                update_fields = [field for field in fields if values_by_field[field] is not None]
                assignments = [f"{field}=?" for field in update_fields] + ["updated_at=?"]
                values = [values_by_field[field] for field in update_fields] + [now, user_id, date_str]
                conn.execute(
                    f"UPDATE server_huawei_sleep_data SET {', '.join(assignments)} WHERE user_id=? AND date=?",
                    tuple(values),
                )
                record_id = existing["id"]
            else:
                columns = ["user_id", "date", *fields, "updated_at"]
                placeholders = ", ".join(["?"] * len(columns))
                values = [user_id, date_str] + [values_by_field[field] for field in fields] + [now]
                cursor = conn.execute(
                    f"INSERT INTO server_huawei_sleep_data ({', '.join(columns)}) VALUES ({placeholders})",
                    tuple(values),
                )
                record_id = cursor.lastrowid
            if "morning_diary" in data or "evening_diary" in data:
                self.sleep_reward_service.reconcile_diary_completion_in_txn(conn, user_id, date_str)
            self._record_server_change(
                conn,
                user_id,
                "huawei_sleep_data",
                record_id,
                "upsert",
                {"date": date_str},
            )
            persisted = conn.execute(
                "SELECT * FROM server_huawei_sleep_data WHERE user_id=? AND date=?", (user_id, date_str),
            ).fetchone()
            settlement_metrics = dict(persisted)
            if report_completed_at:
                settlement_metrics["report_completed_at"] = report_completed_at
            settlement = self.sleep_reward_service.settle_in_txn(
                conn, user_id, date_str, settlement_metrics,
            ) if settle_score else None
            bedtime_result = self.sleep_reward_service.reconcile_bedtime_coin_in_txn(
                conn, user_id, date_str, deadline_reached=False,
            )
            conn.commit()
            return (bedtime_result or settlement) if settle_score else True
        finally:
            conn.close()

    def mark_huawei_sleep_sync_error(self, user_id, date_str, source, error):
        conn = self._connect()
        try:
            now = now_str()
            conn.execute(
                """
                INSERT INTO server_huawei_sleep_data
                    (user_id, date, source, synced_at, sync_status, sync_error, updated_at)
                VALUES (?, ?, ?, ?, 'error', ?, ?)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    source=excluded.source,
                    synced_at=excluded.synced_at,
                    sync_status=excluded.sync_status,
                    sync_error=excluded.sync_error,
                    updated_at=excluded.updated_at
                """,
                (user_id, date_str, source, now, str(error), now),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_sleep_history(self, user_id, limit=14):
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM server_huawei_sleep_data WHERE user_id=? ORDER BY date DESC LIMIT ?", (user_id, int(limit))).fetchall()
            return list(reversed([dict(r) for r in rows]))
        finally:
            conn.close()

    # --- 8. aTimeLogger 数据管理 ---
    def save_atm_data(self, user_id, date_str, data):
        activities = (data.get('activities', []) if isinstance(data, dict)
                      else (data if isinstance(data, list) else []))
        from .db_wrapper import ServerDBWrapper
        writer = ServerDBWrapper(self.db_path).write_server_change
        with self._connect() as conn:
            save_versioned_atm_data(conn, writer, user_id, date_str, activities, now_str())
        return True

    def get_atm_data(self, user_id, date_str):
        conn = self._connect()
        try:
            summary = conn.execute(
                "SELECT * FROM server_atm_summary WHERE user_id=? AND date=?",
                (user_id, date_str)
            ).fetchone()
            if not summary:
                return None

            rows = conn.execute(
                "SELECT * FROM server_atm_activities WHERE user_id=? AND date=? ORDER BY start_time",
                (user_id, date_str)
            ).fetchall()

            activities = []
            for r in rows:
                d = dict(r)
                # 兼容客户端读法
                d['type'] = d.get('activity_type') or ''
                d['start'] = d.get('start_time') or ''
                d['finish'] = d.get('end_time') or ''
                d['duration'] = (d.get('duration_minutes') or 0) * 60
                activities.append(d)

            return {
                'date': date_str,
                'activities': activities,
                'updated_at': dict(summary).get('updated_at', '')
            }
        finally:
            conn.close()

    # ======================== 多端同步 Push / Pull ========================

    def _server_table(self, client_table: str) -> str:
        return server_table_for(client_table)

    def batch_push(self, user_id: int, operations: list) -> dict:
        """
        批量 LWW 推送：接收客户端多表变更，逐条仲裁后写入。

        Args:
            user_id: 当前用户 ID
            operations: [{"table": "categories", "records": [{...}, ...]}, ...]
                       每条 record 必须含 id 和 updated_at

        Returns:
            {"accepted": N, "rejected": N}
        """
        conn = self._connect()
        try:
            accepted = 0
            rejected = 0

            for op in operations:
                table = op.get("table", "")
                records = op.get("records", [])
                try:
                    server_table = self._server_table(table)
                except ValueError:
                    rejected += len(records) if isinstance(records, list) else 1
                    continue

                for record in records:
                    record_id = record.get("id")
                    client_updated = record.get("updated_at", "")
                    action = record.get("action", "upsert")

                    if action == "delete":
                        # 软删除：服务端直接接受客户端的删除操作
                        try:
                            conn.execute(
                                f"UPDATE {server_table} SET is_active = 0, updated_at = ? "
                                f"WHERE id = ? AND user_id = ?",
                                (client_updated, record_id, user_id)
                            )
                            accepted += 1
                        except Exception:
                            rejected += 1
                        continue

                    # 查询服务端当前记录
                    row = conn.execute(
                        f"SELECT updated_at FROM {server_table} WHERE id = ? AND user_id = ?",
                        (record_id, user_id)
                    ).fetchone()

                    if row is None:
                        # 服务端没有 → 直接插入
                        accepted += self._insert_record(conn, server_table, user_id, record)
                    else:
                        server_updated = row["updated_at"] or ""
                        # LWW：客户端时间戳 > 服务端 → 接受
                        if client_updated >= server_updated:
                            accepted += self._update_record(
                                conn, server_table, user_id, record_id, record
                            )
                        else:
                            rejected += 1

            conn.commit()
            return {"accepted": accepted, "rejected": rejected}
        except Exception as e:
            logger.error(f"batch_push 失败: {e}")
            return {"accepted": 0, "rejected": 0, "error": str(e)}
        finally:
            conn.close()

    def _get_table_columns(self, conn, table: str) -> set:
        """获取服务端表的列名集合（带缓存）"""
        table = ensure_server_table(table)
        cache_key = f"_cols_{table}"
        if not hasattr(self, "_col_cache"):
            self._col_cache = {}
        if cache_key not in self._col_cache:
            try:
                cur = conn.execute(f"PRAGMA table_info({table})")
                self._col_cache[cache_key] = {c[1] for c in cur.fetchall()}
            except Exception:
                self._col_cache[cache_key] = set()
        return self._col_cache[cache_key]

    def _insert_record(self, conn, table: str, user_id: int, record: dict) -> int:
        """将记录插入服务端表（只写服务端表中存在的列），返回 1 表示成功，0 表示失败"""
        record = dict(record)
        record["user_id"] = user_id
        record.pop("pushed_at", None)

        if not record.get("updated_at"):
            record["updated_at"] = now_str()

        # 过滤：只保留服务端表中实际存在的列
        valid_cols = self._get_table_columns(conn, table)
        filtered = {k: v for k, v in record.items() if k in valid_cols}
        if not filtered:
            return 0

        columns = ", ".join(filtered.keys())
        placeholders = ", ".join(["?"] * len(filtered))
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})",
                tuple(filtered.values())
            )
            return 1
        except Exception as e:
            logger.error(f"_insert_record {table} 失败: {e}")
            return 0

    def _update_record(self, conn, table: str, user_id: int,
                       record_id, record: dict) -> int:
        """更新服务端记录（只写服务端表中存在的列），返回 1 表示成功"""
        record = dict(record)
        record.pop("id", None)
        record.pop("pushed_at", None)
        record.pop("user_id", None)

        if not record.get("updated_at"):
            record["updated_at"] = now_str()

        # 过滤：只保留服务端表中实际存在的列
        valid_cols = self._get_table_columns(conn, table)
        filtered = {k: v for k, v in record.items() if k in valid_cols and k != 'id'}
        if not filtered:
            return 0

        set_clause = ", ".join([f"{k} = ?" for k in filtered.keys()])
        values = list(filtered.values()) + [record_id, user_id]
        try:
            conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE id = ? AND user_id = ?",
                tuple(values)
            )
            return 1
        except Exception as e:
            logger.error(f"_update_record {table} 失败: {e}")
            return 0

    def pull_incremental(self, user_id: int, since: str = None) -> dict:
        """
        增量拉取：返回所有业务表自 since 以来的变更数据。

        Args:
            user_id: 当前用户 ID
            since: 增量时间戳（YYYY-MM-DD HH:MM:SS），不传则全量

        Returns:
            {"tables": {table_name: [records], ...}, "server_time": "..."}
        """
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        try:
            tables_result = {}

            # 需同步的表列表（reward_ledger 只 push 不 pull，系统流水不可篡改）
            sync_tables = [table for table in SERVER_TABLES if table not in {"server_reward_ledger", "server_user_wallets"}]

            for server_table in sync_tables:
                if since:
                    rows = conn.execute(
                        f"SELECT * FROM {server_table} WHERE user_id = ? AND updated_at > ?",
                        (user_id, since)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT * FROM {server_table} WHERE user_id = ?",
                        (user_id,)
                    ).fetchall()

                if rows:
                    # 返回时去掉 server_ 前缀，客户端表名不带前缀
                    client_table = client_table_for_server(server_table)
                    tables_result[client_table] = [dict(r) for r in rows]

            return {
                "tables": tables_result,
                "server_time": now_str()
            }
        finally:
            conn.close()
