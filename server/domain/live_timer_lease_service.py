"""用户级权威当前计时；与普通 SyncWorker/LWW 瞬态状态隔离。"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from .atimelogger_backup_store import ATimeLoggerBackupStore
from .session_business_date import session_business_date


BEIJING_TZ = timezone(timedelta(hours=8))
FOCUS_GROUPS = (
    frozenset(("输入", "输出")),
    frozenset(("副业生产", "副业研发", "副业营销")),
    frozenset(("工作",)),
)
SUMMARY_TAKEOVER_SECONDS = 90
STATE_FIELDS = (
    "user_id", "session_id", "owner_device_id", "category_id", "category_name", "current_note",
    "state", "started_at", "segment_started_at", "active_elapsed_ms",
    "timer_mode", "duration_ms", "pause_count", "revision", "last_command_seq",
    "last_idempotency_key", "last_user_intent_id", "last_heartbeat_at", "updated_at",
    "summary_state", "summary_owner_device_id", "summary_revision", "completed_session_id", "summary_updated_at",
)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=BEIJING_TZ)


def decide_current_state(current: dict | None, operation: str, observed_revision: int) -> str:
    """纯决策：只比较用户级 revision，不比较来源设备。"""
    revision = int(current["revision"]) if current else 0
    if int(observed_revision) != revision:
        return "stale_timer_revision"
    if operation == "start":
        return "accepted"
    if not current or current.get("state") == "stopped":
        return "timer_inactive"
    if operation == "pause" and current.get("state") != "running":
        return "invalid_timer_state"
    if operation == "resume" and current.get("state") != "paused":
        return "invalid_timer_state"
    if operation == "handoff":
        if current.get("state") != "running":
            return "invalid_timer_state"
    return "accepted"


def same_focus_group(left: str, right: str) -> bool:
    groups = FOCUS_GROUPS if os.getenv("MTL_EXTENDED_FOCUS_GROUPS", "1") != "0" else FOCUS_GROUPS[:1]
    return left != right and any(left in group and right in group for group in groups)


def safe_current_state(row, now: datetime | None = None) -> dict | None:
    if row is None:
        return None
    value = {field: row[field] for field in STATE_FIELDS if field in row.keys()}
    value["updated_by_device_id"] = value.get("owner_device_id")
    value["active"] = value.get("state") in {"running", "paused"}
    value["server_time"] = (now or datetime.now(BEIJING_TZ)).replace(microsecond=0).isoformat(sep=" ")
    return value


# 兼容旧测试/导入名称；语义已经不是租约。
safe_lease = safe_current_state


def decide_acquire(current: dict | None, request: dict) -> str:
    decision = decide_current_state(current, "start", int(request.get("observed_revision", current["revision"] if current else 0)))
    return "accepted" if decision == "accepted" else decision


def _result(status: str, state=None, error_code: str | None = None) -> dict:
    value = {"status": status, "state": state, "lease": state}
    if state:
        value["revision"] = state["revision"]
        value["server_time"] = state["server_time"]
    if error_code:
        value["error_code"] = error_code
    return value


class LiveTimerStateService:
    OPERATIONS = {"start", "switch", "handoff", "note", "pause", "resume", "stop",
                  "request_summary", "resolve_summary", "skip_summary", "takeover_summary"}

    def __init__(self, connect, now=None):
        self._connect = connect
        self._now_factory = now or (lambda: datetime.now(BEIJING_TZ))

    def _now(self) -> tuple[datetime, str]:
        value = self._now_factory()
        if value.tzinfo is None:
            value = value.replace(tzinfo=BEIJING_TZ)
        return value, value.replace(microsecond=0).isoformat(sep=" ")

    @staticmethod
    def _elapsed(row, now_value: datetime) -> int:
        elapsed = int(row["active_elapsed_ms"] or 0)
        if row["state"] == "running":
            started = _parse_time(row["segment_started_at"])
            if started:
                elapsed += max(0, int((now_value - started).total_seconds() * 1000))
        return elapsed

    @staticmethod
    def _replay(conn, user_id: int, key: str):
        row = conn.execute(
            "SELECT result_json FROM live_timer_commands WHERE user_id=? AND idempotency_key=?",
            (user_id, key),
        ).fetchone()
        return json.loads(row["result_json"]) if row else None

    @staticmethod
    def _remember(conn, user_id: int, payload: dict, operation: str, result: dict, now_text: str):
        state = result.get("state")
        conn.execute(
            "INSERT INTO live_timer_commands "
            "(user_id,idempotency_key,user_intent_id,session_id,command,revision,result_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                user_id, payload["idempotency_key"], payload["user_intent_id"],
                (state or {}).get("session_id") or payload.get("session_id") or "inactive",
                operation, result.get("revision", payload.get("observed_revision", 0)),
                json.dumps(result, ensure_ascii=False, separators=(",", ":")), now_text,
            ),
        )

    @staticmethod
    def _finalize_segment(conn, user_id: int, row, now_value: datetime, now_text: str, end_revision: int) -> int:
        elapsed = LiveTimerStateService._elapsed(row, now_value)
        closed = conn.execute(
            "SELECT COALESCE(SUM(active_elapsed_ms),0) AS total FROM live_timer_segments "
            "WHERE user_id=? AND session_id=? AND ended_at IS NOT NULL", (user_id, row["session_id"]),
        ).fetchone()["total"]
        open_segment = conn.execute(
            "SELECT segment_id FROM live_timer_segments "
            "WHERE user_id=? AND session_id=? AND ended_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (user_id, row["session_id"]),
        ).fetchone()
        if open_segment:
            conn.execute(
                "UPDATE live_timer_segments SET ended_at=?,active_elapsed_ms=?,end_revision=? WHERE segment_id=?",
                (now_text, max(0, elapsed - int(closed or 0)), end_revision, open_segment["segment_id"]),
            )
        return elapsed

    @staticmethod
    def _start_segment(conn, user_id: int, session_id: str, payload: dict, now_text: str):
        conn.execute(
            "INSERT INTO live_timer_segments "
            "(segment_id,user_id,session_id,category_id,category_name,started_at,ended_at,"
            "active_elapsed_ms,end_revision,created_at) VALUES (?,?,?,?,?,?,NULL,0,NULL,?)",
            (
                str(uuid.uuid4()), user_id, session_id, payload.get("category_id"),
                payload["category_name"], now_text, now_text,
            ),
        )

    @staticmethod
    def _canonical_category_id(conn, user_id: int, category_name: str) -> int | None:
        rows = conn.execute(
            "SELECT id FROM server_categories WHERE user_id=? AND name=?", (user_id, category_name)
        ).fetchall()
        return int(rows[0]["id"]) if len(rows) == 1 else None

    @staticmethod
    def _publish_completed_session(conn, user_id: int, row, payload: dict, now_text: str) -> str:
        session_id = str(row["session_id"])
        total_ms = conn.execute(
            "SELECT COALESCE(SUM(active_elapsed_ms),0) AS total FROM live_timer_segments "
            "WHERE user_id=? AND session_id=?",
            (user_id, session_id),
        ).fetchone()["total"]
        category_id = row["category_id"]
        if category_id is not None and not conn.execute(
            "SELECT 1 FROM server_categories WHERE user_id=? AND id=?",
            (user_id, category_id),
        ).fetchone():
            category_id = None
        start_value = _parse_time(row["started_at"]) or _parse_time(now_text)
        fallback_date = start_value.astimezone(BEIJING_TZ).date().isoformat()
        date_text = session_business_date(row["started_at"], now_text, fallback_date)
        day_name = "星期" + "一二三四五六日"[datetime.fromisoformat(date_text).weekday()]
        seconds = max(0, int(total_ms // 1000))
        conn.execute(
            "INSERT INTO server_study_sessions "
            "(id,user_id,start_time,end_time,net_duration_minutes,net_duration_seconds,date,day_of_week,"
            "pause_count,pause_reasons,session_summary,category_id,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET end_time=excluded.end_time,"
            "net_duration_minutes=excluded.net_duration_minutes,net_duration_seconds=excluded.net_duration_seconds,"
            "pause_count=excluded.pause_count,session_summary=excluded.session_summary,updated_at=excluded.updated_at",
            (
                session_id, user_id, row["started_at"], now_text, seconds / 60, seconds,
                date_text, day_name, int(row["pause_count"] or 0), "[]",
                str(payload.get("session_summary") or row["current_note"] or ""), category_id, now_text,
            ),
        )
        conn.execute(
            "INSERT INTO server_version_counters(user_id,current_version,updated_at) VALUES (?,0,?) "
            "ON CONFLICT(user_id) DO NOTHING",
            (user_id, now_text),
        )
        conn.execute(
            "UPDATE server_version_counters SET current_version=current_version+1,updated_at=? WHERE user_id=?",
            (now_text, user_id),
        )
        version = conn.execute(
            "SELECT current_version FROM server_version_counters WHERE user_id=?", (user_id,)
        ).fetchone()["current_version"]
        conn.execute(
            "INSERT OR IGNORE INTO server_change_log "
            "(user_id,server_version,change_id,device_id,table_name,record_id,entity_type,entity_id,"
            "operation,changed_fields_json,status,error,changed_at,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                user_id, version, f"timer-session:{session_id}", payload.get("device_id"),
                "server_study_sessions", session_id, "study_session", session_id, "upsert",
                "{}", "applied", None, now_text, now_text,
            ),
        )
        ATimeLoggerBackupStore.enqueue_in_tx(conn, user_id, session_id, now_text)
        return session_id

    def read(self, user_id: int) -> dict:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM live_timer_lease WHERE user_id=?", (user_id,)).fetchone()
            state = safe_current_state(row, self._now_factory())
            return _result("active" if state and state["active"] else "stopped", state)
        finally:
            conn.close()

    def command(self, user_id: int, operation: str, payload: dict) -> dict:
        if operation not in self.OPERATIONS:
            raise ValueError("invalid_timer_command")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            replay = self._replay(conn, user_id, payload["idempotency_key"])
            if replay:
                conn.commit()
                return replay
            row = conn.execute("SELECT * FROM live_timer_lease WHERE user_id=?", (user_id,)).fetchone()
            current = safe_current_state(row, self._now_factory())
            decision = decide_current_state(current, operation, int(payload["observed_revision"]))
            if decision != "accepted":
                conn.rollback()
                return _result("conflict", current, decision)
            summary_revision = int(payload.get("summary_revision") if payload.get("summary_revision") is not None else (current or {}).get("summary_revision") or 0)
            if operation == "request_summary" and current.get("summary_state") == "pending":
                conn.rollback()
                return _result("conflict", current, "summary_already_pending")
            if operation in {"resolve_summary", "skip_summary", "takeover_summary"}:
                if current.get("summary_state") != "pending" or summary_revision != int(current.get("summary_revision") or 0):
                    conn.rollback()
                    return _result("conflict", current, "stale_summary_revision")
                if operation != "takeover_summary" and str(current.get("summary_owner_device_id") or "") != str(payload["device_id"]):
                    conn.rollback()
                    return _result("conflict", current, "summary_not_owner")
            if operation in {"start", "switch", "handoff"}:
                category_id = self._canonical_category_id(conn, user_id, str(payload["category_name"]))
                if category_id is None:
                    conn.rollback()
                    return _result("conflict", current, "invalid_timer_category")
                payload = {**payload, "category_id": category_id}
                if operation == "handoff" and not same_focus_group(str(current.get("category_name") or ""), str(payload["category_name"]).strip()):
                    conn.rollback()
                    return _result("conflict", current, "focus_group_mismatch")

            now_value, now_text = self._now()
            next_revision = (int(row["revision"]) if row else 0) + 1
            device_id = str(payload["device_id"])
            completed_session_id = None

            if operation == "start":
                if row and row["state"] != "stopped":
                    self._finalize_segment(conn, user_id, row, now_value, now_text, next_revision)
                    session_id = row["session_id"]
                    started_at = row["started_at"]
                    pause_count = row["pause_count"]
                else:
                    session_id = str(payload.get("session_id") or uuid.uuid4())
                    started_at = now_text
                    pause_count = 0
                values = (
                    session_id, device_id, payload.get("category_id"), payload["category_name"],
                    str(payload.get("current_note") or ""),
                    "running", started_at, now_text, 0, payload.get("timer_mode", "countup"),
                    max(0, int(payload.get("duration_ms") or 0)), pause_count, next_revision,
                    int(payload.get("command_seq") or 0), payload["idempotency_key"],
                    payload["user_intent_id"], now_text, now_text, user_id,
                )
                if row:
                    conn.execute(
                        "UPDATE live_timer_lease SET session_id=?,owner_device_id=?,category_id=?,category_name=?,current_note=?,"
                        "state=?,started_at=?,segment_started_at=?,active_elapsed_ms=?,timer_mode=?,duration_ms=?,"
                        "pause_count=?,revision=?,last_command_seq=?,last_idempotency_key=?,last_user_intent_id=?,"
                        "last_heartbeat_at=?,updated_at=?,summary_state='none',summary_owner_device_id=NULL,"
                        "summary_revision=0,completed_session_id=NULL,summary_updated_at=NULL WHERE user_id=?",
                        values,
                    )
                else:
                    conn.execute(
                        "INSERT INTO live_timer_lease "
                        "(session_id,owner_device_id,category_id,category_name,current_note,state,started_at,segment_started_at,"
                        "active_elapsed_ms,timer_mode,duration_ms,pause_count,revision,last_command_seq,"
                        "last_idempotency_key,last_user_intent_id,last_heartbeat_at,updated_at,user_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        values,
                    )
                self._start_segment(conn, user_id, session_id, payload, now_text)

            elif operation == "handoff":
                elapsed = self._finalize_segment(conn, user_id, row, now_value, now_text, next_revision)
                conn.execute(
                    "UPDATE live_timer_lease SET owner_device_id=?,category_id=?,category_name=?,current_note=?,"
                    "segment_started_at=?,active_elapsed_ms=?,revision=?,last_idempotency_key=?,last_user_intent_id=?,"
                    "last_heartbeat_at=?,updated_at=? WHERE user_id=?",
                    (device_id, payload.get("category_id"), payload["category_name"], str(payload.get("current_note") or ""),
                     now_text, elapsed, next_revision, payload["idempotency_key"], payload["user_intent_id"], now_text, now_text, user_id),
                )
                self._start_segment(conn, user_id, row["session_id"], payload, now_text)

            elif operation == "switch":
                self._finalize_segment(conn, user_id, row, now_value, now_text, next_revision)
                completed_session_id = self._publish_completed_session(
                    conn, user_id, row, {}, now_text,
                )
                next_session_id = str(payload.get("session_id") or uuid.uuid4())
                if next_session_id == str(row["session_id"]):
                    next_session_id = str(uuid.uuid4())
                conn.execute(
                    "UPDATE live_timer_lease SET session_id=?,owner_device_id=?,category_id=?,category_name=?,"
                    "current_note=?,state='running',started_at=?,segment_started_at=?,active_elapsed_ms=0,"
                    "timer_mode=?,duration_ms=?,pause_count=0,revision=?,"
                    "last_idempotency_key=?,last_user_intent_id=?,last_heartbeat_at=?,updated_at=?,"
                    "summary_state='none',summary_owner_device_id=NULL,summary_revision=0,completed_session_id=NULL,summary_updated_at=NULL WHERE user_id=?",
                    (
                        next_session_id, device_id, payload.get("category_id"),
                        payload["category_name"], str(payload.get("current_note") or ""),
                        now_text, now_text,
                        payload.get("timer_mode", "countup"), max(0, int(payload.get("duration_ms") or 0)),
                        next_revision, payload["idempotency_key"], payload["user_intent_id"],
                        now_text, now_text, user_id,
                    ),
                )
                self._start_segment(conn, user_id, next_session_id, payload, now_text)

            elif operation == "request_summary":
                elapsed = self._elapsed(row, now_value)
                conn.execute(
                    "UPDATE live_timer_lease SET owner_device_id=?,state='paused',segment_started_at=NULL,active_elapsed_ms=?,"
                    "summary_state='pending',summary_owner_device_id=?,summary_revision=summary_revision+1,summary_updated_at=?,"
                    "revision=?,last_idempotency_key=?,last_user_intent_id=?,last_heartbeat_at=?,updated_at=? WHERE user_id=?",
                    (device_id, elapsed, device_id, now_text, next_revision, payload["idempotency_key"],
                     payload["user_intent_id"], now_text, now_text, user_id),
                )

            elif operation == "takeover_summary":
                changed_at = _parse_time(current.get("summary_updated_at")) or now_value
                if (now_value - changed_at).total_seconds() < SUMMARY_TAKEOVER_SECONDS:
                    conn.rollback()
                    return _result("conflict", current, "summary_owner_still_active")
                conn.execute(
                    "UPDATE live_timer_lease SET owner_device_id=?,summary_owner_device_id=?,summary_revision=summary_revision+1,"
                    "summary_updated_at=?,revision=?,last_idempotency_key=?,last_user_intent_id=?,last_heartbeat_at=?,updated_at=? WHERE user_id=?",
                    (device_id, device_id, now_text, next_revision, payload["idempotency_key"], payload["user_intent_id"], now_text, now_text, user_id),
                )

            elif operation == "note":
                conn.execute(
                    "UPDATE live_timer_lease SET owner_device_id=?,current_note=?,revision=?,last_idempotency_key=?,"
                    "last_user_intent_id=?,last_heartbeat_at=?,updated_at=? WHERE user_id=?",
                    (
                        device_id, str(payload.get("current_note") or ""), next_revision,
                        payload["idempotency_key"], payload["user_intent_id"], now_text, now_text, user_id,
                    ),
                )

            elif operation == "pause":
                elapsed = self._elapsed(row, now_value)
                conn.execute(
                    "UPDATE live_timer_lease SET owner_device_id=?,state='paused',segment_started_at=NULL,"
                    "active_elapsed_ms=?,pause_count=pause_count+1,revision=?,last_idempotency_key=?,"
                    "last_user_intent_id=?,last_heartbeat_at=?,updated_at=? WHERE user_id=?",
                    (
                        device_id, elapsed, next_revision, payload["idempotency_key"],
                        payload["user_intent_id"], now_text, now_text, user_id,
                    ),
                )

            elif operation == "resume":
                conn.execute(
                    "UPDATE live_timer_lease SET owner_device_id=?,state='running',segment_started_at=?,"
                    "revision=?,last_idempotency_key=?,last_user_intent_id=?,last_heartbeat_at=?,updated_at=? "
                    ",summary_state='none',summary_owner_device_id=NULL,summary_revision=summary_revision+1,summary_updated_at=? WHERE user_id=?",
                    (
                        device_id, now_text, next_revision, payload["idempotency_key"],
                        payload["user_intent_id"], now_text, now_text, now_text, user_id,
                    ),
                )

            elif operation in {"resolve_summary", "skip_summary"}:
                elapsed = self._finalize_segment(conn, user_id, row, now_value, now_text, next_revision)
                final_payload = {**payload, "session_summary": payload.get("session_summary") if operation == "resolve_summary" else ""}
                completed_session_id = self._publish_completed_session(conn, user_id, row, final_payload, now_text)
                conn.execute(
                    "UPDATE live_timer_lease SET owner_device_id=?,state='stopped',segment_started_at=NULL,"
                    "active_elapsed_ms=?,revision=?,last_idempotency_key=?,last_user_intent_id=?,"
                    "last_heartbeat_at=?,updated_at=?,summary_state=?,summary_revision=summary_revision+1,"
                    "completed_session_id=?,summary_updated_at=? WHERE user_id=?",
                    (
                        device_id, elapsed, next_revision, payload["idempotency_key"],
                        payload["user_intent_id"], now_text, now_text,
                        "resolved" if operation == "resolve_summary" else "skipped", completed_session_id, now_text, user_id,
                    ),
                )

            else:
                elapsed = self._finalize_segment(conn, user_id, row, now_value, now_text, next_revision)
                completed_session_id = self._publish_completed_session(conn, user_id, row, payload, now_text)
                summary_state = "resolved" if str(payload.get("session_summary") or "").strip() else "skipped"
                conn.execute(
                    "UPDATE live_timer_lease SET owner_device_id=?,state='stopped',segment_started_at=NULL,"
                    "active_elapsed_ms=?,revision=?,last_idempotency_key=?,last_user_intent_id=?,"
                    "last_heartbeat_at=?,updated_at=?,summary_state=?,summary_owner_device_id=?,"
                    "summary_revision=summary_revision+1,completed_session_id=?,summary_updated_at=? WHERE user_id=?",
                    (device_id, elapsed, next_revision, payload["idempotency_key"], payload["user_intent_id"],
                     now_text, now_text, summary_state, device_id, completed_session_id, now_text, user_id),
                )

            updated = conn.execute("SELECT * FROM live_timer_lease WHERE user_id=?", (user_id,)).fetchone()
            result = _result("accepted", safe_current_state(updated, now_value))
            result["operation"] = operation
            if completed_session_id:
                result["completed_session_id"] = completed_session_id
            self._remember(conn, user_id, payload, operation, result, now_text)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # 旧调用适配到 current-state，便于服务端滚动升级。
    def acquire(self, user_id: int, payload: dict) -> dict:
        payload = {
            **payload,
            "device_id": payload.get("device_id") or payload.get("owner_device_id"),
            "observed_revision": payload.get("observed_revision", self.read(user_id).get("revision", 0)),
            "user_intent_id": payload.get("user_intent_id") or payload["idempotency_key"],
        }
        return self.command(user_id, "start", payload)


LiveTimerLeaseService = LiveTimerStateService
