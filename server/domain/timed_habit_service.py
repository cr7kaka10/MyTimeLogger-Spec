"""北京时间到点关闭定时习惯；写入与既有失败结算共用事务。"""

from datetime import datetime, timedelta, timezone

from .habit_schedule import scheduled_for_date

BEIJING = timezone(timedelta(hours=8))


class TimedHabitService:
    def __init__(self, transact, habit_domain_service, now_fn=None):
        self._transact = transact
        self._habits = habit_domain_service
        self._now = now_fn or (lambda: datetime.now(BEIJING))

    def run(self, user_id=None):
        now = self._now().astimezone(BEIJING)
        today = now.date().isoformat()
        yesterday = (now.date() - timedelta(days=1)).isoformat()
        minute = now.hour * 60 + now.minute
        changed = set()
        with self._transact() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for day, cutoff in ((yesterday, 1440), (today, minute)):
                rows = conn.execute("""SELECT h.user_id,h.id,h.repeat_rule FROM server_habits h
                    JOIN server_habit_windows w ON w.user_id=h.user_id AND w.habit_id=h.id
                        AND w.effective_from=(SELECT MAX(v.effective_from) FROM server_habit_windows v
                            WHERE v.user_id=h.user_id AND v.habit_id=h.id AND v.effective_from<=?)
                    WHERE (? IS NULL OR h.user_id=?) AND h.source IN ('local','system') AND h.is_active=0
                        AND substr(h.created_at,1,10)<=? AND w.start_minute IS NOT NULL AND w.end_minute<=?
                        AND NOT EXISTS (SELECT 1 FROM server_habit_checkins c WHERE c.user_id=h.user_id
                            AND c.habit_id=h.id AND COALESCE(c.checkin_date,c.date)=? AND c.status IN (1,2))""",
                    (day, user_id, user_id, day, cutoff, day)).fetchall()
                for row in rows:
                    if scheduled_for_date(row["repeat_rule"], day):
                        if self._habits.mark_failed_habit_in_txn(conn, row["user_id"], row["id"], day, automatic=True):
                            changed.add(int(row["user_id"]))
        return changed
