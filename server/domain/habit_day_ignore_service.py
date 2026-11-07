"""同账号、习惯、北京时间日期唯一的忽略命令。"""

from datetime import date
import re


class HabitDayIgnoreService:
    def __init__(self, transact, record_change, now_fn):
        self.transact, self.record_change, self.now_fn = transact, record_change, now_fn

    def set(self, user_id: int, habit_id: str, day: str, command_id: str, ignored: bool) -> dict:
        if not habit_id or not command_id or len(command_id) > 128 or not isinstance(ignored, bool) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError("invalid_ignore_command")
        try:
            requested = date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError("invalid_ignore_date") from exc
        now = self.now_fn()
        if requested > now.date():
            raise ValueError("future_ignore_date")
        stamp, record_id = now.strftime("%Y-%m-%d %H:%M:%S"), f"habit-ignore:{user_id}:{habit_id}:{day}"
        with self.transact() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute("SELECT habit_id,date,is_ignored FROM server_habit_day_ignore_commands WHERE user_id=? AND command_id=?", (user_id, command_id)).fetchone()
            if prior and (prior["habit_id"], prior["date"], bool(prior["is_ignored"])) != (habit_id, day, ignored):
                raise ValueError("ignore_command_conflict")
            if prior:
                state = conn.execute("SELECT is_ignored FROM server_habit_day_ignores WHERE user_id=? AND habit_id=? AND date=?", (user_id, habit_id, day)).fetchone()
                return {"status": "confirmed", "habit_id": habit_id, "date": day, "is_ignored": bool(state["is_ignored"]), "idempotency_key": command_id}
            habit = conn.execute("SELECT 1 FROM server_habits WHERE user_id=? AND id=? AND is_active=0", (user_id, habit_id)).fetchone()
            if not habit:
                raise ValueError("habit_not_found")
            window = conn.execute("SELECT start_minute FROM server_habit_windows WHERE user_id=? AND habit_id=? AND effective_from<=? ORDER BY effective_from DESC LIMIT 1", (user_id, habit_id, day)).fetchone()
            if window and window["start_minute"] is not None:
                raise ValueError("timed_habit_cannot_ignore")
            current = conn.execute("SELECT is_ignored FROM server_habit_day_ignores WHERE user_id=? AND habit_id=? AND date=?", (user_id, habit_id, day)).fetchone()
            if not prior and (current is None or bool(current["is_ignored"]) != ignored):
                conn.execute("""INSERT INTO server_habit_day_ignores(id,user_id,habit_id,date,is_ignored,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,habit_id,date) DO UPDATE SET is_ignored=excluded.is_ignored,updated_at=excluded.updated_at""",
                    (record_id, user_id, habit_id, day, int(ignored), stamp, stamp))
                self.record_change(conn, user_id, "server_habit_day_ignores", record_id, "upsert", {"is_ignored": int(ignored)})
            if not prior:
                conn.execute("INSERT INTO server_habit_day_ignore_commands VALUES(?,?,?,?,?,?)", (user_id, command_id, habit_id, day, int(ignored), stamp))
            state = conn.execute("SELECT is_ignored FROM server_habit_day_ignores WHERE user_id=? AND habit_id=? AND date=?", (user_id, habit_id, day)).fetchone()
        return {"status": "confirmed", "habit_id": habit_id, "date": day, "is_ignored": bool(state["is_ignored"]), "idempotency_key": command_id}
