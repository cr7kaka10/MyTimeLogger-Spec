from __future__ import annotations

from datetime import datetime, timedelta, timezone


BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_text(value: datetime | None = None) -> str:
    current = value or datetime.now(BEIJING_TZ)
    return current.astimezone(BEIJING_TZ).replace(microsecond=0).isoformat(sep=" ")


class HabitCheckinCommandStore:
    """按用户隔离的习惯打卡命令账本，不保存习惯标题或 Provider 凭据。"""

    def __init__(self, connect, now=None):
        self._connect = connect
        self._now = now or (lambda: datetime.now(BEIJING_TZ))

    def get(self, user_id: int, idempotency_key: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM server_habit_checkin_commands WHERE user_id=? AND idempotency_key=?",
                (user_id, str(idempotency_key)),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_or_get(self, user_id: int, idempotency_key: str, habit_id: str, checkin_date: str, desired_status: int) -> tuple[dict, bool]:
        conn = self._connect()
        now_text = beijing_text(self._now())
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM server_habit_checkin_commands WHERE user_id=? AND idempotency_key=?",
                (user_id, str(idempotency_key)),
            ).fetchone()
            if row:
                conn.commit()
                return dict(row), False
            conn.execute(
                """INSERT INTO server_habit_checkin_commands
                   (user_id,idempotency_key,habit_id,checkin_date,desired_status,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,'pending',?,?)""",
                (user_id, str(idempotency_key), str(habit_id), str(checkin_date), int(desired_status), now_text, now_text),
            )
            row = conn.execute(
                "SELECT * FROM server_habit_checkin_commands WHERE user_id=? AND idempotency_key=?",
                (user_id, str(idempotency_key)),
            ).fetchone()
            conn.commit()
            return dict(row), True
        finally:
            conn.close()

    def begin_attempt(self, user_id: int, idempotency_key: str) -> dict | None:
        return self._update(user_id, idempotency_key, "attempts=attempts+1,error_code=NULL,updated_at=?", (beijing_text(self._now()),))

    def mark(self, user_id: int, idempotency_key: str, status: str, *, error_code: str | None = None) -> dict | None:
        conn = self._connect()
        try:
            self.mark_in_txn(conn, user_id, idempotency_key, status, error_code=error_code)
            conn.commit()
        finally:
            conn.close()
        return self.get(user_id, idempotency_key)

    def mark_in_txn(self, conn, user_id: int, idempotency_key: str, status: str, *, error_code: str | None = None) -> None:
        now_text = beijing_text(self._now())
        provider_confirmed_at = now_text if status in {"provider_confirmed", "confirmed"} else None
        confirmed_at = now_text if status == "confirmed" else None
        conn.execute(
            """UPDATE server_habit_checkin_commands
               SET status=?, error_code=?, provider_confirmed_at=COALESCE(?, provider_confirmed_at),
                   confirmed_at=COALESCE(?, confirmed_at), updated_at=?
               WHERE user_id=? AND idempotency_key=?""",
            (status, error_code, provider_confirmed_at, confirmed_at, now_text, user_id, str(idempotency_key)),
        )

    def _update(self, user_id: int, idempotency_key: str, fields: str, params: tuple) -> dict | None:
        conn = self._connect()
        try:
            cur = conn.execute(
                f"UPDATE server_habit_checkin_commands SET {fields} WHERE user_id=? AND idempotency_key=?",
                (*params, user_id, str(idempotency_key)),
            )
            conn.commit()
            return self.get(user_id, idempotency_key) if cur.rowcount else None
        finally:
            conn.close()
