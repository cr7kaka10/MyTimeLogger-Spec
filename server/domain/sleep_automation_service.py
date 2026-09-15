# -*- coding: utf-8 -*-
"""北京时间睡眠自动化的幂等事实写入。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


BEIJING = timezone(timedelta(hours=8))
STEP_TIMER_SWITCH = "timer_switch"
STEP_FULL_ANALYSIS = "full_analysis"
STEP_BEDTIME_DEADLINE = "bedtime_coin_deadline"


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def due_step(now: datetime) -> str | None:
    local = now.astimezone(BEIJING)
    minute = local.hour * 60 + local.minute
    if minute == 12 * 60:
        return STEP_BEDTIME_DEADLINE
    if minute == 22 * 60 + 30:
        return STEP_TIMER_SWITCH
    if minute == 22 * 60 + 35:
        return STEP_FULL_ANALYSIS
    return None


class SleepAutomationService:
    def __init__(self, transact, record_change, now_fn=beijing_now):
        self._transact = transact
        self._record_change = record_change
        self._now = now_fn

    def claim_step(self, user_id: int, sleep_date: str, step: str) -> bool:
        now = self._now().astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        with self._transact() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO server_sleep_automation_runs
                   (id,user_id,sleep_date,step,status,detail,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (f"sleep-run:{user_id}:{sleep_date}:{step}", user_id, sleep_date, step,
                 "running", None, now, now),
            )
            return cursor.rowcount == 1

    def create_timer_switch(self, user_id: int, sleep_date: str) -> dict | None:
        now = self._now().astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        command_id = f"sleep-command:{user_id}:{sleep_date}:timer-switch"
        notification_id = f"sleep-notification:{user_id}:{sleep_date}:sleep-time"
        with self._transact() as conn:
            claimed = conn.execute(
                """INSERT OR IGNORE INTO server_sleep_automation_runs
                   (id,user_id,sleep_date,step,status,detail,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (f"sleep-run:{user_id}:{sleep_date}:{STEP_TIMER_SWITCH}", user_id, sleep_date,
                 STEP_TIMER_SWITCH, "running", None, now, now),
            ).rowcount == 1
            if not claimed:
                prior = conn.execute(
                    "SELECT status FROM server_sleep_automation_runs WHERE user_id=? AND sleep_date=? AND step=?",
                    (user_id, sleep_date, STEP_TIMER_SWITCH),
                ).fetchone()
                if not prior or prior["status"] != "error":
                    return None
                conn.execute(
                    "UPDATE server_sleep_automation_runs SET status='running',detail=NULL,updated_at=? WHERE user_id=? AND sleep_date=? AND step=?",
                    (now, user_id, sleep_date, STEP_TIMER_SWITCH),
                )
                command_row = conn.execute(
                    "SELECT id,scheduled_at,status FROM server_sleep_automation_commands WHERE user_id=? AND sleep_date=? AND command_type='switch_to_sleep'",
                    (user_id, sleep_date),
                ).fetchone()
                if not command_row:
                    return None
                return {"command": {"id": command_row["id"], "sleep_date": sleep_date,
                                    "command_type": "switch_to_sleep", "scheduled_at": command_row["scheduled_at"],
                                    "status": command_row["status"]}}
            command = {"id": command_id, "sleep_date": sleep_date, "command_type": "switch_to_sleep",
                       "scheduled_at": f"{sleep_date} 22:30:00", "status": "pending"}
            notification = {"id": notification_id, "sleep_date": sleep_date, "event_type": "sleep_time",
                            "title": "睡眠时间到", "body": "睡眠时间到", "status": "pending"}
            conn.execute(
                """INSERT INTO server_sleep_automation_commands
                   (id,user_id,sleep_date,command_type,scheduled_at,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (command_id, user_id, sleep_date, command["command_type"], command["scheduled_at"], "pending", now, now),
            )
            conn.execute(
                """INSERT INTO server_sleep_notifications
                   (id,user_id,sleep_date,event_type,title,body,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (notification_id, user_id, sleep_date, notification["event_type"], notification["title"],
                 notification["body"], "pending", now, now),
            )
            self._record_change(conn, user_id, "server_sleep_automation_commands", command_id, "upsert", command)
            self._record_change(conn, user_id, "server_sleep_notifications", notification_id, "upsert", notification)
            return {"command": command, "notification": notification}

    def finish_timer_switch(self, user_id: int, sleep_date: str, status: str, detail: str | None = None) -> None:
        now = self._now().astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        with self._transact() as conn:
            conn.execute(
                "UPDATE server_sleep_automation_runs SET status=?,detail=?,updated_at=? WHERE user_id=? AND sleep_date=? AND step=?",
                (status, detail, now, user_id, sleep_date, STEP_TIMER_SWITCH),
            )

    def claim_full_analysis(self, user_id: int, sleep_date: str) -> bool:
        if self.claim_step(user_id, sleep_date, STEP_FULL_ANALYSIS):
            return True
        now = self._now().astimezone(BEIJING)
        cutoff = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        with self._transact() as conn:
            row = conn.execute(
                "SELECT status,detail,updated_at FROM server_sleep_automation_runs WHERE user_id=? AND sleep_date=? AND step=?",
                (user_id, sleep_date, STEP_FULL_ANALYSIS),
            ).fetchone()
            if not row or row["status"] != "waiting_for_records" or row["updated_at"] > cutoff:
                return False
            try:
                attempts = int(json.loads(row["detail"] or "{}").get("attempts", 1))
            except (TypeError, ValueError, json.JSONDecodeError):
                attempts = 1
            if attempts >= 8:
                return False
            return conn.execute(
                "UPDATE server_sleep_automation_runs SET status='running',updated_at=? WHERE user_id=? AND sleep_date=? AND step=? AND status='waiting_for_records'",
                (now.strftime("%Y-%m-%d %H:%M:%S"), user_id, sleep_date, STEP_FULL_ANALYSIS),
            ).rowcount == 1

    def finish_step(self, user_id: int, sleep_date: str, step: str, status: str, detail: str | None = None) -> None:
        now = self._now().astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        with self._transact() as conn:
            conn.execute(
                "UPDATE server_sleep_automation_runs SET status=?,detail=?,updated_at=? WHERE user_id=? AND sleep_date=? AND step=?",
                (status, detail, now, user_id, sleep_date, step),
            )

    def finish_full_analysis(self, user_id: int, sleep_date: str, status: str, detail: str | None = None) -> None:
        now = self._now().astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        with self._transact() as conn:
            if status == "waiting_for_records":
                row = conn.execute(
                    "SELECT detail FROM server_sleep_automation_runs WHERE user_id=? AND sleep_date=? AND step=?",
                    (user_id, sleep_date, STEP_FULL_ANALYSIS),
                ).fetchone()
                try:
                    previous = json.loads(row["detail"] or "{}") if row else {}
                    waiting = json.loads(detail or "{}")
                    waiting["attempts"] = int(previous.get("attempts", 0)) + 1
                    detail = json.dumps(waiting)
                except (TypeError, ValueError, json.JSONDecodeError):
                    detail = json.dumps({"reason": "insufficient_time_records", "attempts": 1})
            conn.execute(
                "UPDATE server_sleep_automation_runs SET status=?,detail=?,updated_at=? WHERE user_id=? AND sleep_date=? AND step=?",
                (status, detail, now, user_id, sleep_date, STEP_FULL_ANALYSIS),
            )
            if status != "done":
                return
            event_type = "analysis_done"
            notification_id = f"sleep-notification:{user_id}:{sleep_date}:{event_type}"
            conn.execute(
                """INSERT OR IGNORE INTO server_sleep_notifications
                   (id,user_id,sleep_date,event_type,title,body,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (notification_id, user_id, sleep_date, event_type, "完整睡眠报告已生成", "完整睡眠报告已生成", "pending", now, now),
            )
            self._record_change(conn, user_id, "server_sleep_notifications", notification_id, "upsert", {
                "id": notification_id, "sleep_date": sleep_date, "event_type": event_type,
                "title": "完整睡眠报告已生成", "body": "完整睡眠报告已生成", "status": "pending",
            })
