"""V5 饮食规则按账号在次日切换为系统习惯。"""

from datetime import datetime, timedelta, timezone

from .exercise_v4_service import V5_DIET_POINTS, is_exercise_rest_day

BEIJING = timezone(timedelta(hours=8))
RULES = ("no_sugary_drinks", "no_refined_staples", "no_snacks",
         "breakfast_on_time", "lunch_on_time", "dinner_on_time")
NAMES = ("全天不喝含糖饮料", "全天不吃精米白面", "全天不吃零食",
         "08:30 前按时吃早饭", "12:00–13:30 按时吃午饭", "18:00–19:00 按时吃晚饭")
WINDOWS = ((0, 1440), (0, 1440), (0, 1440), (0, 510), (720, 811), (1080, 1141))


class DietHabitMigrationService:
    def __init__(self, record_change):
        self._change = record_change

    def switch_date(self, conn, user_id, now=None):
        now = (now or datetime.now(BEIJING)).astimezone(BEIJING)
        row = conn.execute("SELECT switch_date FROM server_diet_habit_migrations WHERE user_id=?", (user_id,)).fetchone()
        if row:
            return row["switch_date"]
        day = (now.date() + timedelta(days=1)).isoformat()
        conn.execute("INSERT INTO server_diet_habit_migrations VALUES(?,?,?)",
                     (user_id, day, now.strftime("%Y-%m-%d %H:%M:%S")))
        for rule in RULES:
            conn.execute("INSERT OR IGNORE INTO server_diet_habit_rules VALUES(?,?,?)",
                         (user_id, rule, f"diet-v5:{rule}"))
        return day

    @staticmethod
    def active(conn, user_id, date):
        row = conn.execute("SELECT switch_date FROM server_diet_habit_migrations WHERE user_id=?", (user_id,)).fetchone()
        return bool(row and date >= row["switch_date"])

    def ensure_day(self, conn, user_id, date, now=None):
        if not self.active(conn, user_id, date) or is_exercise_rest_day(conn, user_id, "v5", date):
            return False
        stamp = (now or datetime.now(BEIJING)).astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        switch = conn.execute("SELECT switch_date FROM server_diet_habit_migrations WHERE user_id=?", (user_id,)).fetchone()[0]
        day_codes = {"周一": "MO", "周二": "TU", "周三": "WE", "周四": "TH", "周五": "FR", "六": "SA", "日": "SU"}
        days = [day_codes[row[0]] for row in conn.execute("""SELECT DISTINCT day_key FROM server_exercise_plan_items
            WHERE user_id=? AND plan_version='v5' AND variant IN ('gym','rain') AND is_active=1""", (user_id,)) if row[0] in day_codes]
        if not days:
            return False
        repeat = "RRULE:FREQ=WEEKLY;BYDAY=" + ",".join(sorted(days))
        changed = False
        for rule, name, (start, end) in zip(RULES, NAMES, WINDOWS):
            habit_id = f"diet-v5:{rule}"
            inserted = conn.execute("""INSERT OR IGNORE INTO server_habits
                (id,user_id,name,icon,source,repeat_rule,journal_prompt_enabled,created_at,updated_at)
                VALUES (?, ?, ?, '🥗', 'system', ?, 0, ?, ?)""",
                (habit_id, user_id, name, repeat, stamp, stamp))
            if inserted.rowcount:
                self._change(conn, user_id, "server_habits", habit_id)
                changed = True
            window_id = f"diet-window:{user_id}:{rule}"
            inserted = conn.execute("""INSERT OR IGNORE INTO server_habit_windows
                (id,user_id,habit_id,effective_from,start_minute,end_minute,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)""", (window_id, user_id, habit_id, switch, start, end, stamp, stamp))
            if inserted.rowcount:
                self._change(conn, user_id, "server_habit_windows", window_id)
                changed = True
        return changed

