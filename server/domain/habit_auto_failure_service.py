"""按北京时间逐日结算本地习惯漏打卡。"""

import json
from datetime import date, datetime, timedelta, timezone

from .habit_schedule import scheduled_for_date

KEY = "habit_auto_failure_progress_v1"
BEIJING = timezone(timedelta(hours=8))


class HabitAutoFailureService:
    def __init__(self, transact, habit_domain_service):
        self._transact = transact
        self._habits = habit_domain_service

    @staticmethod
    def today() -> date:
        return datetime.now(BEIJING).date()

    def _progress(self, conn, user_id: int, today: date) -> dict:
        row = conn.execute("SELECT value FROM server_system_config WHERE user_id=? AND key=?",
                           (user_id, KEY)).fetchone()
        if row:
            return json.loads(row["value"])
        state = {"start": today.isoformat(), "done": (today - timedelta(days=1)).isoformat()}
        conn.execute("INSERT OR IGNORE INTO server_system_config "
                     "(user_id,key,value,value_type,updated_at) VALUES (?,?,?,'json',?)",
                     (user_id, KEY, json.dumps(state), datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")))
        return state

    def run(self, today: date | None = None, user_id: int | None = None) -> int:
        current = today or self.today()
        with self._transact() as conn:
            users = [row["id"] for row in conn.execute(
                "SELECT id FROM users WHERE (? IS NULL OR id=?)", (user_id, user_id))]
        settled = 0
        for owner in users:
            with self._transact() as conn:
                conn.execute("BEGIN IMMEDIATE")
                state = self._progress(conn, owner, current)
            next_day = date.fromisoformat(state["done"]) + timedelta(days=1)
            while next_day < current:
                settled += self._settle_day(owner, next_day, current)
                next_day += timedelta(days=1)
        return settled

    def _settle_day(self, user_id: int, day: date, today: date) -> int:
        target = day.isoformat()
        with self._transact() as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = self._progress(conn, user_id, today)
            if target < state["start"] or target <= state["done"] or day >= today:
                return 0
            habits = conn.execute(
                "SELECT id,repeat_rule FROM server_habits WHERE user_id=? AND source='local' "
                "AND is_active=0 AND substr(created_at,1,10)<=? AND NOT EXISTS "
                "(SELECT 1 FROM server_habit_checkins c WHERE c.user_id=server_habits.user_id "
                "AND c.habit_id=server_habits.id AND COALESCE(c.checkin_date,c.date)=? "
                "AND c.status IN (1,2)) ORDER BY id", (user_id, target, target),
            ).fetchall()
            count = 0
            for habit in habits:
                if scheduled_for_date(habit["repeat_rule"], target):
                    if self._habits.mark_failed_habit_in_txn(conn, user_id, habit["id"], target, automatic=True):
                        count += 1
            state["done"] = target
            conn.execute("UPDATE server_system_config SET value=?,updated_at=? WHERE user_id=? AND key=?",
                         (json.dumps(state), datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S"), user_id, KEY))
            return count
