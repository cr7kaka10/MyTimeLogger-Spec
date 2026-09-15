from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_text(value: datetime | None = None) -> str:
    current = value or datetime.now(BEIJING_TZ)
    return current.astimezone(BEIJING_TZ).replace(microsecond=0).isoformat(sep=" ")


class TickTickTaskOperationStore:
    """User-scoped, durable idempotency ledger for external task commands."""

    def __init__(self, connect, now=None):
        self._connect = connect
        self._now = now or (lambda: datetime.now(BEIJING_TZ))

    def get(self, user_id: int, request_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM server_ticktick_task_operations WHERE user_id=? AND request_id=?", (user_id, str(request_id))).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_or_get(self, user_id: int, request_id: str, operation: str, *, task_id=None, project_id=None, title_fingerprint=None, expected_fingerprint=None, patch_fingerprint=None) -> tuple[dict, bool]:
        conn = self._connect(); now_text = beijing_text(self._now())
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM server_ticktick_task_operations WHERE user_id=? AND request_id=?", (user_id, str(request_id))).fetchone()
            if row:
                conn.commit()
                existing = dict(row)
                requested = (operation, task_id, project_id, title_fingerprint, expected_fingerprint, patch_fingerprint)
                keys = ("operation", "task_id", "project_id", "title_fingerprint", "expected_fingerprint", "patch_fingerprint")
                if any(value is not None and existing.get(key) != value for key, value in zip(keys, requested)):
                    return {"request_id": str(request_id), "status": "failed", "error_code": "request_id_reused_with_different_patch"}, False
                return existing, False
            conn.execute(
                "INSERT INTO server_ticktick_task_operations (user_id,request_id,operation,task_id,project_id,title_fingerprint,expected_fingerprint,patch_fingerprint,status,attempts,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,'pending',0,?,?)",
                (user_id, str(request_id), operation, task_id, project_id, title_fingerprint, expected_fingerprint, patch_fingerprint, now_text, now_text),
            )
            row = conn.execute("SELECT * FROM server_ticktick_task_operations WHERE user_id=? AND request_id=?", (user_id, str(request_id))).fetchone()
            conn.commit()
            return dict(row), True
        finally:
            conn.close()

    def begin_attempt(self, user_id: int, request_id: str) -> dict | None:
        return self._update(user_id, request_id, "attempts=attempts+1,updated_at=?", (beijing_text(self._now()),))

    def mark(self, user_id: int, request_id: str, status: str, *, result_task_id=None, project_id=None, http_status=None, error_code=None) -> dict | None:
        confirmed_at = beijing_text(self._now()) if status == "confirmed" else None
        return self._update(user_id, request_id, "status=?,result_task_id=COALESCE(?,result_task_id),project_id=COALESCE(?,project_id),http_status=?,error_code=?,confirmed_at=COALESCE(?,confirmed_at),updated_at=?", (status, result_task_id, project_id, http_status, error_code, confirmed_at, beijing_text(self._now())))

    def _update(self, user_id: int, request_id: str, fields: str, params: tuple) -> dict | None:
        conn = self._connect()
        try:
            cur = conn.execute(f"UPDATE server_ticktick_task_operations SET {fields} WHERE user_id=? AND request_id=?", (*params, user_id, str(request_id)))
            conn.commit()
            return self.get(user_id, request_id) if cur.rowcount else None
        finally:
            conn.close()
