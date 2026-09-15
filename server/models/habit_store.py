# -*- coding: utf-8 -*-
"""
习惯存储模块 (habit_store.py)
==============================
独立封装习惯系统的全部数据库读写逻辑。

设计原则：
- HabitStore 仅依赖 db_path（SQLite 数据库文件路径），不依赖 StudyLogger 或任何 UI 组件。
- 方法签名与 database.py 中的原始实现完全一致，调用方无需修改参数。
- 连接方式与 StudyLogger._get_connection() 的 SQLite 分支保持一致。

包含的功能：
- 习惯 CRUD：add_habit / update_habit / remove_habit / get_all_habits
- 打卡操作：toggle_checkin / get_today_checkins / get_checkins_by_date_range
- 连续天数：get_habit_streak / _calc_streak
- 自动标记：auto_mark_missed_habits
- 表结构迁移：_migrate_habits_table
"""

import sqlite3
import logging
from datetime import datetime, timedelta


class HabitStore:
    """
    习惯系统数据存储类。

    只依赖 SQLite 数据库文件路径，不依赖 StudyLogger 或任何其他模块。
    所有方法签名与 database.py 中的原始实现完全一致。

    使用示例::

        store = HabitStore(db_path='/path/to/my_time_logger.db')
        habit_id = store.add_habit('早起', icon='🌅', difficulty='medium')
        store.toggle_checkin(habit_id)
    """

    # ==================== 难度 & 积分常量 ====================
    DIFFICULTY_MAP = {
        'trivial': {'task_coins': 1,  'habit_coins': 0.5, 'streak_bonus': 0.1, 'penalty': 0.25, 'color': '#4CAF50'},
        'easy':    {'task_coins': 2,  'habit_coins': 1,   'streak_bonus': 0.2, 'penalty': 0.5,  'color': '#2196F3'},
        'medium':  {'task_coins': 5,  'habit_coins': 2.5, 'streak_bonus': 0.5, 'penalty': 1.25, 'color': '#FF9800'},
        'hard':    {'task_coins': 10, 'habit_coins': 5,   'streak_bonus': 1.0, 'penalty': 2.5,  'color': '#FF5252'},
    }
    PRIORITY_TO_DIFFICULTY = {5: 'hard', 3: 'medium', 1: 'easy', 0: 'trivial'}
    FORCE_CHANGE_FEE = 1.0  # 10s 强改手续费（积分）

    def __init__(self, db_path: str, config: dict = None):
        """
        初始化 HabitStore。

        :param db_path: SQLite 数据库文件的绝对路径，例如 '/data/my_time_logger.db'
        :param config: 配置文件字典，可选
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

        与 StudyLogger._get_connection() 的 SQLite 分支保持一致：
        每次调用均创建新连接，由调用方负责关闭。

        :return: sqlite3.Connection 对象
        """
        return sqlite3.connect(self.db_path)

    # ======================== 表结构迁移 ========================

    def _migrate_habits_table(self):
        """
        旧表迁移：若 habits / habit_checkins / reward_ledger / rewards 等表
        缺少新字段则执行 ALTER TABLE 补全，并创建缺失的关联表。

        此方法幂等，可安全地多次调用。
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()

            # ---- habits 表字段补全 ----
            cursor.execute("PRAGMA table_info(habits)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'icon' not in cols:
                cursor.execute("ALTER TABLE habits ADD COLUMN icon TEXT NOT NULL DEFAULT '✅'")
            if 'color' not in cols:
                cursor.execute("ALTER TABLE habits ADD COLUMN color TEXT NOT NULL DEFAULT '#A3BE8C'")
            if 'frequency' not in cols:
                cursor.execute("ALTER TABLE habits ADD COLUMN frequency TEXT NOT NULL DEFAULT 'daily'")
            if 'sort_order' not in cols:
                cursor.execute("ALTER TABLE habits ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            if 'is_active' not in cols:
                # is_active = 0 表示正常（未归档），与 TickTick 一致
                cursor.execute("ALTER TABLE habits ADD COLUMN is_active INTEGER NOT NULL DEFAULT 0")
            if 'created_at' not in cols:
                cursor.execute("ALTER TABLE habits ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            if 'difficulty' not in cols:
                cursor.execute("ALTER TABLE habits ADD COLUMN difficulty TEXT DEFAULT 'easy'")

            # ---- habit_checkins 表 ----
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS habit_checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL,
                    checkin_date TEXT NOT NULL,
                    checkin_time TEXT,
                    note TEXT DEFAULT '',
                    FOREIGN KEY (habit_id) REFERENCES habits(id)
                )
            ''')
            cursor.execute("PRAGMA table_info(habit_checkins)")
            checkin_cols = [c[1] for c in cursor.fetchall()]
            if 'status' not in checkin_cols:
                cursor.execute("ALTER TABLE habit_checkins ADD COLUMN status INTEGER DEFAULT 1")

            # ---- reward_ledger 表（积分流水，打卡奖惩依赖） ----
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reward_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id INTEGER,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # ---- rewards 表（奖励商品，供 reward_shop 使用） ----
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rewards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    icon TEXT DEFAULT '🎁',
                    price REAL NOT NULL DEFAULT 10,
                    description TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute("PRAGMA table_info(rewards)")
            reward_cols = [c[1] for c in cursor.fetchall()]
            if 'unlock_task_id' not in reward_cols:
                cursor.execute("ALTER TABLE rewards ADD COLUMN unlock_task_id TEXT DEFAULT NULL")
                cursor.execute("ALTER TABLE rewards ADD COLUMN unlock_task_title TEXT DEFAULT NULL")

            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"习惯表迁移失败: {e}")

    # ======================== 习惯 CRUD ========================

    def get_all_habits(self) -> list:
        """
        获取所有启用（is_active=1）的习惯，按 sort_order 升序排列。

        :return: 习惯字典列表，每个元素对应 habits 表的一行
        """
        if self.config.get("server_mode", False):
            ok, res = self.api_client.get("/api/habits")
            if ok and isinstance(res, dict) and res.get("status") == "ok":
                try:
                    conn = self._connect()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM habits")
                    for idx, h in enumerate(res.get("habits", [])):
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO habits
                                (id, title, icon, color, frequency, category_id, sort_order, is_active, difficulty, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                h["id"],
                                h["name"],
                                h.get("icon") or "✅",
                                h.get("color") or "#A3BE8C",
                                h.get("frequency") or "daily",
                                h.get("category_id"),
                                h.get("sort_order") or idx,
                                h.get("is_active", 1),
                                h.get("difficulty") or "medium",
                                h.get("created_at")
                            )
                        )
                    conn.commit()
                    conn.close()
                except Exception as db_e:
                    logging.warning(f"同步云端习惯到本地失败: {db_e}")
            else:
                logging.warning("从云端获取习惯列表失败，降级本地")

        try:
            self._migrate_habits_table()
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # is_active = 0 表示正常（未归档），与 TickTick 一致
            cursor.execute("SELECT * FROM habits WHERE is_active = 0 ORDER BY sort_order ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logging.error(f"获取习惯列表失败: {e}")
            return []

    def add_habit(
        self,
        title: str,
        icon: str = '✅',
        color: str = '#A3BE8C',
        frequency: str = 'daily',
        category_id=None,
        difficulty: str = 'easy',
    ):
        """
        新增一条习惯记录。
        """
        new_id = None
        if self.config.get("server_mode", False):
            ok, res = self.api_client.post("/api/habits", json={
                "name": title,
                "icon": icon,
                "difficulty": difficulty
            })
            if ok and isinstance(res, dict) and res.get("status") == "ok":
                new_id = res.get("habit_id")
            else:
                logging.error(f"云端创建习惯失败: {res}")
                return None

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(sort_order) FROM habits")
            max_order = cursor.fetchone()[0] or 0
            if new_id is not None:
                cursor.execute(
                    '''
                    INSERT INTO habits
                        (id, title, icon, color, frequency, category_id, sort_order, is_active,
                         difficulty)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                    ''',
                    (new_id, title, icon, color, frequency, category_id, max_order + 1,
                     difficulty),
                )
                conn.commit()
                conn.close()
                from server.utils.utils import mark_pending_sync
                mark_pending_sync(self.db_path, 'habits', new_id, self.config)
                return new_id
            else:
                cursor.execute(
                    '''
                    INSERT INTO habits
                        (title, icon, color, frequency, category_id, sort_order, is_active,
                         difficulty)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                    ''',
                    (title, icon, color, frequency, category_id, max_order + 1,
                     difficulty),
                )
                new_id = cursor.lastrowid
                conn.commit()
                conn.close()
                from server.utils.utils import mark_pending_sync
                mark_pending_sync(self.db_path, 'habits', new_id, self.config)
                return new_id
        except Exception as e:
            logging.error(f"新增习惯失败: {e}")
            return None

    def update_habit(self, habit_id: int, **kwargs) -> bool:
        """
        更新习惯的一个或多个属性。
        """
        if self.config.get("server_mode", False):
            payload = {}
            if 'title' in kwargs: payload['name'] = kwargs['title']
            if 'icon' in kwargs: payload['icon'] = kwargs['icon']
            if 'difficulty' in kwargs: payload['difficulty'] = kwargs['difficulty']
            if 'is_active' in kwargs: payload['is_active'] = kwargs['is_active']
            ok, res = self.api_client.put(f"/api/habits/{habit_id}", json=payload)
            if not ok:
                logging.error(f"云端更新习惯失败: {res}")
                return False

        try:
            conn = self._connect()
            cursor = conn.cursor()
            updates, params = [], []
            for key in [
                'title', 'icon', 'color', 'frequency', 'category_id',
                'sort_order', 'difficulty',
            ]:
                if key in kwargs:
                    updates.append(f"{key} = ?")
                    params.append(kwargs[key])
            if not updates:
                return False
            params.append(habit_id)
            cursor.execute(
                f"UPDATE habits SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
            conn.commit()
            conn.close()
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.db_path, 'habits', habit_id, self.config)
            return True
        except Exception as e:
            logging.error(f"更新习惯失败: {e}")
            return False

    def remove_habit(self, habit_id: int) -> bool:
        """
        软删除习惯（将 is_active 置为 1 表示归档，与 TickTick 一致）。
        """
        if self.config.get("server_mode", False):
            # is_active = 1 表示归档（与 TickTick 一致）
            ok, res = self.api_client.put(f"/api/habits/{habit_id}", json={"is_active": 1})
            if not ok:
                logging.error(f"云端删除习惯失败: {res}")
                return False

        try:
            conn = self._connect()
            cursor = conn.cursor()
            # is_active = 1 表示归档
            cursor.execute("UPDATE habits SET is_active = 1 WHERE id = ?", (habit_id,))
            conn.commit()
            conn.close()
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.db_path, 'habits', habit_id, self.config)
            return True
        except Exception as e:
            logging.error(f"删除习惯失败: {e}")
            return False

    # ======================== 打卡操作 ========================

    def toggle_checkin(self, habit_id: int, date_str: str = None, force: bool = False):
        """
        打卡状态三态轮转（带积分入账）：
        """
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        if self.config.get("server_mode", False):
            try:
                # 查今日习惯打卡
                ok_get, res_get = self.api_client.get(f"/api/habits/today_checkins?date={date_str}")
                if ok_get and isinstance(res_get, dict) and res_get.get("status") == "ok":
                    checkins = res_get.get("checkins", [])
                    is_checked = any(c["habit_id"] == habit_id for c in checkins)
                    if is_checked:
                        ok_call, res_call = self.api_client.delete(f"/api/habits/{habit_id}/checkin?date={date_str}")
                        if not ok_call:
                            logging.error("云端取消打卡失败")
                            return 0, 0, 0
                    else:
                        ok_call, res_call = self.api_client.post(f"/api/habits/{habit_id}/checkin", json={"date": date_str})
                        if not ok_call:
                            logging.error("云端打卡失败")
                            return 0, 0, 0
                else:
                    logging.error("从云端查询今日打卡失败")
                    return 0, 0, 0
            except Exception as call_e:
                logging.error(f"云端打卡交互异常: {call_e}")
                return 0, 0, 0

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, status, checkin_time FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?",
                (habit_id, date_str),
            )
            existing = cursor.fetchone()

            now = datetime.now()
            now_time = now.strftime('%Y-%m-%d %H:%M:%S')

            # 获取习惯难度与名称
            cursor.execute("SELECT difficulty, title FROM habits WHERE id = ?", (habit_id,))
            h_row = cursor.fetchone()
            diff = (h_row[0] if h_row and h_row[0] else 'easy')
            h_title = (h_row[1] if h_row else '未知习惯')
            diff_info = self.DIFFICULTY_MAP.get(diff, self.DIFFICULTY_MAP['easy'])

            coins_earned = 0  # 本次操作的积分变动

            if existing:
                rec_id = existing[0]
                curr_status = existing[1]
                c_time = existing[2]

                # 检查是否超过 10 秒
                if c_time and not force:
                    try:
                        try:
                            last_dt = datetime.strptime(c_time, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            last_dt = datetime.strptime(f"{date_str} {c_time}", '%Y-%m-%d %H:%M:%S')
                        if (now - last_dt).total_seconds() > 10:
                            conn.close()
                            return "timeout", 0, 0
                    except Exception:
                        pass

                # 强改手续费
                if force:
                    cursor.execute(
                        "INSERT INTO reward_ledger (amount, source_type, source_id, description) VALUES (?, 'penalty', ?, ?)",
                        (-self.FORCE_CHANGE_FEE, habit_id, f'10s强改手续费: {h_title}'),
                    )
                    coins_earned -= self.FORCE_CHANGE_FEE

                if curr_status == 2:
                    cursor.execute(
                        "UPDATE habit_checkins SET status = 1, checkin_time = ? WHERE id = ?",
                        (now_time, rec_id),
                    )
                    new_status = 1
                else:
                    cursor.execute("DELETE FROM habit_checkins WHERE id = ?", (rec_id,))
                    new_status = 0
            else:
                cursor.execute(
                    "INSERT INTO habit_checkins (habit_id, checkin_date, checkin_time, status) VALUES (?, ?, ?, 2)",
                    (habit_id, date_str, now_time),
                )
                new_status = 2

            conn.commit()
            streak = self._calc_streak(
                cursor, habit_id, date_str,
                exclude_today=(new_status <= 0 and date_str == datetime.now().strftime('%Y-%m-%d')),
            )

            # 积分入账（仅成功打卡时）
            if new_status == 2:
                base = diff_info['habit_coins']
                bonus = streak * diff_info['streak_bonus']
                total = round(base + bonus, 1)

                # 判断是否为补卡
                today_str = datetime.now().strftime('%Y-%m-%d')
                is_makeup = (date_str != today_str)
                if is_makeup:
                    total = round(total * 0.5, 1)
                    try:
                        dt = datetime.strptime(date_str, '%Y-%m-%d')
                        date_lbl = dt.strftime('%m-%d')
                    except Exception:
                        date_lbl = date_str[5:10] if len(date_str) >= 10 else date_str
                    description = f"习惯补卡[{date_lbl}]: {h_title} (🔥{streak})"
                else:
                    description = f"习惯打卡: {h_title} (🔥{streak})"

                cursor.execute(
                    "INSERT INTO reward_ledger (amount, source_type, source_id, description) VALUES (?, 'habit_checkin', ?, ?)",
                    (total, habit_id, description),
                )
                coins_earned += total
                conn.commit()

            # 标记待同步：habit_checkins + 如有 reward_ledger 条目
            from server.utils.utils import mark_pending_sync
            checkin_id = existing[0] if existing else cursor.lastrowid
            mark_pending_sync(self.db_path, 'habit_checkins', checkin_id, self.config)
            if coins_earned != 0:
                # reward_ledger 条目由 SyncWorker 扫描 pushed_at=NULL 处理
                pass

            conn.close()
            return new_status, streak, coins_earned
        except Exception as e:
            logging.error(f"打卡操作失败: {e}")
            return 0, 0, 0

    def _calc_streak(
        self,
        cursor: sqlite3.Cursor,
        habit_id: int,
        today_str: str,
        exclude_today: bool = False,
    ) -> int:
        """
        计算指定习惯的连续成功打卡天数。
        """
        try:
            today = datetime.strptime(today_str, '%Y-%m-%d').date()
            streak = 0
            check_date = today if not exclude_today else today - timedelta(days=1)
            while True:
                date_s = check_date.strftime('%Y-%m-%d')
                cursor.execute(
                    "SELECT status FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?",
                    (habit_id, date_s),
                )
                row = cursor.fetchone()
                if row and row[0] == 2:
                    streak += 1
                    check_date -= timedelta(days=1)
                else:
                    break
            return streak
        except Exception:
            return 0

    def get_today_checkins(self, date_str: str = None) -> dict:
        """
        获取指定日期所有习惯的打卡状态。
        """
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        if self.config.get("server_mode", False):
            try:
                ok, res = self.api_client.get(f"/api/habits/today_checkins?date={date_str}")
                if ok and isinstance(res, dict) and res.get("status") == "ok":
                    conn = self._connect()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM habit_checkins WHERE checkin_date = ?", (date_str,))
                    for c in res.get("checkins", []):
                        cursor.execute(
                            "INSERT OR REPLACE INTO habit_checkins (habit_id, checkin_date, checkin_time, status) VALUES (?, ?, ?, 2)",
                            (c["habit_id"], date_str, c.get("created_at"))
                        )
                    conn.commit()
                    conn.close()
            except Exception as e:
                logging.warning(f"同步今日云端打卡失败: {e}")

        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT habit_id, status FROM habit_checkins WHERE checkin_date = ?",
                (date_str,),
            )
            result = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()
            return result
        except Exception as e:
            logging.error(f"获取今日打卡失败: {e}")
            return {}


    def get_checkins_by_date_range(self, start_date_str: str, end_date_str: str) -> dict:
        """
        批量获取指定日期范围内的打卡数据。

        :param start_date_str: 起始日期（'YYYY-MM-DD'，含）
        :param end_date_str: 结束日期（'YYYY-MM-DD'，含）
        :return: {habit_id: {date_str: status}} 嵌套字典
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT habit_id, checkin_date, status FROM habit_checkins "
                "WHERE checkin_date BETWEEN ? AND ?",
                (start_date_str, end_date_str),
            )
            result = {}
            for row in cursor.fetchall():
                hid, d, s = row[0], row[1], row[2]
                if hid not in result:
                    result[hid] = {}
                result[hid][d] = s
            conn.close()
            return result
        except Exception as e:
            logging.error(f"获取范围打卡失败: {e}")
            return {}

    def get_habit_streak(self, habit_id: int) -> int:
        """
        获取某个习惯截至今天的连续成功打卡天数。

        :param habit_id: 习惯 ID
        :return: 连续成功天数（int），异常时返回 0
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            today_str = datetime.now().strftime('%Y-%m-%d')
            streak = self._calc_streak(cursor, habit_id, today_str)
            conn.close()
            return streak
        except Exception:
            return 0

    def auto_mark_missed_habits(self):
        """
        [已禁用] 本地习惯管理不设截止时间。
        """
        return
