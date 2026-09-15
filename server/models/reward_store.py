# -*- coding: utf-8 -*-
"""
积分与奖励商店模块 (reward_store.py)
=====================================
将 StudyLogger 中所有积分流水和奖励商店相关方法提取为独立存储类。

主要职责：
- 积分余额查询与流水记录（reward_ledger 表）
- 自定义奖励配置读写（reward_config 表）
- 外部系统静默打卡奖励管理（external_rewards 表）
- 奖励商品 CRUD（rewards 表）
- 背包物品管理（reward_ledger 中 source_type='reward_unlock' 的记录）
- 金币重置

设计原则：
- RewardStore 不依赖 StudyLogger，仅依赖 db_path 字符串
- 每次操作独立建立 SQLite 连接，操作完毕后关闭，保持线程安全
- 方法签名与 StudyLogger 中原始方法完全一致，便于后续统一替换调用方
"""

import sqlite3
import logging
from datetime import datetime, timedelta


class RewardStore:
    """
    积分流水与奖励商店的数据库读写层。

    接受 db_path 参数，独立于 StudyLogger 运行，
    所有方法均通过 _connect() 获取 SQLite 连接。
    """

    def __init__(self, db_path: str, config: dict = None):
        """
        初始化 RewardStore。

        参数：
            db_path (str): SQLite 数据库文件的绝对路径。
            config (dict, optional): 应用配置字典。
        """
        self.db_path = db_path
        self.config = config if config is not None else {}

    @property
    def api_client(self):
        from server.utils.api_client import APIClient
        return APIClient(self.config)

    def _connect(self) -> sqlite3.Connection:
        """
        返回一个新的 SQLite 连接。

        返回：
            sqlite3.Connection: 指向 self.db_path 的数据库连接。
        """
        return sqlite3.connect(self.db_path)

    # ======================== 积分系统 CRUD ========================

    def get_balance(self):
        """
        获取当前积分余额（100% 只读本地 SQLite）。
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(amount) FROM reward_ledger")
            row = cursor.fetchone()
            conn.close()
            return round(row[0] or 0, 1)
        except Exception:
            return 0

    def add_ledger_entry(self, amount, source_type, source_id=None, description='', created_at=None):
        """
        写入一条积分流水，并防止重复入账（本地优先，异步同步）。
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()

            if source_id:
                cursor.execute(
                    "SELECT id FROM reward_ledger WHERE source_type = ? AND source_id = ?",
                    (source_type, str(source_id))
                )
                if cursor.fetchone():
                    logging.info(f"忽略重复流水: {source_type}/{source_id}")
                    conn.close()
                    return False

            now_str = created_at if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            final_desc = description
            if now_str not in description:
                final_desc = f"{description} [{now_str}]"

            cursor.execute(
                "INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, ?, ?, ?, ?)",
                (amount, source_type, source_id, final_desc, now_str)
            )
            conn.commit()
            conn.close()

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload():
                    self.api_client.post("/api/rewards/ledger", json={
                        "amount": amount,
                        "source_type": source_type,
                        "source_id": str(source_id) if source_id else None,
                        "description": final_desc
                    })
                import threading
                threading.Thread(target=upload, daemon=True).start()

            return True
        except Exception as e:
            logging.error(f"写入积分流水失败: {e}")
            return False

    def get_ledger_history(self, limit=30):
        """
        获取最近 N 条积分流水（100% 只读本地 SQLite）。
        """

        try:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM reward_ledger ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    # ======================== 自定义奖励配置 ========================

    def get_item_reward(self, item_type: str, item_id: str, default: float = 0.1) -> dict:
        """
        获取指定任务/习惯的奖励配置，返回 {'reward': x, 'penalty': y}。
        """
        if self.config.get("server_mode", False):
            ok, res = self.api_client.get(f"/api/rewards/config/{item_type}/{item_id}?default_coins={default}")
            if ok and isinstance(res, dict) and res.get("status") == "ok":
                try:
                    conn = self._connect()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT OR REPLACE INTO reward_config (item_type, item_id, coins, penalty) VALUES (?, ?, ?, ?)",
                        (item_type, item_id, res["coins"], res["penalty"])
                    )
                    conn.commit()
                    conn.close()
                except Exception as db_e:
                    logging.warning(f"同步云端奖励配置到本地失败: {db_e}")
                return {'reward': res["coins"], 'penalty': res["penalty"]}
            else:
                logging.warning("拉取云端奖励配置失败，降级本地")

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT coins, penalty FROM reward_config WHERE item_type = ? AND item_id = ?",
                (item_type, item_id)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    'reward': row[0],
                    'penalty': row[1] if row[1] is not None else row[0]
                }
            return {'reward': default, 'penalty': default}
        except Exception:
            return {'reward': default, 'penalty': default}

    def set_item_reward(self, item_type: str, item_id: str, coins: float, penalty: float = None):
        """
        设置指定任务/习惯的奖励和惩罚金币数。
        """
        if self.config.get("server_mode", False):
            ok, res = self.api_client.post("/api/rewards/config", json={
                "item_type": item_type,
                "item_id": item_id,
                "coins": coins,
                "penalty": penalty
            })
            if not ok:
                logging.error(f"设置云端奖励配置失败: {res}")
                return False

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO reward_config (item_type, item_id, coins, penalty) VALUES (?, ?, ?, ?)",
                (item_type, item_id, coins, penalty if penalty is not None else coins)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"设置奖励配置失败: {e}")
            return False

    # ======================== 外部系统奖励 ========================

    def add_external_reward(self, ext_id: str, item_type: str, item_name: str, coins: float, status: int = 0):
        """
        添加外部完成奖励记录。
        """
        if self.config.get("server_mode", False):
            ok, res = self.api_client.post("/api/rewards/external", json={
                "ext_id": ext_id,
                "item_type": item_type,
                "item_name": item_name,
                "coins": coins,
                "status": status
            })
            if not ok:
                logging.error(f"云端添加外部奖励失败: {res}")
                return False

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO external_rewards (ext_id, item_type, item_name, coins, status) VALUES (?, ?, ?, ?, ?)",
                (ext_id, item_type, item_name, coins, status)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"添加外部奖励失败: {e}")
            return False

    def get_unclaimed_rewards(self) -> list:
        """
        获取所有待领取的外部奖励。
        """
        import time
        now = time.time()
        if not hasattr(self, '_last_auto_settle') or now - self._last_auto_settle > 10:
            self.auto_settle_goals()
            self._last_auto_settle = now

        # 纯本地获取未领取奖励，避免网络阻塞

        try:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM external_rewards WHERE status = 0 ORDER BY created_at DESC"
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def claim_rewards(self, ext_ids: list) -> float:
        """
        将指定的奖励标记为已领取，并分条写入积分流水。
        """
        if not ext_ids:
            return 0.0

        if self.config.get("server_mode", False):
            ok, res = self.api_client.post("/api/rewards/claim", json={"ids": ext_ids})
            if ok and isinstance(res, dict) and res.get("status") == "ok":
                pass
            else:
                logging.error(f"云端领取奖励失败: {res}")
                return 0.0

        total_coins = 0.0
        try:
            conn = self._connect()
            cursor = conn.cursor()

            placeholders = ','.join(['?'] * len(ext_ids))
            cursor.execute(
                f"SELECT ext_id, item_name, coins, item_type FROM external_rewards WHERE status = 0 AND ext_id IN ({placeholders})",
                tuple(ext_ids)
            )
            items = cursor.fetchall()

            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            for ext_id, item_name, coins, item_type in items:
                total_coins += coins
                if item_type == 'habit':
                    desc = f"习惯打卡: {item_name}"
                elif item_type == 'task':
                    desc = f"任务完成: {item_name}"
                else:
                    desc = f"领取奖励: {item_name}"
                cursor.execute(
                    "INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, 'external_claim', ?, ?, ?)",
                    (coins, ext_id, desc, now_str)
                )

            cursor.execute(
                f"UPDATE external_rewards SET status = 1 WHERE status = 0 AND ext_id IN ({placeholders})",
                tuple(ext_ids)
            )

            conn.commit()
            conn.close()

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload():
                    self.api_client.post("/api/rewards/claim", json={"ids": ext_ids})
                import threading
                threading.Thread(target=upload, daemon=True).start()
            return total_coins
        except Exception as e:
            logging.error(f"领取外部奖励失败: {e}")
            return 0.0

    # ======================== 奖励商品 CRUD ========================

    def add_reward(self, title, icon='🎁', price=10, description='', unlock_task_id=None, unlock_task_title=None):
        """
        新增奖励商品。
        """
        new_id = None
        if self.config.get("server_mode", False):
            ok, res = self.api_client.post("/api/rewards", json={
                "title": title,
                "icon": icon,
                "price": price,
                "description": description,
                "unlock_task_id": unlock_task_id,
                "unlock_task_title": unlock_task_title
            })
            if ok and isinstance(res, dict) and res.get("status") == "ok":
                new_id = res.get("reward_id")
            else:
                logging.error(f"云端创建商品失败: {res}")
                return False

        try:
            conn = self._connect()
            cursor = conn.cursor()
            if new_id is not None:
                cursor.execute(
                    "INSERT OR REPLACE INTO rewards (id, title, icon, price, description, unlock_task_id, unlock_task_title) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (new_id, title, icon, price, description, unlock_task_id, unlock_task_title)
                )
            else:
                cursor.execute(
                    "INSERT INTO rewards (title, icon, price, description, unlock_task_id, unlock_task_title) VALUES (?, ?, ?, ?, ?, ?)",
                    (title, icon, price, description, unlock_task_id, unlock_task_title)
                )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"新增奖励失败: {e}")
            return False

    def remove_reward(self, reward_id):
        """
        软删除奖励（将 is_active 置为 0，不物理删除）。
        """
        if self.config.get("server_mode", False):
            ok, res = self.api_client.delete(f"/api/rewards/{reward_id}")
            if not ok:
                logging.error(f"云端删除商品失败: {res}")
                return False

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("UPDATE rewards SET is_active = 0 WHERE id = ?", (reward_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def update_reward(self, reward_id, title, icon='🎁', price=10, description='', unlock_task_id=None, unlock_task_title=None):
        """
        修改奖励商品配置。
        """
        if self.config.get("server_mode", False):
            ok, res = self.api_client.put(f"/api/rewards/{reward_id}", json={
                "title": title,
                "icon": icon,
                "price": price,
                "description": description,
                "unlock_task_id": unlock_task_id,
                "unlock_task_title": unlock_task_title
            })
            if not ok:
                logging.error(f"云端修改商品配置失败: {res}")
                return False

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE rewards SET title=?, icon=?, price=?, description=?, unlock_task_id=?, unlock_task_title=? WHERE id=?",
                (title, icon, price, description, unlock_task_id, unlock_task_title, reward_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"修改奖励失败: {e}")
            return False

    def buy_reward(self, reward_id):
        """
        购买奖励：检查余额 → 扣款 → 写流水，返回 (success, message)。
        """
        try:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rewards WHERE id = ? AND is_active = 1", (reward_id,))
            reward = cursor.fetchone()
            if not reward:
                conn.close()
                return False, '奖励不存在'
            price = reward['price']
            title = reward['title']

            unlock_task_id = reward['unlock_task_id'] if 'unlock_task_id' in reward.keys() else None
            unlock_task_title = reward['unlock_task_title'] if 'unlock_task_title' in reward.keys() else None

            if unlock_task_id:
                conn.close()
                available = self.get_available_unlocks(unlock_task_id, reward_id)
                if available <= 0:
                    return False, f'需要先完成条件「{unlock_task_title or "未知"}」才能兑换（或剩余额度不足）！'

                now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                source_name = unlock_task_title or unlock_task_id or '未知来源'
                desc_text = f'任务解锁兑换: {title} [来自: {source_name}]'
                conn = self._connect()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, 'reward_unlock', ?, ?, ?)",
                    (0, reward_id, desc_text, now_str)
                )

                try:
                    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
                    cursor.execute(
                        """
                        UPDATE reward_ledger
                        SET description = description || ?
                        WHERE source_id = ?
                          AND created_at >= ?
                          AND source_type != 'reward_unlock'
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (f" 🎁[解锁奖励:{title}]", str(unlock_task_id), yesterday)
                    )
                except Exception as e:
                    logging.warning(f"合并奖励描述失败: {e}")

                conn.commit()
                conn.close()

                # 云端异步双写
                if self.config.get("server_mode", False):
                    def upload_unlock():
                        self.api_client.post(f"/api/rewards/buy/{reward_id}")
                    import threading
                    threading.Thread(target=upload_unlock, daemon=True).start()

                return True, f'成功兑换「{title}」！'

            cursor.execute("SELECT SUM(amount) FROM reward_ledger")
            balance = cursor.fetchone()[0] or 0
            if balance < price:
                conn.close()
                return False, f'余额不足（需要 {price}🪙，当前 {round(balance,1)}🪙）'

            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, 'reward_buy', ?, ?, ?)",
                (-price, reward_id, f'购买奖励: {title}', now_str)
            )
            conn.commit()
            conn.close()

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload_buy():
                    self.api_client.post(f"/api/rewards/buy/{reward_id}")
                import threading
                threading.Thread(target=upload_buy, daemon=True).start()

            return True, f'成功兑换「{title}」！'
        except Exception as e:
            logging.error(f"购买奖励失败: {e}")
            return False, str(e)

    def get_available_unlocks(self, unlock_task_id: str, reward_id: int) -> int:
        """
        计算特定解锁条件剩余的兑换额度。
        """
        if not unlock_task_id:
            return 0

        try:
            conn = self._connect()
            cursor = conn.cursor()

            achieved_count = 0
            if unlock_task_id.startswith("goal_"):
                cursor.execute(
                    "SELECT COUNT(*) FROM external_rewards WHERE ext_id LIKE ? AND coins >= 0",
                    (f"{unlock_task_id}_%",)
                )
                achieved_count = cursor.fetchone()[0] or 0
            else:
                cursor.execute(
                    "SELECT 1 FROM tasks WHERE ticktick_id = ? AND status = 2",
                    (unlock_task_id,)
                )
                if cursor.fetchone():
                    achieved_count = 1
                else:
                    cursor.execute(
                        "SELECT COUNT(*) FROM external_rewards WHERE ext_id = ? OR ext_id = ?",
                        (f"task_{unlock_task_id}", f"habit_{unlock_task_id}")
                    )
                    achieved_count = cursor.fetchone()[0] or 0

            cursor.execute(
                "SELECT COUNT(*) FROM reward_ledger WHERE source_type = 'reward_unlock' AND source_id = ?",
                (reward_id,)
            )
            used_count = cursor.fetchone()[0] or 0

            conn.close()
            return max(0, achieved_count - used_count)
        except Exception as e:
            logging.error(f"获取解锁额度失败: {e}")
            return 0

    # ======================== 背包物品管理 ========================

    def get_backpack_items(self):
        """
        获取背包物品列表（所有已兑换的解锁型奖励），含使用状态。
        """
        # 纯本地获取背包物品，避免网络阻塞

        try:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT rl.id, rl.source_id as reward_id, rl.created_at,
                       r.title, r.icon, r.description,
                       r.unlock_task_title,
                       COALESCE(rl.description, '') as memo
                FROM reward_ledger rl
                LEFT JOIN rewards r ON r.id = rl.source_id
                WHERE rl.source_type = 'reward_unlock'
                ORDER BY rl.created_at DESC
                """
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logging.error(f"获取背包失败: {e}")
            return []

    def mark_backpack_item_used(self, ledger_id: int):
        """
        将背包物品标记为已使用（在 description 末尾追加 [已使用]）。
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reward_ledger SET description = description || ' [已使用]' WHERE id = ? AND source_type = 'reward_unlock' AND description NOT LIKE '%[已使用]%'",
                (ledger_id,)
            )
            conn.commit()
            conn.close()

            # 云端异步双写
            if self.config.get("server_mode", False) and cursor.rowcount > 0:
                def upload_use():
                    self.api_client.post(f"/api/rewards/use_item/{ledger_id}")
                import threading
                threading.Thread(target=upload_use, daemon=True).start()

            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"标记使用失败: {e}")
            return False

    # ======================== 重置功能 ========================

    def reset_coins(self):
        """
        重置金币：清空积分流水表和待领取外部奖励表。
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reward_ledger")
            cursor.execute("DELETE FROM external_rewards")
            conn.commit()
            conn.close()

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload_reset():
                    self.api_client.post("/api/rewards/reset")
                import threading
                threading.Thread(target=upload_reset, daemon=True).start()

            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                from server.utils.config import load_or_create_config, save_config
                config = load_or_create_config()
                config["last_reset_time"] = now_str
                save_config(config)
            except Exception as cfg_e:
                logging.warning(f"重置金币后更新配置失败: {cfg_e}")

            return True
        except Exception as e:
            logging.error(f"重置金币失败: {e}")
            return False


    # ======================== 目标自动结算（依赖项，供 get_unclaimed_rewards 调用）========================

    def auto_settle_goals(self):
        """
        自动结算目标挑战（由 get_unclaimed_rewards 内部调用）。
        """
        try:
            from server.models.goal_store import GoalStore
            from server.utils.config import load_or_create_config
            config = load_or_create_config()
            GoalStore(self.db_path, config).auto_settle_goals()

            # 自动领取所有未领取的 goal 类型奖励/惩罚，使其直接进入金币流水
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM external_rewards WHERE item_type = 'goal' AND status = 0")
            goal_ids = [r[0] for r in cursor.fetchall()]
            conn.close()

            if goal_ids:
                self.claim_rewards(goal_ids)
        except Exception as e:
            logging.error(f"RewardStore 自动结算并领取目标奖励失败: {e}")
