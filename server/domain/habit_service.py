# -*- coding: utf-8 -*-
"""服务端习惯打卡领域服务。

调用链路：
  REST API(server.py)
    -> ServerSleepStore.checkin_habit/cancel_checkin_habit
      -> HabitDomainService
        -> server_habits / server_habit_checkins / RewardSettlementService.reconcile_habit_success_in_txn

事务边界：
  打卡记录、奖励流水、钱包快照在同一事务里完成；重复打卡依赖 server_habit_checkins 唯一键回滚。
"""

import sqlite3
import uuid


class HabitDomainService:
    """习惯打卡/取消的唯一业务入口。"""

    def __init__(self, transact, now_fn, reward_wallet_service, reward_settlement_service, reward_rule_service, record_change_in_txn=None):
        self._transact = transact
        self._now = now_fn
        self._reward_wallet = reward_wallet_service
        self._reward_settlement = reward_settlement_service
        self._reward_rules = reward_rule_service
        self._record_change_in_txn = record_change_in_txn

    def _record_change(self, conn, user_id, record_id, operation, fields=None):
        if self._record_change_in_txn:
            self._record_change_in_txn(
                conn, user_id, "server_habit_checkins", record_id, operation, fields or {"id": str(record_id)}
            )

    def checkin_habit(self, user_id, habit_id, date_str) -> bool:
        """习惯打卡。

        SQL/事务：
          SELECT server_habits 校验归属
          INSERT server_habit_checkins
          按配置调和稳定的 server_reward_ledger(source_type='habit_checkin')
          UPDATE/INSERT server_user_wallets

        返回：True 表示打卡成功；重复打卡或习惯不存在返回 False。
        """
        try:
            with self._transact() as conn:
                return bool(self.checkin_habit_in_txn(conn, user_id, habit_id, date_str))
        except sqlite3.IntegrityError:
            return False

    def checkin_habit_in_txn(self, conn, user_id, habit_id, date_str) -> str | None:
        """在调用方事务内登记服务端确认的打卡和全部派生奖励事实。"""
        habit = conn.execute(
            "SELECT name, difficulty, icon FROM server_habits WHERE id=? AND user_id=?",
            (habit_id, user_id),
        ).fetchone()
        if not habit:
            return None
        now_ts = self._now()
        checkin_id = uuid.uuid4().hex
        checkin_time = now_ts.split(" ")[1] if " " in now_ts else "12:00:00"
        conn.execute(
            """INSERT INTO server_habit_checkins
               (id,user_id,habit_id,date,checkin_date,checkin_time,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,2,?,?)""",
            (checkin_id, user_id, habit_id, date_str, date_str, checkin_time, now_ts, now_ts),
        )
        reward = self._reward_rules.calculate_habit_success(
            user_id, habit_id, habit["name"], habit["difficulty"] or "easy", date_str, now_ts
        )
        self._reward_settlement.reconcile_habit_success_in_txn(
            conn, user_id, habit_id, reward.title, reward.amount, date_str, now_ts
        )
        event_key = self._reward_settlement.completion_event_key("habit", habit_id, date_str)
        self._reward_settlement.grant_task_unlocks_in_txn(conn, user_id, "habit", habit_id, event_key, habit["name"], date_str)
        self._record_change(conn, user_id, checkin_id, "upsert")
        return checkin_id

    def can_mark_failed_in_txn(self, conn, user_id, habit_id, date_str) -> bool:
        habit = conn.execute("SELECT id FROM server_habits WHERE user_id=? AND id=?", (user_id, habit_id)).fetchone()
        if not habit:
            return False
        checkin = conn.execute(
            "SELECT status FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND COALESCE(checkin_date,date)=?",
            (user_id, habit_id, date_str),
        ).fetchone()
        return not checkin or int(checkin["status"] or 0) != 2 or self.can_cancel_checkin_in_txn(conn, user_id, habit_id, date_str)

    def mark_failed_habit_in_txn(self, conn, user_id, habit_id, date_str) -> str | None:
        """记录失败状态，并用既有奖励规则结算失败流水。"""
        if not self.can_mark_failed_in_txn(conn, user_id, habit_id, date_str):
            return None
        habit = conn.execute(
            "SELECT name,difficulty FROM server_habits WHERE user_id=? AND id=?", (user_id, habit_id)
        ).fetchone()
        if not habit:
            return None
        existing = conn.execute(
            "SELECT id FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND COALESCE(checkin_date,date)=?",
            (user_id, habit_id, date_str),
        ).fetchone()
        event_key = self._reward_settlement.completion_event_key("habit", habit_id, date_str)
        self._reward_settlement.remove_task_unlocks_in_txn(conn, user_id, "habit", habit_id, event_key)
        self._reward_settlement.remove_state_ledgers_in_txn(
            conn, user_id, habit_id, ("habit_checkin", "habit_fail", "habit_cancel"), date_str
        )
        now_ts = self._now()
        checkin_id = existing["id"] if existing else uuid.uuid4().hex
        if existing:
            conn.execute("UPDATE server_habit_checkins SET status=1,updated_at=? WHERE id=?", (now_ts, checkin_id))
        else:
            conn.execute(
                """INSERT INTO server_habit_checkins
                   (id,user_id,habit_id,date,checkin_date,checkin_time,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,1,?,?)""",
                (checkin_id, user_id, habit_id, date_str, date_str, now_ts.split(" ")[1], now_ts, now_ts),
            )
        reward = self._reward_rules.calculate_habit_fail(user_id, habit_id, habit["name"], habit["difficulty"] or "easy")
        self._reward_settlement.settle_habit_fail_in_txn(conn, user_id, habit_id, reward.title, reward.amount, date_str)
        self._record_change(conn, user_id, checkin_id, "upsert")
        return checkin_id

    def cancel_checkin_habit(self, user_id, habit_id, date_str) -> bool:
        """取消习惯打卡。

        SQL/事务：
          SELECT server_habit_checkins 校验目标日期
          DELETE server_habit_checkins
          INSERT server_reward_ledger(source_type='habit_cancel', target_date=目标日期)
          UPDATE/INSERT server_user_wallets

        返回：True 表示撤销成功；目标日期未打卡返回 False。
        """
        with self._transact() as conn:
            return self.cancel_checkin_habit_in_txn(conn, user_id, habit_id, date_str)

    def can_cancel_checkin_in_txn(self, conn, user_id, habit_id, date_str) -> bool:
        """在调用 Provider 前确认目标日期存在可撤销的习惯状态。"""
        checkin = conn.execute(
            "SELECT id FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND COALESCE(checkin_date,date)=?",
            (user_id, habit_id, date_str),
        ).fetchone()
        return checkin is not None

    def cancel_checkin_habit_in_txn(self, conn, user_id, habit_id, date_str) -> bool:
        """在调用方事务内撤销打卡、金币、自动商品及其使用流水。"""
        if not self.can_cancel_checkin_in_txn(conn, user_id, habit_id, date_str):
            return False
        checkin = conn.execute(
            "SELECT id FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND COALESCE(checkin_date,date)=?",
            (user_id, habit_id, date_str),
        ).fetchone()
        if not checkin:
            return False
        habit = conn.execute(
            "SELECT name FROM server_habits WHERE id=? AND user_id=?", (habit_id, user_id)
        ).fetchone()
        if not habit:
            return False
        event_key = self._reward_settlement.completion_event_key("habit", habit_id, date_str)
        self._reward_settlement.revoke_fragments_for_event_in_txn(conn, user_id, "habit", habit_id, event_key)
        self._reward_settlement.remove_task_unlocks_in_txn(
            conn, user_id, "habit", habit_id, event_key, reverse_used=True
        )
        self._reward_settlement.remove_state_ledgers_in_txn(
            conn, user_id, habit_id, ("habit_checkin", "habit_fail", "habit_cancel"), date_str
        )
        conn.execute(
            "DELETE FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND COALESCE(checkin_date,date)=?",
            (user_id, habit_id, date_str),
        )
        self._record_change(conn, user_id, checkin["id"], "delete")
        threshold_rewards = conn.execute(
            """SELECT id,title,inventory_mode,inventory_limit,unlock_required_count,unlock_threshold_started_at
               FROM server_rewards WHERE user_id=? AND is_active=1
                 AND unlock_source_type='habit' AND unlock_source_id=? AND unlock_required_count>1""",
            (user_id, habit_id),
        ).fetchall()
        for reward in threshold_rewards:
            self._reward_settlement.reconcile_habit_unlock_thresholds_in_txn(
                conn, user_id, habit_id, reward, habit["name"], reverse_used=True
            )
        return True
