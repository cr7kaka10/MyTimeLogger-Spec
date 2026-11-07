"""精确撤销 2026-09-24 启动迁移误生成的闪念任务。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Callable


POLLUTED_FLASH_TASKS = (
    {"task_id": "local_11cd3f5fc0765135b4597c8a3f919d73", "flash_card_id": "ebf3b013-5836-45d4-8543-fa9e8ccf6ab5", "recommendation_id": "87e9227b-f786-5794-ad07-f328bb467a00"},
    {"task_id": "local_122825122421560497b97927dbd89beb", "flash_card_id": "e7799169-bab3-4e62-a3b5-1dd8796a6410", "recommendation_id": "d0e5cd0d-c6dc-565e-9e79-a64b4905e10b"},
    {"task_id": "local_5bf788aab5825bd09737a02f9ebc6273", "flash_card_id": "a6e206ab-ff24-46da-8b4e-663269bcb2b4", "recommendation_id": "d7d579d3-4f79-5e1a-9045-c1fe6157dfc5"},
    {"task_id": "local_816780a447355b28be0c8ede408286bc", "flash_card_id": "3f9b22ec-d527-44c6-9340-3080c0752b64", "recommendation_id": "5d162119-9f02-562a-a4f0-b4d067eaea85"},
    {"task_id": "local_8515c69d2184595aa0615be5b488facc", "flash_card_id": "b48dea1b-bdfa-4947-aee9-05ac7dbc0947", "recommendation_id": "7e771aad-4598-5b3f-88ea-bd5e54a505d9"},
    {"task_id": "local_8fed6131630154019d28af1d15e9e36c", "flash_card_id": "3b9bb77a-851a-4997-8f68-032293f8917d", "recommendation_id": "17ff8835-5900-569c-a37b-2f27f0c89712"},
    {"task_id": "local_cacdd035dcc254b7aa55ad1cfe20b539", "flash_card_id": "eb2f28d3-df13-4f8e-b0a8-8a0af61bcf19", "recommendation_id": "2892638a-cc27-5591-88d3-f6c5f1fed865"},
)


class FlashTaskPollutionRepairService:
    def __init__(self, connect: Callable[[], sqlite3.Connection], record_change: Callable):
        self.connect = connect
        self.record_change = record_change

    @staticmethod
    def _inspect_item(conn: sqlite3.Connection, item: dict) -> tuple[str, int | None, list[str]]:
        task_rows = conn.execute("SELECT * FROM server_tasks WHERE id=?", (item["task_id"],)).fetchall()
        rec_rows = conn.execute("SELECT * FROM server_flash_task_recommendations WHERE id=?", (item["recommendation_id"],)).fetchall()
        errors: list[str] = []
        if len(task_rows) != 1 or len(rec_rows) != 1:
            return "invalid", None, ["task_or_recommendation_count"]
        task, rec = task_rows[0], rec_rows[0]
        user_id = int(task["user_id"])
        try:
            raw = json.loads(task["raw_json"] or "{}")
        except (TypeError, ValueError):
            raw = {}
        checks = {
            "user": int(rec["user_id"]) == user_id,
            "source": task["source"] == "local",
            "due_date": str(task["due_date"] or "") == "2026-09-24",
            "flash_link": rec["flash_card_id"] == item["flash_card_id"] == raw.get("flash_card_id"),
            "recommendation_link": raw.get("recommendation_id") == item["recommendation_id"],
            "flash_exists": bool(conn.execute("SELECT 1 FROM server_flash_cards WHERE id=? AND user_id=? AND deleted_at IS NULL", (item["flash_card_id"], user_id)).fetchone()),
            "reward_config": conn.execute("SELECT COUNT(*) FROM server_reward_config WHERE user_id=? AND item_type='task' AND item_id=?", (user_id, item["task_id"])).fetchone()[0] == 1,
            "no_reward_ledger": conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=? AND source_id=?", (user_id, item["task_id"])).fetchone()[0] == 0,
        }
        errors.extend(key for key, valid in checks.items() if not valid)
        active = task["deleted_at"] is None and rec["status"] == "added" and rec["local_task_id"] == item["task_id"] and rec["creation_mode"] == "direct"
        repaired = task["deleted_at"] is not None and rec["status"] == "pending" and rec["local_task_id"] is None
        if not active and not repaired:
            errors.append("lifecycle_state")
        return ("active" if active else "repaired" if repaired else "invalid"), user_id, errors

    def preflight(self) -> dict:
        with closing(self.connect()) as conn:
            states, mismatches = [], {}
            for item in POLLUTED_FLASH_TASKS:
                state, _user_id, errors = self._inspect_item(conn, item)
                states.append(state)
                if errors:
                    mismatches[item["task_id"]] = errors
            status = "ready" if states and all(state == "active" for state in states) else "already_repaired" if states and all(state == "repaired" for state in states) else "blocked"
            return {"status": status, "tasks": len(states), "mismatches": mismatches}

    def repair(self) -> dict:
        with closing(self.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            states, users, mismatches = [], {}, {}
            for item in POLLUTED_FLASH_TASKS:
                state, user_id, errors = self._inspect_item(conn, item)
                states.append(state)
                users[item["task_id"]] = user_id
                if errors:
                    mismatches[item["task_id"]] = errors
            if all(state == "repaired" for state in states):
                conn.rollback()
                return {"status": "already_repaired", "tasks": 7, "recommendations": 7}
            if mismatches or not all(state == "active" for state in states):
                conn.rollback()
                return {"status": "blocked", "mismatches": mismatches}
            try:
                now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                for item in POLLUTED_FLASH_TASKS:
                    user_id = int(users[item["task_id"]])
                    conn.execute("UPDATE server_tasks SET deleted_at=?,updated_at=? WHERE user_id=? AND id=?", (now, now, user_id, item["task_id"]))
                    self.record_change(conn, user_id, "server_tasks", item["task_id"], "delete", {"id": item["task_id"], "deleted_at": now, "repair": "chg-20260924-004"})
                    conn.execute("UPDATE server_flash_task_recommendations SET status='pending',local_task_id=NULL,updated_at=? WHERE user_id=? AND id=?", (now, user_id, item["recommendation_id"]))
                    self.record_change(conn, user_id, "server_flash_task_recommendations", item["recommendation_id"], "upsert", {"id": item["recommendation_id"], "status": "pending", "local_task_id": None})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return {"status": "repaired", "tasks": 7, "recommendations": 7}
