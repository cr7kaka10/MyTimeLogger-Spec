# -*- coding: utf-8 -*-
"""奖励流水与钱包快照领域服务。

调用链路：
  REST API(server.py) / SyncHub(sync_hub.py)
    -> ServerSleepStore 兼容门面(store.py)
      -> RewardWalletService
        -> SQLite: server_reward_ledger / server_user_wallets / server_external_rewards / server_rewards

事务边界：
  所有“流水写入 + 钱包快照”必须在同一个 conn 事务里完成；异常由 store._transact 统一回滚。

返回数据：
  查询类返回 float/list/dict；写入类返回 bool 或 (bool, message)，保持旧 store API 兼容。
"""

import json
import re
import uuid

try:
    from ..statistics_start_date import is_user_statistics_date_eligible
except ImportError:
    from statistics_start_date import is_user_statistics_date_eligible


class RewardWalletService:
    """奖励流水、钱包快照和背包使用的唯一业务入口。"""

    def __init__(self, connect, transact, now_fn, update_wallet_in_txn, record_change_in_txn=None):
        self._connect = connect
        self._transact = transact
        self._now = now_fn
        self._update_wallet_in_txn = update_wallet_in_txn
        self._record_change_in_txn = record_change_in_txn

    def _record_change(self, conn, user_id, table_name, record_id, operation, fields=None):
        if self._record_change_in_txn:
            self._record_change_in_txn(conn, user_id, table_name, record_id, operation, fields or {})

    def _ledger_sum_in_txn(self, conn, user_id) -> float:
        row = conn.execute(
            "SELECT SUM(amount) AS total FROM server_reward_ledger WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return float(row["total"]) if row and row["total"] is not None else 0.0

    @staticmethod
    def rebuild_wallet_snapshot_in_txn(conn, user_id, now_fn) -> dict:
        """在调用方事务内按 ledger 重建钱包快照。

        调用链路：RewardWalletService/SyncHub -> 本函数 -> SUM(server_reward_ledger) -> UPSERT(server_user_wallets)。
        返回：{"balance": ledger汇总, "wallet_balance": 写入后的快照余额, "consistent": True}。
        """
        row = conn.execute(
            "SELECT SUM(amount) AS total FROM server_reward_ledger WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        balance = float(row["total"]) if row and row["total"] is not None else 0.0
        existing = conn.execute(
            "SELECT balance FROM server_user_wallets WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing and float(existing["balance"]) == balance:
            return {"balance": balance, "wallet_balance": balance, "consistent": True}
        conn.execute(
            """
            INSERT INTO server_user_wallets (user_id, balance, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                balance = excluded.balance,
                updated_at = excluded.updated_at
            """,
            (user_id, balance, now_fn()),
        )
        return {"balance": balance, "wallet_balance": balance, "consistent": True}

    def rebuild_wallet_snapshot(self, user_id) -> dict:
        """调用链路：REST/测试/SyncHub -> store.rebuild_wallet_snapshot -> 本函数 -> SUM(ledger) -> UPSERT wallet。

        SQL：
          SELECT SUM(amount) FROM server_reward_ledger WHERE user_id=?
          INSERT ... ON CONFLICT(user_id) DO UPDATE ...

        返回：{"balance": ledger汇总, "wallet_balance": 写入后的快照余额, "consistent": True}
        """
        with self._transact() as conn:
            return self.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)

    def verify_wallet_consistency(self, user_id) -> dict:
        """校验钱包快照是否能由 reward_ledger 重建。"""
        conn = self._connect()
        try:
            ledger_balance = self._ledger_sum_in_txn(conn, user_id)
            row = conn.execute(
                "SELECT balance FROM server_user_wallets WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            wallet_balance = float(row["balance"]) if row else ledger_balance
            return {
                "ledger_balance": ledger_balance,
                "wallet_balance": wallet_balance,
                "consistent": abs(ledger_balance - wallet_balance) < 0.000001,
            }
        finally:
            conn.close()

    def get_gold_balance(self, user_id) -> float:
        conn = self._connect()
        try:
            return self._ledger_sum_in_txn(conn, user_id)
        finally:
            conn.close()

    def get_user_wallet_balance(self, user_id) -> float:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT balance FROM server_user_wallets WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return float(row["balance"])
        finally:
            conn.close()
        return self.rebuild_wallet_snapshot(user_id)["balance"]

    def update_user_wallet_balance(self, user_id, amount_change, ledger_uuid=None) -> float:
        with self._transact() as conn:
            self._update_wallet_in_txn(
                conn,
                user_id,
                amount_change,
                ledger_uuid=ledger_uuid,
                amount_already_in_ledger=False,
            )
            row = conn.execute(
                "SELECT balance FROM server_user_wallets WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return float(row["balance"]) if row else 0.0

    def append_ledger_in_txn(
        self,
        conn,
        user_id,
        amount,
        source_type,
        source_id=None,
        description="",
        target_date=None,
        ledger_id=None,
        occurred_at=None,
    ) -> str:
        """在调用方事务内追加事实流水，并同步更新钱包快照。

        调用链路：HabitDomainService/RewardWalletService/SyncHub -> append_ledger_in_txn -> INSERT ledger -> UPDATE wallet。
        SQL：INSERT INTO server_reward_ledger；UPDATE/INSERT server_user_wallets。
        返回：ledger_id。
        """
        now_ts = self._now()
        target_date = target_date or now_ts.split(" ")[0]
        ledger_id = ledger_id or uuid.uuid4().hex
        if not is_user_statistics_date_eligible(conn, user_id, target_date):
            return ledger_id
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO server_reward_ledger
                (id, user_id, amount, source_type, source_id, description, target_date, occurred_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ledger_id, user_id, amount, source_type, source_id, description, target_date, occurred_at, now_ts, now_ts),
        )
        if cur.rowcount > 0:
            self._update_wallet_in_txn(conn, user_id, amount, ledger_uuid=ledger_id)
            self._record_change(conn, user_id, "server_reward_ledger", ledger_id, "upsert")
            self._record_change(conn, user_id, "server_user_wallets", user_id, "upsert")
            if source_type == "reward_buy":
                self.record_backpack_event_in_txn(
                    conn, user_id, ledger_id, "acquired",
                    event_id=f"backpack:acquired:{ledger_id}", occurred_at=occurred_at or now_ts,
                )
        return ledger_id

    def record_action_event_in_txn(
        self, conn, user_id, event_id, event_type, amount, occurred_at, subject_id=None, payload=None,
    ):
        """记录不可变用户动作；重复 event_id 只读复用，绝不改写原金额。"""
        conn.execute(
            """INSERT OR IGNORE INTO server_reward_action_events
               (id,user_id,event_type,amount,occurred_at,subject_id,payload_json,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (str(event_id), user_id, event_type, float(amount), occurred_at,
             str(subject_id) if subject_id is not None else None,
             json.dumps(payload or {}, ensure_ascii=False, sort_keys=True), self._now()),
        )

    def record_backpack_event_in_txn(
        self, conn, user_id, ledger_id, event_type, *, reward_id=None, fragment_id=None, quantity=1, detail=None,
        event_id=None, occurred_at=None,
    ):
        conn.execute(
            """INSERT OR IGNORE INTO server_backpack_events
               (id,user_id,ledger_id,event_type,reward_id,fragment_id,quantity,detail,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (event_id or uuid.uuid4().hex, user_id, str(ledger_id), event_type, str(reward_id) if reward_id else None,
             str(fragment_id) if fragment_id else None, int(quantity or 1), detail, occurred_at or self._now()),
        )

    def remove_ledger_entries_in_txn(self, conn, user_id, ledger_ids, backpack_event="revoked") -> list[dict]:
        """移除服务端自动事实流水，并同步删除变更与钱包快照。"""
        ids = [str(ledger_id) for ledger_id in ledger_ids if ledger_id]
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        rows = [dict(row) for row in conn.execute(
            f"SELECT * FROM server_reward_ledger WHERE user_id=? AND id IN ({placeholders})",
            [user_id, *ids],
        ).fetchall()]
        if not rows:
            return []
        for row in rows:
            if backpack_event and row["source_type"] == "reward_buy":
                self.record_backpack_event_in_txn(conn, user_id, row["id"], backpack_event)
        conn.execute(
            f"DELETE FROM server_reward_ledger WHERE user_id=? AND id IN ({placeholders})",
            [user_id, *ids],
        )
        for row in rows:
            self._record_change(conn, user_id, "server_reward_ledger", row["id"], "delete", {"id": row["id"]})
        wallet = self.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
        self._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {
            "user_id": user_id, "balance": wallet["balance"], "updated_at": self._now(),
        })
        return rows

    def list_ledger(self, user_id, limit=30) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM server_reward_ledger WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def add_ledger_entry(self, user_id, amount, source_type, source_id=None, description="") -> bool:
        with self._transact() as conn:
            occurred_at = self._now()
            ledger_id = self.append_ledger_in_txn(
                conn, user_id, amount, source_type, source_id, description,
                occurred_at=occurred_at,
            )
            self.record_action_event_in_txn(
                conn, user_id, f"action:{ledger_id}", "manual_adjustment", amount,
                occurred_at, source_id, {"description": description, "source_type": source_type},
            )
        return True

    def buy_reward(self, user_id, reward_id):
        """兑换商品。

        调用链路：POST /api/rewards/buy/{reward_id} -> store.buy_reward -> 本函数。
        SQL/事务：SELECT reward + SELECT SUM ledger + INSERT reward_buy ledger + UPDATE wallet，同一事务提交。
        返回：(success, message)。
        """
        with self._transact() as conn:
            reward = conn.execute(
                "SELECT * FROM server_rewards WHERE id=? AND user_id=? AND is_active=1",
                (reward_id, user_id),
            ).fetchone()
            if not reward:
                return False, "未找到该商品"

            price = float(reward["price"])
            balance = self._ledger_sum_in_txn(conn, user_id)
            if balance < price:
                return False, "金币余额不足"

            desc = f"兑换商品成功: {reward['icon']}{reward['title']}"
            occurred_at = self._now()
            ledger_id = self.append_ledger_in_txn(
                conn,
                user_id,
                -price,
                "reward_buy",
                str(reward_id),
                desc,
                occurred_at.split(" ")[0],
                occurred_at=occurred_at,
            )
            self.record_action_event_in_txn(
                conn, user_id, f"action:{ledger_id}", "reward_purchase", -price,
                occurred_at, reward_id, {"ledger_id": ledger_id, "description": desc,
                                         "source_id": str(reward_id), "source_type": "reward_buy"},
            )
        return True, "购买成功"

    def list_unclaimed_rewards(self, user_id) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM server_external_rewards WHERE user_id=? AND status=0 ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def claim_rewards(self, user_id, ids) -> float:
        if not ids:
            return 0.0
        with self._transact() as conn:
            total_claimed = 0.0
            for ext_id in ids:
                row = conn.execute(
                    """
                    SELECT coins, item_type, item_name, created_at
                    FROM server_external_rewards
                    WHERE ext_id=? AND user_id=? AND status=0
                    """,
                    (ext_id, user_id),
                ).fetchone()
                if not row:
                    continue

                coins = float(row["coins"])
                item_type = row["item_type"]
                target_date = row["created_at"].split(" ")[0] if row["created_at"] else self._now().split(" ")[0]
                clean_name = re.sub(r"[^\w\s,.\-\[\]()]", "", row["item_name"]).strip()
                source_type = "external_claim"
                if item_type == "task":
                    source_type = "task_complete"
                elif item_type == "habit":
                    source_type = "habit_checkin" if coins >= 0 else "habit_fail"
                elif item_type == "goal":
                    source_type = "goal_reward" if coins >= 0 else "goal_penalty"

                conn.execute(
                    "UPDATE server_external_rewards SET status=1, updated_at=? WHERE ext_id=? AND user_id=?",
                    (self._now(), ext_id, user_id),
                )
                self._record_change(conn, user_id, "server_external_rewards", ext_id, "upsert")
                self.append_ledger_in_txn(
                    conn,
                    user_id,
                    coins,
                    source_type,
                    ext_id,
                    clean_name,
                    target_date,
                )
                total_claimed += coins
        return total_claimed

    def add_external_reward(self, user_id, ext_id, item_type, item_name, coins, status=0) -> bool:
        """登记外部奖励待领取队列。

        调用链路：SyncHub TickTick 拉取/REST -> store.add_external_reward -> 本函数。
        幂等键：UNIQUE(user_id, ext_id)，不同用户同 ext_id 不互相覆盖。
        """
        with self._transact() as conn:
            reward_id = uuid.uuid4().hex
            now_ts = self._now()
            conn.execute(
                """
                INSERT INTO server_external_rewards
                    (id, ext_id, user_id, item_type, item_name, coins, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, ext_id) DO UPDATE SET
                    item_type = excluded.item_type,
                    item_name = excluded.item_name,
                    coins = excluded.coins,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (reward_id, ext_id, user_id, item_type, item_name, coins, status, now_ts, now_ts),
            )
            self._record_change(conn, user_id, "server_external_rewards", ext_id, "upsert")
        return True

    def list_backpack(self, user_id) -> list[dict]:
        conn = self._connect()
        try:
            purchases = conn.execute(
                """
                SELECT
                    l.id,
                    l.source_id,
                    COALESCE(CAST(r.id AS TEXT), l.source_id) as reward_id,
                    l.created_at,
                    COALESCE(r.title, '已下架奖励') AS title,
                    COALESCE(r.icon, '🎁') AS icon,
                    COALESCE(r.description, l.description) AS description,
                    used.created_at AS used_at
                FROM server_reward_ledger l
                LEFT JOIN server_rewards r
                  ON l.source_id = CAST(r.id AS TEXT)
                  OR l.source_id LIKE CAST(r.id AS TEXT) || ':%'
                  OR l.source_id LIKE 'unlock:' || CAST(r.id AS TEXT) || ':%'
                LEFT JOIN server_reward_ledger used
                  ON used.user_id = l.user_id
                  AND used.source_type = 'backpack_use'
                  AND used.source_id = l.id
                WHERE l.user_id=? AND l.source_type='reward_buy'
                  AND NOT EXISTS(SELECT 1 FROM server_reward_ledger discarded
                      WHERE discarded.user_id=l.user_id AND discarded.source_type='backpack_discard'
                        AND discarded.source_id=l.id)
                """,
                (user_id,),
            ).fetchall()
            return [
                {
                    "id": p["id"],
                    "reward_id": str(p["reward_id"]),
                    "title": p["title"],
                    "icon": p["icon"],
                    "description": p["description"],
                    "created_at": p["created_at"],
                    "is_used": bool(p["used_at"]),
                    "used_at": p["used_at"],
                }
                for p in purchases
            ]
        finally:
            conn.close()

    def list_backpack_fragments(self, user_id) -> list[dict]:
        """返回尚未合成的服务端权威碎片库存投影，碎片本身不可使用。"""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT f.reward_id, f.rule_version, SUM(f.progress_units-f.consumed_units) AS active_units,
                       MIN(f.expires_at) AS earliest_expires_at,
                       r.title, r.icon, r.description, r.inventory_mode, r.inventory_limit
                FROM server_reward_fragments f
                JOIN server_rewards r ON r.id=f.reward_id AND r.user_id=f.user_id
                WHERE f.user_id=? AND f.status='active' AND f.expires_at>?
                GROUP BY f.reward_id, f.rule_version
                ORDER BY earliest_expires_at ASC, f.reward_id ASC
                """, (user_id, self._now()),
            ).fetchall()
            result = []
            for row in rows:
                reward_id, mode, limit = str(row["reward_id"]), str(row["inventory_mode"] or "unlimited"), int(row["inventory_limit"] or 0)
                today, used = self._now()[:10], 0
                if mode in {"daily", "monthly"} and limit > 0:
                    clause, value = ("target_date=?", today) if mode == "daily" else ("substr(target_date,1,7)=?", today[:7])
                    used = int(conn.execute(f"""SELECT COUNT(*) count FROM server_reward_ledger WHERE user_id=? AND source_type='reward_buy'
                        AND (source_id LIKE ? OR source_id LIKE ?) AND {clause}""", (user_id, f"{reward_id}:%", f"unlock:{reward_id}:%", value)).fetchone()["count"] or 0)
                units = int(row["active_units"] or 0)
                result.append({"id": f"fragment:{reward_id}:{row['rule_version']}", "reward_id": reward_id,
                    "title": row["title"], "icon": row["icon"] or "🧩", "description": row["description"],
                    "current_count": units, "target_count": 100, "progress_percent": units,
                    "inventory_used": used, "inventory_limit": limit or None,
                    "inventory_limit_reached": mode != "unlimited" and limit > 0 and used >= limit,
                    "earliest_expires_at": row["earliest_expires_at"], "rule_version": int(row["rule_version"])})
            return result
        finally:
            conn.close()

    def use_backpack_item(self, user_id, ledger_id):
        with self._transact() as conn:
            purchase = conn.execute(
                "SELECT id, description FROM server_reward_ledger WHERE id=? AND user_id=? AND source_type='reward_buy'",
                (ledger_id, user_id),
            ).fetchone()
            if not purchase:
                return False, "未找到该背包物品"
            used = conn.execute(
                "SELECT 1 FROM server_reward_ledger WHERE user_id=? AND source_type IN ('backpack_use','backpack_discard') AND source_id=?",
                (user_id, str(ledger_id)),
            ).fetchone()
            if used:
                return True, "物品已使用"
            occurred_at = self._now()
            action_ledger_id = self.append_ledger_in_txn(
                conn,
                user_id,
                0,
                "backpack_use",
                str(ledger_id),
                f"使用背包物品: {purchase['description']}",
                occurred_at=occurred_at,
            )
            self.record_action_event_in_txn(
                conn, user_id, f"action:{action_ledger_id}", "backpack_use", 0,
                occurred_at, ledger_id, {"ledger_id": action_ledger_id},
            )
            self.record_backpack_event_in_txn(conn, user_id, ledger_id, "used")
        return True, "使用成功"

    def discard_backpack_item(self, user_id, ledger_id):
        with self._transact() as conn:
            row = conn.execute("SELECT id FROM server_reward_ledger WHERE id=? AND user_id=? AND source_type='reward_buy'", (ledger_id, user_id)).fetchone()
            used = conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=? AND source_type IN ('backpack_use','backpack_discard') AND source_id=?", (user_id, str(ledger_id))).fetchone()
            if not row or used:
                return False, "物品不可丢弃"
            occurred_at = self._now()
            action_ledger_id = self.append_ledger_in_txn(
                conn, user_id, 0, "backpack_discard", str(ledger_id), "丢弃背包物品",
                occurred_at=occurred_at,
            )
            self.record_action_event_in_txn(
                conn, user_id, f"action:{action_ledger_id}", "backpack_discard", 0,
                occurred_at, ledger_id, {"ledger_id": action_ledger_id},
            )
            self.record_backpack_event_in_txn(conn, user_id, ledger_id, "discarded")
        return True, "已丢弃"

    def list_backpack_events(self, user_id, limit=50, offset=0):
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT e.*, COALESCE(r.title, '已下架奖励') AS item_title,
                       COALESCE(e.quantity, 1) AS quantity
                FROM server_backpack_events e
                LEFT JOIN server_reward_ledger l ON l.id=e.ledger_id AND l.user_id=e.user_id
                LEFT JOIN server_rewards r ON r.user_id=e.user_id AND (
                    e.reward_id=CAST(r.id AS TEXT) OR l.source_id=CAST(r.id AS TEXT) OR l.source_id LIKE CAST(r.id AS TEXT) || ':%'
                    OR l.source_id LIKE 'unlock:' || CAST(r.id AS TEXT) || ':%'
                )
                WHERE e.user_id=? ORDER BY e.created_at DESC LIMIT ? OFFSET ?
                """, (user_id, int(limit), int(offset)),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def reset_coins(self, user_id) -> bool:
        with self._transact() as conn:
            conn.execute("DELETE FROM server_reward_ledger WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM server_external_rewards WHERE user_id=?", (user_id,))
            conn.execute(
                """
                INSERT INTO server_user_wallets (user_id, balance, updated_at)
                VALUES (?, 0.0, ?)
                ON CONFLICT(user_id) DO UPDATE SET balance=0.0, updated_at=excluded.updated_at
                """,
                (user_id, self._now()),
            )
        return True
