# -*- coding: utf-8 -*-
"""Explicit per-item reward configuration without schema changes."""

from __future__ import annotations

import sqlite3
from datetime import datetime


class RewardConfigMissingError(RuntimeError):
    """Raised when a rewardable source violates the explicit-config invariant."""


class RewardConfigService:
    """Create and read only explicit reward rules for a single SQLite transaction."""

    TASK_DEFAULT = 0.1
    EXERCISE_DEFAULT = 1.0
    DIFFICULTY_DEFAULTS = {"trivial": 0.5, "easy": 1.0, "medium": 2.5, "hard": 5.0}

    @classmethod
    def defaults(cls, item_type: str, *, difficulty: str | None = None, reward: float | None = None) -> tuple[float, float]:
        if item_type == "task":
            return cls.TASK_DEFAULT, cls.TASK_DEFAULT
        if item_type == "habit":
            amount = cls.DIFFICULTY_DEFAULTS.get(str(difficulty or "easy"), cls.DIFFICULTY_DEFAULTS["easy"])
            return amount, amount
        if item_type == "learning":
            amount = cls.EXERCISE_DEFAULT if reward is None else float(reward)
            return amount, amount
        if item_type == "exercise":
            return cls.EXERCISE_DEFAULT, cls.EXERCISE_DEFAULT
        raise ValueError(f"unsupported reward item type: {item_type}")

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def ensure_item(self, conn: sqlite3.Connection, user_id: int, item_type: str, item_id: str, *, difficulty: str | None = None, reward: float | None = None) -> bool:
        coins, penalty = self.defaults(item_type, difficulty=difficulty, reward=reward)
        cursor = conn.execute(
            """INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,item_type,item_id) DO NOTHING""",
            (user_id, item_type, str(item_id), coins, penalty, self._now()),
        )
        return cursor.rowcount == 1

    def materialize_user(self, conn: sqlite3.Connection, user_id: int) -> int:
        created = 0
        sources = (
            ("task", "SELECT id FROM server_tasks WHERE user_id=?", lambda row: {}),
            ("habit", "SELECT id,difficulty FROM server_habits WHERE user_id=?", lambda row: {"difficulty": row["difficulty"]}),
            ("learning", "SELECT id,reward FROM server_learning_tasks WHERE user_id=?", lambda row: {"reward": row["reward"]}),
            ("exercise", "SELECT id FROM server_exercise_plan_items WHERE user_id=?", lambda row: {}),
        )
        for item_type, query, options in sources:
            for row in conn.execute(query, (user_id,)):
                created += int(self.ensure_item(conn, user_id, item_type, str(row["id"]), **options(row)))
        return created

    @staticmethod
    def require(conn: sqlite3.Connection, user_id: int, item_type: str, item_id: str) -> dict[str, float]:
        row = conn.execute(
            "SELECT coins,penalty FROM server_reward_config WHERE user_id=? AND item_type=? AND item_id=?",
            (user_id, item_type, str(item_id)),
        ).fetchone()
        if row is None:
            raise RewardConfigMissingError(f"reward_config_missing:{item_type}:{item_id}")
        return {"reward": float(row["coins"]), "penalty": float(row["penalty"] if row["penalty"] is not None else row["coins"])}
