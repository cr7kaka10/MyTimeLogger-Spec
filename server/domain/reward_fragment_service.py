# -*- coding: utf-8 -*-
"""服务端权威的奖励碎片发放、失效和自动合成。"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib

from .reward_period import period_end
from .reward_fragment_provenance import RewardFragmentProvenance


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

    def _consume_debt(self, conn, user_id, reward_id, fragment_id, now_text):
        debt = conn.execute("""SELECT id,remaining_units FROM server_reward_fragment_debts
            WHERE user_id=? AND reward_id=? AND remaining_units>0 ORDER BY created_at,id LIMIT 1""",
            (user_id, str(reward_id)),
        ).fetchone()
        if not debt:
            return False
        conn.execute("UPDATE server_reward_fragment_debts SET remaining_units=remaining_units-1,updated_at=? WHERE id=?",
                     (now_text, debt["id"]))
        conn.execute("UPDATE server_reward_fragments SET consumed_units=1,status='revoked',updated_at=? WHERE user_id=? AND id=?",
                     (now_text, user_id, fragment_id))
        self._record(conn, user_id, fragment_id)
        self._record_activity(conn, user_id, reward_id, fragment_id, "fragment_debt_settled",
                              detail="本次碎片用于抵扣已使用商品的撤销欠额", occurred_at=now_text)
        return True

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

    def _compose_available(self, conn, user_id, reward, title, target_date, now_text):
        ledger_ids = []
        target = max(1, int(reward["fragment_target_count"] or 1))
        version = max(1, int(reward["fragment_rule_version"] or 1))
        while True:
            active = conn.execute(
                """SELECT id,progress_units,consumed_units FROM server_reward_fragments
                   WHERE user_id=? AND reward_id=? AND fragment_measure_mode='count'
                     AND status='active' AND expires_at>? AND progress_units>consumed_units
                   ORDER BY issued_at,id""",
                (user_id, str(reward["id"]), now_text),
            ).fetchall()
            if sum(int(row["progress_units"]) - int(row["consumed_units"] or 0) for row in active) < target:
                break
            if self._inventory_available_in_txn and not self._inventory_available_in_txn(conn, user_id, reward, str(target_date)[:10]):
                break
            remaining, contributions = target, []
            for row in active:
                available = int(row["progress_units"]) - int(row["consumed_units"] or 0)
                take = min(available, remaining)
                if take:
                    contributions.append((str(row["id"]), int(row["consumed_units"] or 0), take, int(row["progress_units"])))
                    remaining -= take
                if remaining == 0:
                    break
            batch_id = hashlib.sha256(":".join(f"{item[0]}:{item[1]}:{item[2]}" for item in contributions).encode("utf-8")).hexdigest()[:32]
            ledger_id = f"reward:{user_id}:fragment:{reward['id']}:{batch_id}"
            RewardFragmentProvenance.record_batch(conn, user_id, batch_id, reward["id"], version, "count", target, 1, ledger_id, now_text)
            RewardFragmentProvenance.append_contributions(conn, user_id, batch_id, [(item[0], item[1], item[2]) for item in contributions], now_text)
            for selected_id, consumed, take, awarded in contributions:
                new_consumed = consumed + take
                status = "consumed" if new_consumed >= awarded else "active"
                conn.execute("UPDATE server_reward_fragments SET consumed_units=?,status=?,compose_batch_id=CASE WHEN ?='consumed' THEN ? ELSE compose_batch_id END,updated_at=? WHERE user_id=? AND id=?", (new_consumed, status, status, batch_id, now_text, user_id, selected_id))
                self._record(conn, user_id, selected_id)
            self._record_activity(conn, user_id, reward["id"], batch_id, "fragment_composed", quantity=1, detail=f"自动合成完整物品：{reward['title'] or title}", occurred_at=now_text)
            self._reward_wallet.append_ledger_in_txn(conn, user_id, 0, "reward_buy", f"unlock:{reward['id']}:fragment:{batch_id}", f"碎片自动合成: {reward['title'] or title}", str(target_date)[:10], ledger_id, expires_at=period_end(target_date, str(reward["inventory_mode"] or "unlimited")))
            ledger_ids.append(ledger_id)
        return ledger_ids

    def grant_for_event_in_txn(self, conn, user_id, source_type, source_id, event_key, title, target_date, rewards):
        """发放碎片并在集齐时生成既有 reward_buy 背包事实，返回新流水 ID。"""
        now_text = f"{str(target_date)[:10]} 00:00:00"
        ledger_ids = []
        for reward in rewards:
            if str(reward["fulfillment_mode"] or "immediate") != "fragment":
                continue
            target = max(1, int(reward["fragment_target_count"] or 1))
            version = max(1, int(reward["fragment_rule_version"] or 1))
            # active fragment 商品只有一种新结算语义：一次完成事件固定一枚。
            # 旧 percent/random 字段仅供历史审计，不能继续影响新事实。
            measure = "count"
            self._expire(conn, user_id, reward["id"], now_text)
            fragment_id = hashlib.sha256(
                f"{user_id}:{reward['id']}:{event_key}".encode("utf-8")
            ).hexdigest()[:32]
            existing = conn.execute(
                """SELECT id,progress_units FROM server_reward_fragments
                   WHERE user_id=? AND reward_id=? AND completion_event_key=?
                   ORDER BY created_at,id LIMIT 1""",
                (user_id, str(reward["id"]), event_key),
            ).fetchone()
            if existing:
                fragment_id = str(existing["id"])
                progress_units = int(existing["progress_units"])
            else:
                progress_units = 1
            inserted = conn.execute(
                """INSERT OR IGNORE INTO server_reward_fragments
                   (id,user_id,reward_id,source_type,source_id,completion_event_key,rule_version,fragment_measure_mode,progress_units,consumed_units,issued_at,expires_at,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,0,?,?,'active',?,?)""",
                (fragment_id, user_id, str(reward["id"]), source_type, str(source_id), event_key, version,
                 measure, progress_units, now_text,
                 period_end(target_date, str(reward["inventory_mode"] or "unlimited")) or self._expires_at(now_text, target),
                 now_text, now_text),
            ).rowcount > 0
            if inserted:
                self._record(conn, user_id, fragment_id)
                detail = "获得物品碎片 1 枚"
                self._record_activity(conn, user_id, reward["id"], fragment_id, "fragment_acquired", detail=detail, occurred_at=now_text)
                if self._consume_debt(conn, user_id, reward["id"], fragment_id, now_text):
                    continue
            ledger_ids.extend(self._compose_available(conn, user_id, reward, title, target_date, now_text))
        return ledger_ids

    def compose_for_user_in_txn(self, conn, user_id):
        """补做同一物品跨规则版本已达门槛但尚未执行的按枚合成。"""
        now_text = self._now()
        rewards = conn.execute(
            """SELECT * FROM server_rewards
               WHERE user_id=? AND is_active=1 AND fulfillment_mode='fragment'
               ORDER BY id""",
            (user_id,),
        ).fetchall()
        ledger_ids = []
        for reward in rewards:
            ledger_ids.extend(self._compose_available(
                conn, user_id, reward, reward["title"], now_text[:10], now_text,
            ))
        return ledger_ids

    def revoke_event_in_txn(self, conn, user_id, source_type, source_id, event_key):
        rows = conn.execute(
            """SELECT id,status,reward_id,consumed_units FROM server_reward_fragments WHERE user_id=? AND source_type=? AND source_id=?
               AND completion_event_key=?""",
            (user_id, source_type, str(source_id), event_key),
        ).fetchall()
        now_text = self._now()
        for row in rows:
            if str(row["status"]) == "active":
                conn.execute("UPDATE server_reward_fragments SET status='revoked',updated_at=? WHERE id=? AND user_id=?", (now_text, row["id"], user_id))
                self._record(conn, user_id, row["id"])
                self._record_activity(conn, user_id, row["reward_id"], row["id"], "fragment_revoked", detail="碎片已撤销", occurred_at=now_text)
            elif str(row["status"]) == "consumed" or int(row["consumed_units"] or 0) > 0:
                batch = RewardFragmentProvenance.batch_for_fragment(conn, user_id, row["id"])
                if not batch:
                    raise ValueError("fragment_provenance_missing")
                if batch["output_action"]:
                    debt_id = f"fragment-debt:{user_id}:{row['id']}"
                    conn.execute("""INSERT OR IGNORE INTO server_reward_fragment_debts
                        (id,user_id,reward_id,source_fragment_id,units,remaining_units,created_at,updated_at)
                        VALUES (?,?,?,?,1,1,?,?)""",
                        (debt_id, user_id, str(row["reward_id"]), str(row["id"]), now_text, now_text))
                    conn.execute("UPDATE server_reward_fragments SET status='revoked',updated_at=? WHERE user_id=? AND id=?",
                                 (now_text, user_id, row["id"]))
                    self._record_activity(conn, user_id, row["reward_id"], row["id"], "fragment_debt_created",
                                          detail="完整商品已使用，后续 1 枚碎片先抵扣", occurred_at=now_text)
                    self._record(conn, user_id, row["id"])
                    continue
                self._reward_wallet.remove_ledger_entries_in_txn(
                    conn, user_id, [batch["output_ledger_id"]], backpack_event="fragment_batch_reversed",
                )
                for contribution in batch["contributions"]:
                    conn.execute("""UPDATE server_reward_fragments
                        SET consumed_units=MAX(0,consumed_units-?),
                            status=CASE WHEN progress_units>MAX(0,consumed_units-?) THEN 'active' ELSE 'consumed' END,
                            compose_batch_id=CASE WHEN MAX(0,consumed_units-?)=0 THEN NULL ELSE compose_batch_id END,
                            updated_at=? WHERE user_id=? AND id=?""",
                        (contribution["units"], contribution["units"], contribution["units"], now_text,
                         user_id, contribution["fragment_id"]))
                    self._record(conn, user_id, contribution["fragment_id"])
                conn.execute("UPDATE server_reward_fragments SET status='revoked',updated_at=? WHERE user_id=? AND id=?",
                             (now_text, user_id, row["id"]))
                self._record_activity(conn, user_id, row["reward_id"], row["id"], "fragment_revoked",
                                      detail="已拆分未使用合成商品并撤销碎片", occurred_at=now_text)
                reward = conn.execute("SELECT * FROM server_rewards WHERE user_id=? AND id=?", (user_id, row["reward_id"])).fetchone()
                if reward:
                    self._compose_available(conn, user_id, reward, reward["title"], now_text[:10], now_text)
        return [str(row["id"]) for row in rows]

    def expire_for_user_in_txn(self, conn, user_id):
        now_text = self._now()
        rows = conn.execute("SELECT DISTINCT reward_id FROM server_reward_fragments WHERE user_id=? AND status='active' AND expires_at<=?", (user_id, now_text)).fetchall()
        expired = []
        for row in rows:
            expired.extend(self._expire(conn, user_id, row["reward_id"], now_text))
        return expired
