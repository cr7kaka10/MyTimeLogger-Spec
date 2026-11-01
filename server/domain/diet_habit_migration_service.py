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

