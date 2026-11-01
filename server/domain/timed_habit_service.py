"""北京时间到点关闭定时习惯；写入与既有失败结算共用事务。"""

from datetime import datetime, timedelta, timezone

from .habit_schedule import scheduled_for_date
from .exercise_v4_service import DIET_RULE_NAMES, V5_MEAL_RULES, is_exercise_rest_day
from .diet_habit_migration_service import DietHabitMigrationService

BEIJING = timezone(timedelta(hours=8))


class TimedHabitService:
    def __init__(self, transact, habit_domain_service, now_fn=None, wallet=None, record_change=None):
        self._transact = transact
        self._habits = habit_domain_service
        self._now = now_fn or (lambda: datetime.now(BEIJING))
        self._wallet, self._change = wallet, record_change

    def _settle_diet_timeout(self, conn, row, day, now):
        rule = row["id"].removeprefix("diet-v5:")
        if row["source"] != "system" or rule not in V5_MEAL_RULES or self._wallet is None:
            return
        owner = int(row["user_id"])
        ledger_id = f"exercise-diet-penalty:{owner}:{day}:v5:{rule}"
        if conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=? AND id=?", (owner, ledger_id)).fetchone():
            return
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        self._wallet.append_ledger_in_txn(conn, owner, -20, "exercise_diet_penalty", ledger_id,
            f"{DIET_RULE_NAMES[rule]}超时未完成，扣20金币", day, ledger_id, stamp)
        self._wallet.rebuild_wallet_snapshot_in_txn(conn, owner, lambda: stamp)
        self._change(conn, owner, "server_reward_ledger", ledger_id)
        self._change(conn, owner, "server_user_wallets", str(owner))

    def run(self, user_id=None):
        now = self._now().astimezone(BEIJING)
        today = now.date().isoformat()
        yesterday = (now.date() - timedelta(days=1)).isoformat()
        minute = now.hour * 60 + now.minute
        changed = set()
        with self._transact() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for day, cutoff in ((yesterday, 1440), (today, minute)):
                rows = conn.execute("""SELECT h.user_id,h.id,h.source,h.repeat_rule FROM server_habits h
                    JOIN server_habit_windows w ON w.user_id=h.user_id AND w.habit_id=h.id
                        AND w.effective_from=(SELECT MAX(v.effective_from) FROM server_habit_windows v
                            WHERE v.user_id=h.user_id AND v.habit_id=h.id AND v.effective_from<=?)
                    WHERE (? IS NULL OR h.user_id=?) AND h.source IN ('local','system') AND h.is_active=0
                        AND substr(h.created_at,1,10)<=? AND w.start_minute IS NOT NULL AND w.end_minute<=?
                        AND NOT EXISTS (SELECT 1 FROM server_habit_checkins c WHERE c.user_id=h.user_id
                            AND c.habit_id=h.id AND COALESCE(c.checkin_date,c.date)=? AND c.status IN (1,2))""",
                    (day, user_id, user_id, day, cutoff, day)).fetchall()
                for row in rows:
                    if row["source"] == "system" and (not DietHabitMigrationService.active(conn, row["user_id"], day)
                            or is_exercise_rest_day(conn, row["user_id"], "v5", day)):
                        continue
                    if scheduled_for_date(row["repeat_rule"], day):
                        if self._habits.mark_failed_habit_in_txn(conn, row["user_id"], row["id"], day, automatic=True):
                            changed.add(int(row["user_id"]))
                            self._settle_diet_timeout(conn, row, day, now)
        return changed
