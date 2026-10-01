# -*- coding: utf-8 -*-
"""任务、习惯与学习最小执行单元的统一奖励摘要。"""
from contextlib import closing
from datetime import datetime, timezone, timedelta
from .reward_period import period_end, period_window


SOURCE_TYPES = {
    "checklist_task": ("task", "checklist_task"),
    "habit": ("habit", "habit"),
    "learning_task": ("learning", "learning_task"),
    "learning_objective": ("learning_objective", "learning_objective"),
}


class SourceRewardError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class SourceRewardService:
    def __init__(self, connect, now_fn=None):
        self._connect = connect
        self._now = now_fn or (lambda: datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"))

    @staticmethod
    def mapping(source_type: str) -> tuple[str, str]:
        try:
            return SOURCE_TYPES[source_type]
        except KeyError as exc:
            raise SourceRewardError("奖励来源类型无效") from exc

    def duplicate_bindings(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT user_id,unlock_source_type,unlock_source_id,COUNT(*) binding_count,
                          GROUP_CONCAT(id) reward_ids
                   FROM server_rewards WHERE is_active=1
                     AND unlock_source_type IN ('checklist_task','habit','learning_task')
                     AND unlock_source_id IS NOT NULL AND unlock_source_id<>''
                   GROUP BY user_id,unlock_source_type,unlock_source_id HAVING COUNT(*)>1"""
            ).fetchall()
            return [dict(row) for row in rows]

    def summary(self, user_id: int, source_type: str, source_id: str) -> dict:
        coin_type, binding_type = self.mapping(source_type)
        source_id = str(source_id or "").strip()
        if not source_id:
            raise SourceRewardError("奖励来源 ID 不能为空")
        with closing(self._connect()) as conn:
            config = conn.execute(
                "SELECT coins,penalty FROM server_reward_config WHERE user_id=? AND item_type=? AND item_id=?",
                (user_id, coin_type, source_id),
            ).fetchone()
            rewards = conn.execute(
                """SELECT r.* FROM server_reward_source_bindings b
                   JOIN server_rewards r ON r.id=b.reward_id
                   WHERE b.user_id=? AND b.source_type=? AND b.source_id=? AND r.is_active=1
                   ORDER BY r.updated_at DESC,r.id""",
                (user_id, binding_type, source_id),
            ).fetchall()
            progress = {}
            fragment_rewards = [str(row["id"]) for row in rewards if str(row["fulfillment_mode"] or "immediate") == "fragment"]
            if fragment_rewards:
                placeholders = ",".join("?" for _ in fragment_rewards)
                now_text = self._now()
                rows = conn.execute(
                    f"""SELECT reward_id,SUM(progress_units-consumed_units) AS active_units,MIN(expires_at) AS earliest_expires_at
                        FROM server_reward_fragments WHERE user_id=? AND reward_id IN ({placeholders})
                        AND status='active' AND expires_at>? GROUP BY reward_id""",
                    (user_id, *fragment_rewards, now_text),
                ).fetchall()
                counts = {str(row["reward_id"]): row for row in rows}
                for reward in rewards:
                    reward_id = str(reward["id"])
                    if reward_id not in fragment_rewards:
                        continue
                    row = counts.get(reward_id)
                    mode, limit = str(reward["inventory_mode"] or "unlimited"), int(reward["inventory_limit"] or 0)
                    used = 0
                    if mode in {"daily", "weekly", "monthly"} and limit > 0:
                        today = now_text[:10]
                        start, end = period_window(today, mode)
                        used = int(conn.execute(
                            """SELECT COUNT(*) count FROM server_reward_ledger WHERE user_id=? AND source_type='reward_buy'
                                AND (source_id LIKE ? OR source_id LIKE ?) AND target_date BETWEEN ? AND ?""",
                            (user_id, f"{reward_id}:%", f"unlock:{reward_id}:%", start, end),
                        ).fetchone()["count"] or 0)
                    units = int(row["active_units"] if row else 0)
                    measure = str(reward["fragment_measure_mode"] or "count")
                    target = int(reward["fragment_target_count"] or 1) if measure == "count" else 100
                    available = int(conn.execute(
                        """SELECT COUNT(*) count FROM server_reward_ledger l WHERE l.user_id=? AND l.source_type='reward_buy'
                           AND (l.source_id LIKE ? OR l.source_id LIKE ?) AND (l.expires_at IS NULL OR l.expires_at>?)
                           AND NOT EXISTS(SELECT 1 FROM server_reward_ledger a WHERE a.user_id=l.user_id
                             AND a.source_type IN ('backpack_use','backpack_discard') AND a.source_id=l.id)""",
                        (user_id, f"{reward_id}:%", f"unlock:{reward_id}:%", now_text),
                    ).fetchone()["count"] or 0)
                    progress[reward_id] = {
                        "active": units, "target": target,
                        "activePieces": units if measure == "count" else None,
                        "targetPieces": target if measure == "count" else None,
                        "activeUnits": units, "targetUnits": target,
                        "percent": min(100, round(units * 100 / target)), "measureMode": measure,
                        "availableItems": available, "periodUsed": used, "periodMode": mode,
                        "expiresAt": period_end(now_text, mode),
                        "inventoryUsed": used, "inventoryLimit": limit or None,
                        "inventoryLimitReached": mode != "unlimited" and limit > 0 and used >= limit,
                        "earliestExpiresAt": row["earliest_expires_at"] if row else None,
                    }
        coins = float(config["coins"]) if config else 0.0
        penalty = float(config["penalty"] if config and config["penalty"] is not None else coins)
        return {"sourceType": source_type, "sourceId": source_id, "coins": coins,
                "penalty": penalty, "itemReward": dict(rewards[0]) if rewards else None,
                "itemRewards": [dict(reward) for reward in rewards], "fragmentProgress": progress}
