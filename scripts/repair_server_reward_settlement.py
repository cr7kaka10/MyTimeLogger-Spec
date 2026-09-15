# -*- coding: utf-8 -*-
"""Repair and backfill server-owned reward settlement.

Default mode is dry-run. Use --apply to write changes.
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server.store import ServerSleepStore


START_DATE = "2026-06-01"


def _task_target_date(row) -> str:
    raw = row["updated_at"] or row["due_date"] or START_DATE
    return str(raw)[:10]


def run(db_path: str | None, apply: bool) -> dict:
    store = ServerSleepStore(db_path)
    stats = {
        "fixed_descriptions": 0,
        "fixed_amounts": 0,
        "makeup_titles_fixed": 0,
        "tasks_backfilled": 0,
        "habit_success_backfilled": 0,
        "habit_fail_backfilled": 0,
        "exercise_backfilled": 0,
        "learning_backfilled": 0,
        "wallets_rebuilt": 0,
    }

    with store._transact() as conn:
        users = [row["id"] for row in conn.execute("SELECT id FROM users").fetchall()]

        rows = conn.execute(
            """
            SELECT id, user_id, amount, source_type, source_id, description, target_date
            FROM server_reward_ledger
            WHERE target_date >= ?
            """,
            (START_DATE,),
        ).fetchall()
        for row in rows:
            source_type = row["source_type"] or ""
            item_type = "task"
            title = row["description"] or ""
            success = float(row["amount"]) >= 0
            expected_amount = None
            is_makeup_reward = False
            if source_type in ("habit_checkin", "habit_fail"):
                item_type = "habit"
                habit = conn.execute(
                    "SELECT name, difficulty FROM server_habits WHERE user_id=? AND id=?",
                    (row["user_id"], row["source_id"]),
                ).fetchone()
                title = habit["name"] if habit else title
                success = source_type != "habit_fail"
                expected_amount = None
                if source_type == "habit_checkin" and habit:
                    reward = store.reward_rule_service.calculate_habit_success(
                        row["user_id"], row["source_id"], habit["name"], habit["difficulty"], row["target_date"]
                    )
                    title = reward.title
                    expected_amount = reward.amount
                    is_makeup_reward = reward.is_makeup
                elif source_type == "habit_fail" and habit:
                    reward = store.reward_rule_service.calculate_habit_fail(
                        row["user_id"], row["source_id"], habit["name"], habit["difficulty"]
                    )
                    title = reward.title
                    expected_amount = -abs(reward.amount)
            elif source_type in ("goal_reward", "goal_penalty"):
                item_type = "goal"
                success = source_type != "goal_penalty"
            elif source_type == "reward_buy":
                item_type = "reward"
                success = True
            elif source_type == "exercise_checkin":
                item_type = "exercise"
            elif source_type == "learning_checkin":
                item_type = "learning"
            new_desc = store.reward_settlement_service.format_description(success, item_type, title)
            if new_desc != row["description"]:
                stats["fixed_descriptions"] += 1
                if is_makeup_reward:
                    stats["makeup_titles_fixed"] += 1
                if apply:
                    conn.execute(
                        "UPDATE server_reward_ledger SET description=?, updated_at=? WHERE id=?",
                        (new_desc, store.reward_settlement_service._now(), row["id"]),
                    )
            if expected_amount is not None and abs(float(row["amount"]) - float(expected_amount)) > 0.000001:
                stats["fixed_amounts"] += 1
                if apply:
                    conn.execute(
                        "UPDATE server_reward_ledger SET amount=?, updated_at=? WHERE id=?",
                        (expected_amount, store.reward_settlement_service._now(), row["id"]),
                    )

        for user_id in users:
            task_rows = conn.execute(
                """
                SELECT id, title, due_date, updated_at
                FROM server_tasks
                WHERE user_id=? AND status=2
                  AND COALESCE(substr(updated_at, 1, 10), due_date) >= ?
                """,
                (user_id, START_DATE),
            ).fetchall()
            for task in task_rows:
                stats["tasks_backfilled"] += 1
                if apply:
                    reward = store.reward_rule_service.calculate_task_success(user_id, task["id"], task["title"])
                    store.reward_settlement_service.settle_task_success_in_txn(
                        conn, user_id, task["id"], reward.title, reward.amount, _task_target_date(task)
                    )

            habit_rows = conn.execute(
                """
                SELECT c.habit_id, c.checkin_date, c.status, COALESCE(h.name, c.habit_name, c.habit_id) AS title,
                       COALESCE(h.difficulty, 'easy') AS difficulty
                FROM server_habit_checkins c
                LEFT JOIN server_habits h ON h.user_id=c.user_id AND h.id=c.habit_id
                WHERE c.user_id=? AND c.checkin_date >= ? AND c.status IN (1, 2)
                """,
                (user_id, START_DATE),
            ).fetchall()
            for habit in habit_rows:
                if habit["status"] == 2:
                    stats["habit_success_backfilled"] += 1
                    if apply:
                        reward = store.reward_rule_service.calculate_habit_success(
                            user_id, habit["habit_id"], habit["title"], habit["difficulty"], habit["checkin_date"]
                        )
                        store.reward_settlement_service.settle_habit_success_in_txn(
                            conn, user_id, habit["habit_id"], reward.title, reward.amount, habit["checkin_date"]
                        )
                elif habit["status"] == 1:
                    stats["habit_fail_backfilled"] += 1
                    if apply:
                        reward = store.reward_rule_service.calculate_habit_fail(
                            user_id, habit["habit_id"], habit["title"], habit["difficulty"]
                        )
                        store.reward_settlement_service.settle_habit_fail_in_txn(
                            conn, user_id, habit["habit_id"], reward.title, reward.amount, habit["checkin_date"]
                        )

            exercise_rows = conn.execute(
                """
                SELECT c.id, l.exercise_type, l.date
                FROM server_exercise_checkins c
                JOIN server_exercise_daily_logs l ON l.user_id=c.user_id AND l.id=c.log_id
                WHERE c.user_id=? AND c.status > 0 AND l.date >= ?
                """,
                (user_id, START_DATE),
            ).fetchall()
            for exercise in exercise_rows:
                stats["exercise_backfilled"] += 1
                if apply:
                    reward = store.reward_rule_service.calculate_exercise_success(user_id, exercise["id"], exercise["exercise_type"])
                    store.reward_settlement_service.settle_exercise_success_in_txn(
                        conn, user_id, exercise["id"], reward.title, reward.amount, exercise["date"]
                    )

            learning_rows = conn.execute(
                """
                SELECT id, title, COALESCE(substr(updated_at, 1, 10), ?) AS target_date
                FROM server_learning_tasks
                WHERE user_id=? AND status=2
                  AND COALESCE(substr(updated_at, 1, 10), ?) >= ?
                """,
                (START_DATE, user_id, START_DATE, START_DATE),
            ).fetchall()
            for learning in learning_rows:
                stats["learning_backfilled"] += 1
                if apply:
                    reward = store.reward_rule_service.calculate_learning_success(user_id, learning["id"], learning["title"])
                    store.reward_settlement_service.settle_learning_success_in_txn(
                        conn, user_id, learning["id"], reward.title, reward.amount, learning["target_date"]
                    )

            stats["wallets_rebuilt"] += 1
            if apply:
                store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(conn, user_id, store.reward_settlement_service._now)

        if not apply:
            conn.rollback()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="Path to mtl_server.db")
    parser.add_argument("--apply", action="store_true", help="Write repairs")
    args = parser.parse_args()
    stats = run(args.db, args.apply)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode} reward settlement repair")
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
