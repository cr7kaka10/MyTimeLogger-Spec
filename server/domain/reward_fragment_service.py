# -*- coding: utf-8 -*-
"""服务端权威的奖励碎片发放、失效和自动合成。"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import secrets


class RewardFragmentService:
    def __init__(self, now_fn, reward_wallet_service, record_change_in_txn=None, inventory_available_in_txn=None):
        self._now = now_fn
        self._reward_wallet = reward_wallet_service
        self._record_change_in_txn = record_change_in_txn
        self._inventory_available_in_txn = inventory_available_in_txn

    def _record(self, conn, user_id, fragment_id):
        if self._record_change_in_txn:
            self._record_change_in_txn(conn, user_id, "server_reward_fragments", fragment_id, "upsert", {"id": fragment_id})

    def _record_activity(self, conn, user_id, reward_id, fragment_id, event_type, *, quantity=1, detail=None, occurred_at=None):
        self._reward_wallet.record_backpack_event_in_txn(
            conn, user_id, f"fragment:{fragment_id}", event_type,
            reward_id=reward_id, fragment_id=fragment_id, quantity=quantity, detail=detail,
            event_id=f"fragment-event:{event_type}:{fragment_id}", occurred_at=occurred_at,
        )

    def _expire(self, conn, user_id, reward_id, now_text):
        rows = conn.execute(
            "SELECT id FROM server_reward_fragments WHERE user_id=? AND reward_id=? AND status='active' AND expires_at<=?",
            (user_id, str(reward_id), now_text),
        ).fetchall()
        if not rows:
            return []
        conn.execute(
            "UPDATE server_reward_fragments SET status='expired',updated_at=? WHERE user_id=? AND reward_id=? AND status='active' AND expires_at<=?",
            (now_text, user_id, str(reward_id), now_text),
        )
        for row in rows:
            self._record(conn, user_id, row["id"])
            self._record_activity(conn, user_id, reward_id, row["id"], "fragment_expired", detail="碎片已过期", occurred_at=now_text)
        return [str(row["id"]) for row in rows]

    @staticmethod
    def _expires_at(now_text: str, target: int) -> str:
        start = datetime.fromisoformat(str(now_text)[:19]).replace(hour=0, minute=0, second=0, microsecond=0)
        return (start + timedelta(days=target)).strftime("%Y-%m-%d %H:%M:%S")

    def grant_for_event_in_txn(self, conn, user_id, source_type, source_id, event_key, title, target_date, rewards):
        """发放碎片并在集齐时生成既有 reward_buy 背包事实，返回新流水 ID。"""
        now_text = f"{str(target_date)[:10]} 00:00:00"
        ledger_ids = []
        for reward in rewards:
            if str(reward["fulfillment_mode"] or "immediate") != "fragment":
                continue
            target = max(1, int(reward["fragment_target_count"] or 1))
            version = max(1, int(reward["fragment_rule_version"] or 1))
            self._expire(conn, user_id, reward["id"], now_text)
            fragment_id = hashlib.sha256(
                f"{user_id}:{reward['id']}:{version}:{event_key}".encode("utf-8")
            ).hexdigest()[:32]
            existing = conn.execute("SELECT progress_units FROM server_reward_fragments WHERE id=?", (fragment_id,)).fetchone()
            minimum = reward["drop_min_units"]
            maximum = reward["drop_max_units"]
            if existing:
                progress_units = int(existing["progress_units"])
            elif minimum is None:
                progress_units = max(1, (100 + target - 1) // target)
            elif str(reward["drop_mode"] or "fixed") == "random":
                low, high = sorted((max(1, int(minimum)), max(1, int(maximum if maximum is not None else minimum))))
                progress_units = low + secrets.randbelow(high - low + 1)
            else:
                progress_units = max(1, int(minimum))
            inserted = conn.execute(
                """INSERT OR IGNORE INTO server_reward_fragments
                   (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,progress_units,consumed_units,issued_at,expires_at,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,0,?,?,'active',?,?)""",
                (fragment_id, user_id, str(reward["id"]), source_type, str(source_id), event_key, version,
                 progress_units, now_text, self._expires_at(now_text, target), now_text, now_text),
            ).rowcount > 0
            if inserted:
                self._record(conn, user_id, fragment_id)
                self._record_activity(conn, user_id, reward["id"], fragment_id, "fragment_acquired", detail=f"获得物品进度 {progress_units}%", occurred_at=now_text)
            while True:
                active = conn.execute(
                    """SELECT id,progress_units,consumed_units FROM server_reward_fragments WHERE user_id=? AND reward_id=? AND rule_version=?
                       AND status='active' AND expires_at>? AND progress_units>consumed_units ORDER BY issued_at,id""",
                    (user_id, str(reward["id"]), version, now_text),
                ).fetchall()
                if sum(int(row["progress_units"]) - int(row["consumed_units"] or 0) for row in active) < 100:
                    break
                if self._inventory_available_in_txn and not self._inventory_available_in_txn(conn, user_id, reward, str(target_date)[:10]):
                    break
                remaining, contributions = 100, []
                for row in active:
                    available = int(row["progress_units"]) - int(row["consumed_units"] or 0)
                    take = min(available, remaining)
                    if take:
                        contributions.append((str(row["id"]), int(row["consumed_units"] or 0), take, int(row["progress_units"])))
                        remaining -= take
                    if remaining == 0:
                        break
                batch_id = hashlib.sha256(":".join(f"{item[0]}:{item[1]}:{item[2]}" for item in contributions).encode("utf-8")).hexdigest()[:32]
                for selected_id, consumed, take, awarded in contributions:
                    new_consumed = consumed + take
                    conn.execute("UPDATE server_reward_fragments SET consumed_units=?,status=?,compose_batch_id=CASE WHEN ?='consumed' THEN ? ELSE compose_batch_id END,updated_at=? WHERE user_id=? AND id=?", (new_consumed, "consumed" if new_consumed >= awarded else "active", "consumed" if new_consumed >= awarded else "active", batch_id, now_text, user_id, selected_id))
                    self._record(conn, user_id, selected_id)
                self._record_activity(conn, user_id, reward["id"], batch_id, "fragment_composed", quantity=1, detail=f"自动合成完整物品：{reward['title'] or title}", occurred_at=now_text)
                ledger_id = f"reward:{user_id}:fragment:{reward['id']}:{batch_id}"
                self._reward_wallet.append_ledger_in_txn(conn, user_id, 0, "reward_buy", f"unlock:{reward['id']}:fragment:{batch_id}", f"碎片自动合成: {reward['title'] or title}", str(target_date)[:10], ledger_id)
                ledger_ids.append(ledger_id)
        return ledger_ids

    def revoke_event_in_txn(self, conn, user_id, source_type, source_id, event_key):
        rows = conn.execute(
            """SELECT id,status,reward_id,consumed_units FROM server_reward_fragments WHERE user_id=? AND source_type=? AND source_id=?
               AND completion_event_key=?""",
            (user_id, source_type, str(source_id), event_key),
        ).fetchall()
        if any(str(row["status"]) == "consumed" or int(row["consumed_units"] or 0) > 0 for row in rows):
            raise ValueError("碎片已合成物品，不能撤销对应完成")
        now_text = self._now()
        for row in rows:
            if str(row["status"]) == "active":
                conn.execute("UPDATE server_reward_fragments SET status='revoked',updated_at=? WHERE id=? AND user_id=?", (now_text, row["id"], user_id))
                self._record(conn, user_id, row["id"])
                self._record_activity(conn, user_id, row["reward_id"], row["id"], "fragment_revoked", detail="碎片已撤销", occurred_at=now_text)
        return [str(row["id"]) for row in rows]

    def expire_for_user_in_txn(self, conn, user_id):
        now_text = self._now()
        rows = conn.execute("SELECT DISTINCT reward_id FROM server_reward_fragments WHERE user_id=? AND status='active' AND expires_at<=?", (user_id, now_text)).fetchall()
        expired = []
        for row in rows:
            expired.extend(self._expire(conn, user_id, row["reward_id"], now_text))
        return expired
