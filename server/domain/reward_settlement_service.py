# -*- coding: utf-8 -*-
"""服务端金币结算领域服务。

调用链路：
  SyncHub / ServerSleepStore
    -> RewardSettlementService
      -> server_reward_ledger / server_user_wallets

事务边界：
  settle_* 默认使用 store._transact()；settle_*_in_txn 复用调用方连接。
  业务事实、流水、钱包快照必须在同一事务内提交或回滚。
"""

from __future__ import annotations

import re
import sqlite3
import uuid
import hashlib
from datetime import date, timedelta

try:
    from ..statistics_start_date import is_user_statistics_date_eligible
except ImportError:
    from statistics_start_date import is_user_statistics_date_eligible


class RewardSettlementService:
    """金币结算、流水描述和钱包快照的服务端唯一入口。"""

    LABELS = {
        "task": "清单",
        "habit": "习惯",
        "goal": "目标",
        "reward": "兑换",
        "exercise": "运动",
        "learning": "学习",
    }

    def __init__(self, transact, now_fn, reward_wallet_service, record_change_in_txn=None):
        self._transact = transact
        self._now = now_fn
        self._reward_wallet = reward_wallet_service
        from .reward_fragment_service import RewardFragmentService
        self._fragments = RewardFragmentService(
            now_fn, reward_wallet_service, record_change_in_txn, self._inventory_available_in_txn,
        )

    def format_description(self, success: bool, item_type: str, title: str) -> str:
        """生成统一流水描述：√/× + 标签 + 名称。"""
        sign = "√" if success else "×"
        label = self.LABELS.get(item_type, item_type or "项目")
        clean_title = self._clean_title(title)
        return f"{sign} {label} {clean_title}".strip()

    def make_ledger_id(self, user_id, source_type: str, source_id, target_date: str) -> str:
        raw = f"{user_id}:{source_type}:{source_id or ''}:{target_date or ''}"
        safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", raw).strip("_")
        return f"ledger_{safe}"[:180] or uuid.uuid4().hex

    def settle(
        self,
        user_id,
        amount,
        item_type: str,
        title: str,
        source_type: str,
        source_id=None,
        target_date=None,
        success: bool | None = None,
        ledger_id: str | None = None,
        occurred_at=None,
    ) -> str:
        """在独立事务中结算一条金币流水。"""
        with self._transact() as conn:
            return self.settle_in_txn(
                conn,
                user_id,
                amount,
                item_type,
                title,
                source_type,
                source_id=source_id,
                target_date=target_date,
                success=success,
                ledger_id=ledger_id,
                occurred_at=occurred_at,
            )

    def settle_in_txn(
        self,
        conn,
        user_id,
        amount,
        item_type: str,
        title: str,
        source_type: str,
        source_id=None,
        target_date=None,
        success: bool | None = None,
        ledger_id: str | None = None,
        occurred_at=None,
    ) -> str:
        """在调用方事务内结算一条金币流水，重复事实不会重复入账。"""
        amount = float(amount)
        target_date = target_date or self._now().split(" ")[0]
        success = amount >= 0 if success is None else success
        description = self.format_description(success, item_type, title)
        ledger_id = ledger_id or self.make_ledger_id(user_id, source_type, source_id, target_date)
        if not is_user_statistics_date_eligible(conn, user_id, target_date):
            return ledger_id

        try:
            cur = conn.execute(
                """
                INSERT INTO server_reward_ledger
                    (id, user_id, amount, source_type, source_id, description, target_date, occurred_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ledger_id, user_id, amount, source_type, str(source_id) if source_id is not None else None, description, target_date, occurred_at, self._now(), self._now()),
            )
        except sqlite3.IntegrityError:
            if occurred_at:
                conn.execute(
                    "UPDATE server_reward_ledger SET occurred_at=?, updated_at=? WHERE id=? AND occurred_at IS NULL",
                    (occurred_at, self._now(), ledger_id),
                )
            return ledger_id

        if cur.rowcount > 0:
            wallet = self._reward_wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
            self._reward_wallet._record_change(conn, user_id, "server_reward_ledger", ledger_id, "upsert")
            self._reward_wallet._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {
                "user_id": user_id, "balance": wallet["balance"], "updated_at": self._now(),
            })
        return ledger_id

    def settle_task_success_in_txn(self, conn, user_id, task_id, title, coins, target_date, occurred_at=None) -> str:
        return self.settle_in_txn(
            conn, user_id, coins, "task", title, "task_complete", task_id,
            target_date, True, occurred_at=occurred_at,
        )

    def settle_habit_success_in_txn(self, conn, user_id, habit_id, title, coins, target_date, occurred_at=None) -> str:
        ledger_id, _ = self.reconcile_habit_success_in_txn(
            conn, user_id, habit_id, title, coins, target_date, occurred_at
        )
        return ledger_id

    def reconcile_habit_success_in_txn(
        self, conn, user_id, habit_id, title, coins, target_date, occurred_at=None
    ) -> tuple[str, str]:
        """按实际打卡时间原地核对习惯成功流水，不改变稳定事实 ID。"""
        ledger_id = self.make_ledger_id(user_id, "habit_checkin", habit_id, target_date)
        row = conn.execute(
            "SELECT amount,description,occurred_at FROM server_reward_ledger WHERE user_id=? AND id=?",
            (user_id, ledger_id),
        ).fetchone()
        if row is None:
            created = self.settle_in_txn(
                conn, user_id, coins, "habit", title, "habit_checkin", habit_id,
                target_date, True, ledger_id, occurred_at,
            )
            return created, "created"
        if not occurred_at:
            return ledger_id, "unverifiable"
        amount = float(coins)
        description = self.format_description(True, "habit", title)
        if float(row["amount"]) == amount and row["description"] == description and row["occurred_at"] == occurred_at:
            return ledger_id, "unchanged"
        conn.execute(
            "UPDATE server_reward_ledger SET amount=?,description=?,occurred_at=?,updated_at=? WHERE user_id=? AND id=?",
            (amount, description, occurred_at, self._now(), user_id, ledger_id),
        )
        wallet = self._reward_wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
        self._reward_wallet._record_change(conn, user_id, "server_reward_ledger", ledger_id, "upsert")
        self._reward_wallet._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {
            "user_id": user_id, "balance": wallet["balance"], "updated_at": self._now(),
        })
        return ledger_id, "corrected"

    def settle_habit_fail_in_txn(self, conn, user_id, habit_id, title, coins, target_date, occurred_at=None) -> str:
        return self.settle_in_txn(conn, user_id, -abs(float(coins)), "habit", title, "habit_fail", habit_id, target_date, False, occurred_at=occurred_at)

    @staticmethod
    def completion_event_key(source_type: str, source_id, target_date: str, revision=None, plan_version=None, item_key=None) -> str:
        """返回不依赖客户端时钟的奖励完成事实键。"""
        if source_type == "exercise_checkin":
            return f"exercise:{plan_version or 'v0'}:{target_date}:{item_key or source_id}"
        if source_type == "habit":
            return f"habit:{source_id}:{target_date}"
        prefix = "checklist" if source_type == "checklist_task" else "learning"
        return f"{prefix}:{source_id}:{revision or target_date}"

    def grant_task_unlocks_in_txn(self, conn, user_id, source_type, source_id, event_key, title, target_date) -> list[str]:
        """为匹配的任务型兑换创建幂等的零价背包入库流水。"""
        if not is_user_statistics_date_eligible(conn, user_id, target_date):
            return []
        rewards = conn.execute(
            """
            SELECT r.id, r.title, r.inventory_mode, r.inventory_limit, r.unlock_required_count,
                   r.unlock_threshold_started_at, r.fulfillment_mode, r.fragment_target_count,
                   r.fragment_rule_version, b.drop_mode, b.drop_min_units, b.drop_max_units
            FROM server_reward_source_bindings b
            JOIN server_rewards r ON r.id=b.reward_id
            WHERE b.user_id=? AND b.source_type=? AND b.source_id=? AND r.is_active=1
            """,
            (user_id, source_type, str(source_id)),
        ).fetchall()
        ledger_ids = []
        ledger_ids.extend(self._fragments.grant_for_event_in_txn(
            conn, user_id, source_type, source_id, event_key, title, target_date, rewards,
        ))
        for reward in rewards:
            if str(reward["fulfillment_mode"] or "immediate") == "fragment":
                continue
            if source_type == "habit" and int(reward["unlock_required_count"] or 1) > 1:
                ledger_ids.extend(self.reconcile_habit_unlock_thresholds_in_txn(conn, user_id, source_id, reward, title))
                continue
            if not self._inventory_available_in_txn(conn, user_id, reward, target_date):
                continue
            source = f"unlock:{reward['id']}:{source_type}:{event_key}"
            ledger_id = self.make_ledger_id(user_id, "reward_buy", source, target_date)
            self._reward_wallet.append_ledger_in_txn(
                conn, user_id, 0, "reward_buy", source,
                f"任务自动解锁兑换: {reward['title'] or title}", target_date, ledger_id,
            )
            ledger_ids.append(ledger_id)
        return ledger_ids

    def revoke_fragments_for_event_in_txn(self, conn, user_id, source_type, source_id, event_key):
        return self._fragments.revoke_event_in_txn(conn, user_id, source_type, source_id, event_key)

    def expire_fragments_for_user_in_txn(self, conn, user_id):
        return self._fragments.expire_for_user_in_txn(conn, user_id)

    def inventory_available_in_txn(self, conn, user_id, reward, target_date: str) -> bool:
        """按服务端北京时间目标窗口判断商品是否还能入包。"""
        return self._inventory_available_in_txn(conn, user_id, reward, target_date)

    def _inventory_available_in_txn(self, conn, user_id, reward, target_date: str) -> bool:
        mode = str(reward["inventory_mode"] or "unlimited")
        if mode == "unlimited":
            return True
        limit = int(reward["inventory_limit"] or 0)
        if mode not in {"daily", "weekly", "monthly"} or limit <= 0:
            return False
        start, end = self._inventory_window(target_date, mode)
        count = conn.execute(
            """
            SELECT COUNT(*) AS count FROM server_reward_ledger
            WHERE user_id=? AND source_type='reward_buy' AND target_date BETWEEN ? AND ?
              AND (source_id LIKE ? OR source_id LIKE ?)
            """,
            (user_id, start, end, f"{reward['id']}:%", f"unlock:{reward['id']}:%"),
        ).fetchone()["count"]
        return int(count or 0) < limit

    @staticmethod
    def _inventory_window(target_date: str, mode: str) -> tuple[str, str]:
        value = date.fromisoformat(str(target_date)[:10])
        if mode == "daily":
            return value.isoformat(), value.isoformat()
        if mode == "weekly":
            start = value - timedelta(days=value.weekday())
            return start.isoformat(), (start + timedelta(days=6)).isoformat()
        start = value.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start.isoformat(), (next_month - timedelta(days=1)).isoformat()

    def reconcile_habit_unlock_thresholds_in_txn(self, conn, user_id, habit_id, reward, fallback_title, reverse_used=False) -> list[str]:
        """让习惯阈值商品数量与服务端有效打卡数一致。"""
        required = int(reward["unlock_required_count"] or 1)
        if required <= 1:
            return []
        started_at = reward["unlock_threshold_started_at"] or ""
        checkins = conn.execute(
            """
            SELECT checkin_date, date FROM server_habit_checkins
            WHERE user_id=? AND habit_id=? AND status=2 AND created_at>=?
            ORDER BY checkin_date ASC, date ASC, id ASC
            """,
            (user_id, str(habit_id), started_at),
        ).fetchall()
        expected = len(checkins) // required
        prefix = f"unlock:{reward['id']}:habit:threshold:"
        existing = conn.execute(
            """SELECT id, source_id FROM server_reward_ledger
               WHERE user_id=? AND source_type='reward_buy' AND source_id LIKE ?""",
            (user_id, f"{prefix}%"),
        ).fetchall()
        existing_by_block = {int(str(row["source_id"]).rsplit(":", 1)[-1]): row["id"] for row in existing}
        stale_blocks = sorted(block for block in existing_by_block if block > expected)
        if stale_blocks:
            stale_ids = [existing_by_block[block] for block in stale_blocks]
            placeholders = ", ".join("?" for _ in stale_ids)
            if reverse_used:
                self._remove_backpack_uses_for_unlocks_in_txn(conn, user_id, stale_ids)
            else:
                used = conn.execute(
                    f"SELECT 1 FROM server_reward_ledger WHERE user_id=? AND source_type='backpack_use' AND source_id IN ({placeholders}) LIMIT 1",
                    [user_id, *stale_ids],
                ).fetchone()
                if used:
                    raise ValueError("奖励物品已使用，不能取消对应完成记录")
            self._reward_wallet.remove_ledger_entries_in_txn(conn, user_id, stale_ids)
        created = []
        for block in range(1, expected + 1):
            if block in existing_by_block:
                continue
            checkin = checkins[block * required - 1]
            target_date = str(checkin["checkin_date"] or checkin["date"])[:10]
            if not self._inventory_available_in_txn(conn, user_id, reward, target_date):
                continue
            source = f"{prefix}{block}"
            ledger_id = self.make_ledger_id(user_id, "reward_buy", source, target_date)
            self._reward_wallet.append_ledger_in_txn(
                conn, user_id, 0, "reward_buy", source,
                f"习惯累计解锁兑换: {reward['title'] or fallback_title}", target_date, ledger_id,
            )
            created.append(ledger_id)
        return created

    def _remove_backpack_uses_for_unlocks_in_txn(self, conn, user_id, unlock_ledger_ids) -> list[dict]:
        """先撤销指定自动入包商品的使用流水，保持商品来源链可逆。"""
        ids = [str(ledger_id) for ledger_id in unlock_ledger_ids if ledger_id]
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        used_ids = [row["id"] for row in conn.execute(
            f"SELECT id FROM server_reward_ledger WHERE user_id=? AND source_type='backpack_use' AND source_id IN ({placeholders})",
            [user_id, *ids],
        ).fetchall()]
        return self._reward_wallet.remove_ledger_entries_in_txn(conn, user_id, used_ids)

    def remove_task_unlocks_in_txn(self, conn, user_id, source_type, source_id, event_key, reverse_used=False) -> list[dict]:
        """撤销来源事件产生的自动入包流水，可选同步撤销其使用流水。"""
        rewards = conn.execute(
            """
            SELECT r.id, r.unlock_required_count FROM server_reward_source_bindings b
            JOIN server_rewards r ON r.id=b.reward_id
            WHERE b.user_id=? AND b.source_type=? AND b.source_id=?
            """,
            (user_id, source_type, str(source_id)),
        ).fetchall()
        sources = [
            f"unlock:{row['id']}:{source_type}:{event_key}"
            for row in rewards
            if not (source_type == "habit" and int(row["unlock_required_count"] or 1) > 1)
        ]
        if not sources:
            return []
        placeholders = ", ".join("?" for _ in sources)
        rows = [dict(row) for row in conn.execute(
            f"SELECT id FROM server_reward_ledger WHERE user_id=? AND source_type='reward_buy' AND source_id IN ({placeholders})",
            [user_id, *sources],
        ).fetchall()]
        if not rows:
            return []
        purchase_ids = [row["id"] for row in rows]
        if reverse_used:
            self._remove_backpack_uses_for_unlocks_in_txn(conn, user_id, purchase_ids)
        else:
            used = conn.execute(
                f"SELECT 1 FROM server_reward_ledger WHERE user_id=? AND source_type='backpack_use' AND source_id IN ({', '.join('?' for _ in purchase_ids)}) LIMIT 1",
                [user_id, *purchase_ids],
            ).fetchone()
            if used:
                raise ValueError("奖励物品已使用，不能取消对应完成记录")
        return self._reward_wallet.remove_ledger_entries_in_txn(conn, user_id, purchase_ids)

    def remove_task_unlocks_for_source_in_txn(self, conn, user_id, source_type, source_id) -> list[dict]:
        """撤销来源恢复为未完成时遗留的自动入包流水。"""
        rewards = conn.execute(
            """SELECT r.id FROM server_reward_source_bindings b JOIN server_rewards r ON r.id=b.reward_id
               WHERE b.user_id=? AND b.source_type=? AND b.source_id=?""",
            (user_id, source_type, str(source_id)),
        ).fetchall()
        event_prefix = f"checklist:{source_id}:" if source_type == "checklist_task" else f"{source_type}:{source_id}:"
        prefixes = [f"unlock:{row['id']}:{source_type}:{event_prefix}%" for row in rewards]
        if not prefixes:
            return []
        rows = [dict(row) for row in conn.execute(
            "SELECT id FROM server_reward_ledger WHERE user_id=? AND source_type='reward_buy' AND ("
            + " OR ".join("source_id LIKE ?" for _ in prefixes) + ")",
            [user_id, *prefixes],
        ).fetchall()]
        purchase_ids = [row["id"] for row in rows]
        if not purchase_ids:
            return []
        used = conn.execute(
            f"SELECT 1 FROM server_reward_ledger WHERE user_id=? AND source_type='backpack_use' AND source_id IN ({', '.join('?' for _ in purchase_ids)}) LIMIT 1",
            [user_id, *purchase_ids],
        ).fetchone()
        if used:
            raise ValueError("奖励物品已使用，不能取消对应完成记录")
        return self._reward_wallet.remove_ledger_entries_in_txn(conn, user_id, purchase_ids)

    def remove_state_ledgers_in_txn(
        self, conn, user_id, source_id, source_types, target_date=None, keep_source_type=None
    ) -> list[dict]:
        """删除同一业务事实下与当前状态互斥的流水，并返回被删除的完整记录。"""
        placeholders = ", ".join("?" for _ in source_types)
        params = [user_id, str(source_id), *source_types]
        where = (
            f"user_id = ? AND source_id = ? AND source_type IN ({placeholders})"
        )
        if target_date is not None:
            where += " AND target_date = ?"
            params.append(target_date)
        if keep_source_type is not None:
            where += " AND source_type <> ?"
            params.append(keep_source_type)
        rows = [dict(row) for row in conn.execute(
            f"SELECT * FROM server_reward_ledger WHERE {where}", params
        ).fetchall()]
        if rows:
            self._reward_wallet.remove_ledger_entries_in_txn(conn, user_id, [row["id"] for row in rows])
        return rows

    def preview_invalid_habit_unlocks(self, user_id):
        conn = self._connect_for_preview()
        try:
            rows = [dict(row) for row in conn.execute("""SELECT l.id,l.target_date,l.source_id,
                EXISTS(SELECT 1 FROM server_reward_ledger u WHERE u.user_id=l.user_id AND u.source_type='backpack_use' AND u.source_id=l.id) used
                FROM server_reward_ledger l WHERE l.user_id=? AND l.source_type='reward_buy' AND l.source_id LIKE 'unlock:%:habit:%'""", (user_id,)).fetchall()]
            today = self._now()[:10]
            invalid = [row for row in rows if row['target_date'] < today or not conn.execute("SELECT 1 FROM server_habit_checkins WHERE user_id=? AND status=2 AND checkin_date=?", (user_id, row['target_date'])).fetchone()]
            digest = hashlib.sha256('|'.join(sorted(row['id'] for row in invalid)).encode()).hexdigest()
            return {'count': len(invalid), 'summary_hash': digest, 'items': invalid}
        finally:
            conn.close()

    def _connect_for_preview(self):
        # RewardWalletService owns the established read-only connection factory.
        return self._reward_wallet._connect()

    def remove_invalid_habit_unlocks(self, user_id, summary_hash):
        preview = self.preview_invalid_habit_unlocks(user_id)
        if summary_hash != preview['summary_hash']:
            raise ValueError('审计摘要不匹配')
        with self._transact() as conn:
            ids = [row['id'] for row in preview['items']]
            uses = [row['id'] for row in conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=? AND source_type='backpack_use' AND source_id IN (" + ','.join('?' for _ in ids) + ')', [user_id, *ids]).fetchall()] if ids else []
            self._reward_wallet.remove_ledger_entries_in_txn(conn, user_id, uses + ids)
        return len(ids)

    def settle_exercise_success_in_txn(self, conn, user_id, item_id, title, coins, target_date) -> str:
        return self.settle_in_txn(conn, user_id, coins, "exercise", title, "exercise_checkin", item_id, target_date, True)

    def settle_learning_success_in_txn(self, conn, user_id, item_id, title, coins, target_date) -> str:
        return self.settle_in_txn(conn, user_id, coins, "learning", title, "learning_checkin", item_id, target_date, True)

    def settle_reward_buy_in_txn(self, conn, user_id, purchase_id, title, price, target_date) -> str:
        return self.settle_in_txn(conn, user_id, -abs(float(price)), "reward", title, "reward_buy", purchase_id, target_date, True)

    def _clean_title(self, title: str) -> str:
        text = str(title or "").strip()
        text = re.sub(r"habit_[A-Za-z0-9_]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
