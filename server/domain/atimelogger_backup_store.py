from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


BEIJING_TZ = timezone(timedelta(hours=8))
RETRYABLE_STATES = (
    "pending", "failed", "delete_pending", "start_pending",
    "finalize_pending", "uncertain_start",
)


def beijing_text(value: datetime | None = None) -> str:
    current = value or datetime.now(BEIJING_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING_TZ)
    return current.astimezone(BEIJING_TZ).replace(microsecond=0).isoformat(sep=" ")


class ATimeLoggerBackupStore:
    def __init__(self, connect, now=None):
        self._connect = connect
        self._now = now or (lambda: datetime.now(BEIJING_TZ))

    @staticmethod
    def enqueue_in_tx(conn, user_id: int, session_id: str, now_text: str):
        conn.execute(
            "INSERT INTO server_atimelogger_backups "
            "(user_id,stable_session_id,sync_state,attempts,created_at,updated_at) "
            "VALUES (?,?, 'pending',0,?,?) ON CONFLICT(user_id,stable_session_id) "
            "DO UPDATE SET sync_state='pending',"
            "last_error_code=NULL,last_error_step=NULL,next_retry_at=NULL,updated_at=excluded.updated_at",
            (user_id, str(session_id), now_text, now_text),
        )

    @staticmethod
    def delete_in_tx(conn, user_id: int, session_id: str, now_text: str):
        row = conn.execute(
            "SELECT remote_activity_id,remote_interval_id FROM server_atimelogger_backups "
            "WHERE user_id=? AND stable_session_id=?", (user_id, str(session_id)),
        ).fetchone()
        if not row or not row["remote_activity_id"]:
            conn.execute(
                "DELETE FROM server_atimelogger_backups WHERE user_id=? AND stable_session_id=?",
                (user_id, str(session_id)),
            )
            return
        conn.execute(
            "UPDATE server_atimelogger_backups SET sync_state='delete_pending',last_error_code=NULL,"
            "next_retry_at=NULL,claimed_at=NULL,updated_at=? WHERE user_id=? AND stable_session_id=?",
            (now_text, user_id, str(session_id)),
        )

    def claim_due(self, stale_seconds: int = 120) -> dict | None:
        conn = self._connect()
        now = self._now()
        now_text = beijing_text(now)
        stale_text = beijing_text(now - timedelta(seconds=stale_seconds))
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM server_atimelogger_backups WHERE "
                "((sync_state IN ('pending','failed','delete_pending') AND "
                "(next_retry_at IS NULL OR next_retry_at<=?)) OR "
                "(sync_state IN ('start_pending','finalize_pending','uncertain_start') "
                "AND (next_retry_at IS NULL OR next_retry_at<=?) "
                "AND (claimed_at IS NULL OR claimed_at<=?)) OR "
                "(sync_state='processing' AND claimed_at<=?)) ORDER BY updated_at,id LIMIT 1",
                (now_text, now_text, stale_text, stale_text),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                "UPDATE server_atimelogger_backups SET sync_state='processing',"
                "attempts=attempts+1,claimed_at=?,updated_at=? WHERE id=?",
                (now_text, now_text, row["id"]),
            )
            conn.commit()
            claimed = dict(conn.execute(
                "SELECT * FROM server_atimelogger_backups WHERE id=?", (row["id"],)
            ).fetchone())
            claimed["claimed_from_state"] = row["sync_state"]
            return claimed
        finally:
            conn.close()

    def mark(self, job_id: int, state: str, *, activity_id=None, interval_id=None,
             error_code=None, error_step=None, next_retry_at=None, baseline=None):
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE server_atimelogger_backups SET sync_state=?,remote_activity_id=COALESCE(?,remote_activity_id),"
                "remote_interval_id=COALESCE(?,remote_interval_id),last_error_code=?,last_error_step=?,"
                "running_baseline_json=COALESCE(?,running_baseline_json),next_retry_at=?,"
                "claimed_at=NULL,updated_at=? WHERE id=?",
                (state, activity_id, interval_id, error_code, error_step,
                 json.dumps(sorted(set(baseline))) if baseline is not None else None, next_retry_at,
                 beijing_text(self._now()), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def prepare_start(self, job_id: int, baseline: list[str]):
        self._persist_inflight(
            job_id, "start_pending", baseline=baseline, error_step="activity.final.start",
        )

    def record_started(self, job_id: int, activity_id: str):
        self._persist_inflight(
            job_id, "finalize_pending", activity_id=activity_id,
            error_step="activity.final.stop",
        )

    def _persist_inflight(self, job_id: int, state: str, *, activity_id=None,
                          baseline=None, error_step=None):
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE server_atimelogger_backups SET sync_state=?,"
                "remote_activity_id=COALESCE(?,remote_activity_id),"
                "running_baseline_json=COALESCE(?,running_baseline_json),"
                "last_error_code=NULL,last_error_step=?,updated_at=? WHERE id=?",
                (
                    state, activity_id,
                    json.dumps(sorted(set(baseline))) if baseline is not None else None,
                    error_step, beijing_text(self._now()), job_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def reconcile_user(self, user_id: int, *, cutover: str | None = None,
                       session_ids: list[str] | None = None) -> int:
        ids = [str(value) for value in (session_ids or []) if str(value).strip()]
        if not ids and not cutover:
            return 0
        conn = self._connect()
        now_text = beijing_text(self._now())
        try:
            where = "s.user_id=?"
            params: list[object] = [user_id]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                where += f" AND s.id IN ({placeholders})"
                params.extend(ids)
            else:
                where += " AND s.end_time>=?"
                params.append(str(cutover))
            cur = conn.execute(
                "INSERT INTO server_atimelogger_backups "
                "(user_id,stable_session_id,sync_state,attempts,created_at,updated_at) "
                f"SELECT s.user_id,s.id,'pending',0,?,? FROM server_study_sessions s WHERE {where} "
                "AND NOT EXISTS (SELECT 1 FROM server_atimelogger_backups b "
                "WHERE b.user_id=s.user_id AND b.stable_session_id=s.id)",
                (now_text, now_text, *params),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def retry_user(self, user_id: int) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE server_atimelogger_backups SET sync_state=CASE "
                "WHEN sync_state IN ('start_pending','uncertain_start','finalize_pending') "
                "THEN sync_state ELSE 'pending' END,last_error_code=NULL,last_error_step=NULL,"
                "next_retry_at=NULL,claimed_at=NULL,updated_at=? WHERE user_id=? "
                "AND sync_state IN ('pending','failed','auth_required','unmapped',"
                "'start_pending','uncertain_start','finalize_pending')",
                (beijing_text(self._now()), user_id),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def remove(self, job_id: int):
        conn = self._connect()
        try:
            conn.execute("DELETE FROM server_atimelogger_backups WHERE id=?", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def status(self, user_id: int) -> dict:
        conn = self._connect()
        try:
            counts = {
                row["sync_state"]: row["count"]
                for row in conn.execute(
                    "SELECT sync_state,COUNT(*) count FROM server_atimelogger_backups "
                    "WHERE user_id=? GROUP BY sync_state", (user_id,),
                )
            }
            latest = conn.execute(
                "SELECT stable_session_id,sync_state,last_error_code,last_error_step,updated_at "
                "FROM server_atimelogger_backups WHERE user_id=? ORDER BY updated_at DESC,id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return {
                "pending_count": sum(counts.get(key, 0) for key in (
                    "pending", "processing", "delete_pending", "start_pending",
                    "finalize_pending", "uncertain_start",
                )),
                "failed_count": sum(counts.get(key, 0) for key in ("failed", "auth_required", "unmapped")),
                "latest": dict(latest) if latest else None,
            }
        finally:
            conn.close()

    def failed_details(self, user_id: int, limit: int = 50) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT b.stable_session_id,b.sync_state,b.attempts,b.last_error_code,b.last_error_step,
                          b.next_retry_at,b.updated_at,s.id AS session_id,s.date,s.start_time,s.end_time,
                          s.session_summary,c.name AS category_name
                   FROM server_atimelogger_backups b
                   LEFT JOIN server_study_sessions s ON s.user_id=b.user_id AND s.id=b.stable_session_id
                   LEFT JOIN server_categories c ON c.user_id=s.user_id AND c.id=s.category_id
                   WHERE b.user_id=? AND b.sync_state IN ('failed','auth_required','unmapped')
                   ORDER BY b.updated_at DESC,b.id DESC LIMIT ?""",
                (user_id, max(1, min(int(limit), 50))),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
