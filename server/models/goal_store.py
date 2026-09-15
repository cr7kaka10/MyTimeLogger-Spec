# -*- coding: utf-8 -*-
"""
目标挑战存储模块 (goal_store.py)
=================================
封装目标挑战系统（Goals）的全部数据库读写逻辑。

GoalStore 是一个独立的存储层，不依赖 StudyLogger，
仅通过 db_path 字符串连接 SQLite 数据库。

主要功能：
- 添加、删除、更新目标
- 查询所有激活目标
- 自动结算目标（奖励/惩罚写入 external_rewards 表）
- 计算目标当前进度
- 获取目标每日统计趋势
"""

import sqlite3
import logging
from datetime import datetime, timedelta


class GoalStore:
    """
    目标挑战系统的数据库存储层。

    接受 db_path 参数，独立于 StudyLogger，
    直接操作 SQLite 数据库中的 goals / external_rewards / study_sessions 表。

    参数
    ----
    db_path : str
        SQLite 数据库文件的绝对路径。
    config : dict, optional
        应用配置字典，用于读取 last_reset_time 等配置项。
        若不传则使用空字典（结算时 last_reset_time 默认为 '2026-05-01 00:00:00'）。
    """

    def __init__(self, db_path: str, config: dict = None):
        """
        初始化 GoalStore。

        参数
        ----
        db_path : str
            SQLite 数据库文件路径。
        config : dict, optional
            应用配置字典，主要用于读取 last_reset_time。
        """
        self.db_path = db_path
        self.config = config if config is not None else {}
        self._cached_sessions = None
        self._cached_ledger_source_ids = None

    @property
    def api_client(self):
        from server.utils.api_client import APIClient
        return APIClient(self.config)

    def _connect(self) -> sqlite3.Connection:
        """
        创建并返回一个新的 SQLite 连接。

        返回
        ----
        sqlite3.Connection
            指向 self.db_path 的 SQLite 连接对象。
        """
        return sqlite3.connect(self.db_path)

    # ======================== 目标 CRUD ========================

    def add_goal(self, title, category_id, metric, target_value, period,
                 reward_coins, reward_id=None, operator='>=', penalty_coins=None):
        """
        添加新目标。

        参数
        ----
        title : str
            目标标题。
        category_id : int
            关联的时间分类 ID。
        metric : str
            统计指标，'duration'（时长/分钟）或 'count'（次数）。
        target_value : float
            目标值（分钟数或次数）。
        period : str
            周期类型：'daily'、'weekly'、'monthly' 或 'per_session'。
        reward_coins : float
            达成目标时的奖励金币数。
        reward_id : int, optional
            关联的兑换项 ID，默认为 None。
        operator : str, optional
            比较运算符，'>=' 或 '<='，默认为 '>='。
        penalty_coins : float, optional
            未达标时的惩罚金币数，默认与 reward_coins 相同。

        返回
        ----
        bool
            成功返回 True，失败返回 False。
        """
        try:
            if penalty_coins is None:
                penalty_coins = reward_coins
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn = self._connect()
            cursor = conn.cursor()
            sql = (
                "INSERT INTO goals "
                "(title, category_id, metric, target_value, period, reward_coins, "
                "reward_id, operator, penalty_coins, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)"
            )
            cursor.execute(sql, (
                title, category_id, metric, target_value, period,
                reward_coins, reward_id, operator, penalty_coins, now_str
            ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"添加目标失败: {e}")
            return False

    def remove_goal(self, goal_id):
        """
        软删除目标（将 is_active 置为 0）。

        参数
        ----
        goal_id : int
            目标的数据库 ID。

        返回
        ----
        bool
            成功返回 True，失败返回 False。
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("UPDATE goals SET is_active = 0 WHERE id = ?", (goal_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def update_goal(self, goal_id, **kwargs):
        """
        更新目标的指定字段。

        参数
        ----
        goal_id : int
            目标的数据库 ID。
        **kwargs
            要更新的字段名和对应的新值，例如 title='新标题', target_value=60。

        返回
        ----
        bool
            成功返回 True，失败返回 False。
        """
        if not kwargs:
            return False
        try:
            conn = self._connect()
            cursor = conn.cursor()
            fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
            values = list(kwargs.values())
            values.append(goal_id)
            cursor.execute(f"UPDATE goals SET {fields} WHERE id = ?", values)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"更新目标失败: {e}")
            return False

    def get_all_goals(self):
        """
        获取所有激活的目标列表（is_active = 1），按创建时间倒序排列。

        返回
        ----
        list[dict]
            目标字典列表，每个字典对应 goals 表的一行记录。
            若查询失败则返回空列表。
        """
        try:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM goals WHERE is_active = 1 ORDER BY created_at DESC"
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    # ======================== 目标结算 ========================

    def auto_settle_goals(self):
        """
        自动结算单次和每日目标（包括成功和失败）。

        结算逻辑：
        - per_session：每次专注会话结束后立即结算，达标奖励，未达标惩罚。
        - daily：
            - 昨天：无论成败均结算。
            - 今天：仅在确定状态时提前结算（>= 已达成 或 <= 已超限）。

        结算结果写入 external_rewards 表，使用唯一 claim_id 防止重复结算。
        结算时间不早于目标创建时间，也不早于 config 中的 last_reset_time。
        """
        try:
            from datetime import date, timedelta
            today = date.today()
            yesterday = today - timedelta(days=1)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if self.config.get("server_mode", False):
                # 异步通知云端进行目标自动结算以对齐奖励，主线程退回本地进行即时结算
                def async_settle():
                    self.api_client.post("/api/goals/auto_settle")
                import threading
                threading.Thread(target=async_settle, daemon=True).start()

            conn = self._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM goals WHERE is_active = 1")
            goals = [dict(r) for r in cursor.fetchall()]

            for g in goals:
                g_id = g['id']
                title = g['title']
                cat_id = g['category_id']
                period = g['period']
                metric = g['metric']
                target = g['target_value']
                operator = g.get('operator', '>=')
                reward_coins = g['reward_coins']
                penalty_coins = g.get('penalty_coins', reward_coins)
                created_at_goal = g.get('created_at', '2000-01-01')  # 目标创建时间

                def _issue(claim_id, is_met, val, target_val, operator_str,
                           date_str, fail_if_not_met=False):
                    """
                    向 external_rewards 表写入一条结算记录（幂等，已存在则跳过）。

                    参数
                    ----
                    claim_id : str
                        唯一结算标识符，防止重复结算。
                    is_met : bool
                        是否达成目标。
                    val : float
                        实际完成值。
                    target_val : float
                        目标值。
                    operator_str : str
                        比较运算符字符串（'>=' 或 '<='）。
                    date_str : str
                        结算日期字符串（YYYY-MM-DD）。
                    fail_if_not_met : bool, optional
                        若为 True，未达标时写入惩罚记录；默认 False（不写入）。
                    """
                    cursor.execute(
                        "SELECT 1 FROM external_rewards WHERE ext_id = ?", (claim_id,)
                    )
                    if cursor.fetchone():
                        return

                    amount, desc = 0, ""
                    unit = "m" if metric == 'duration' else "次"
                    status_text = "达成" if is_met else "未达标"
                    # 详细描述：目标达成[2026-05-05]: 标题 (实际 45m / 目标 <=60m)
                    desc = (
                        f"目标{status_text}[{date_str}]: {title} "
                        f"({int(val)}{unit} / {operator_str}{int(target_val)}{unit})"
                    )

                    if is_met:
                        amount = reward_coins
                    elif fail_if_not_met:
                        amount = -abs(penalty_coins)
                    else:
                        return

                    if amount != 0:
                        cursor.execute(
                            "INSERT INTO external_rewards "
                            "(ext_id, item_type, item_name, coins, status, created_at) "
                            "VALUES (?, 'goal', ?, ?, 0, ?)",
                            (claim_id, desc, amount, now_str)
                        )

                last_reset_str = self.config.get(
                    "last_reset_time", "2026-05-01 00:00:00"
                )

                if period == 'per_session':
                    cursor.execute(
                        "SELECT id, net_duration_minutes, start_time "
                        "FROM study_sessions "
                        "WHERE category_id = ? AND date = ? AND start_time > ?",
                        (cat_id, today.strftime('%Y-%m-%d'), last_reset_str)
                    )
                    for s_id, s_dur, s_time in cursor.fetchall():
                        # 会话开始时间也必须在目标创建之后
                        if s_time < created_at_goal:
                            continue
                        is_met = (
                            (s_dur >= target) if operator == '>='
                            else (s_dur <= target)
                        )
                        # 单次目标每次完成后立刻结算
                        _issue(
                            f"goal_{g_id}_session_{s_id}",
                            is_met, s_dur, target, operator, s_time[:10],
                            fail_if_not_met=True
                        )

                elif period == 'daily':
                    for d in [yesterday, today]:
                        d_str = d.strftime('%Y-%m-%d')
                        # 核心修正：结算日期不能早于目标创建日期
                        if d_str < created_at_goal[:10]:
                            continue

                        if d_str < last_reset_str[:10]:
                            continue

                        if metric == 'duration':
                            cursor.execute(
                                "SELECT SUM(net_duration_minutes) "
                                "FROM study_sessions "
                                "WHERE category_id = ? AND date = ? AND start_time > ?",
                                (cat_id, d_str, last_reset_str)
                            )
                        else:
                            cursor.execute(
                                "SELECT COUNT(*) "
                                "FROM study_sessions "
                                "WHERE category_id = ? AND date = ? AND start_time > ?",
                                (cat_id, d_str, last_reset_str)
                            )
                        val = cursor.fetchone()[0] or 0.0

                        is_met = (
                            (val >= target) if operator == '>='
                            else (val <= target)
                        )
                        claim_id = f"goal_{g_id}_{d_str.replace('-', '')}"

                        if d == yesterday:
                            # 昨天已结束，无论成败均结算
                            _issue(
                                claim_id, is_met, val, target, operator,
                                d_str, fail_if_not_met=True
                            )
                        else:
                            # 今天：仅在确定状态（>= 达成 或 <= 失败）时提前结算
                            if operator == '>=' and is_met:
                                _issue(claim_id, True, val, target, operator, d_str)
                            elif operator == '<=' and not is_met:
                                _issue(
                                    claim_id, False, val, target, operator,
                                    d_str, fail_if_not_met=True
                                )
                            # 对于 <= 且当前未超限的情况，必须等到明天结算

            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"目标自动结算失败: {e}")

    # ======================== 目标进度查询 ========================

    def get_goal_progress(self, goal_dict, active_session_info=None):
        """
        计算目标的当前进度。

        参数
        ----
        goal_dict : dict
            目标字典，包含 id、metric、period、category_id、operator、target_value 等字段。
        active_session_info : dict, optional
            当前正在计时的会话信息，包含 category_id 和 duration_minutes。
            用于实时叠加进行中的专注时长。

        返回
        ----
        tuple[float, bool, str]
            (当前进度值, 是否已领取, claim_id)
            - 当前进度值：时长（分钟）或次数
            - 是否已领取：True 表示该周期奖励已写入 external_rewards
            - claim_id：本周期的唯一结算标识符
        """
        import calendar

        metric = goal_dict['metric']
        period = goal_dict['period']
        cat_id = goal_dict['category_id']

        # 计算起止日期
        from datetime import date
        today = date.today()
        start_date = today
        end_date = today

        if period == 'daily':
            start_date = today
            end_date = today
        elif period == 'weekly':
            # 周一为起点
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        elif period == 'monthly':
            start_date = today.replace(day=1)
            _, last_day = calendar.monthrange(today.year, today.month)
            end_date = today.replace(day=last_day)

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        operator = goal_dict.get('operator', '>=')
        target = goal_dict.get('target_value', 0)

        # 纯本地计算目标进度以解决网络延迟导致的UI卡顿

        try:
            conn = self._connect()
            cursor = conn.cursor()

            if period == 'per_session':
                # "每次" 逻辑：查找今日最近一次尚未领取的达标记录
                # 首先找到今日该分类的所有 session id
                cursor.execute(
                    "SELECT id, net_duration_minutes "
                    "FROM study_sessions "
                    "WHERE category_id = ? AND date = ? ORDER BY id DESC",
                    (cat_id, today.strftime('%Y-%m-%d'))
                )
                sessions = cursor.fetchall()

                val = 0
                claim_id = ""
                is_claimed = False

                # 寻找最新一个符合条件的且未领取的 session
                for s_id, s_dur in sessions:
                    # 检查达标条件
                    met = False
                    if operator == '>=':
                        met = (s_dur >= target)
                    else:
                        met = (s_dur <= target)

                    if met:
                        c_id = f"goal_{goal_dict['id']}_session_{s_id}"
                        cursor.execute(
                            "SELECT 1 FROM external_rewards WHERE ext_id = ?", (c_id,)
                        )
                        if cursor.fetchone():
                            # 已领取，继续找下一个（或者如果这是最新的，就显示已完成）
                            if not claim_id:
                                claim_id = c_id
                                is_claimed = True
                                val = s_dur
                            continue
                        else:
                            # 找到了一个符合条件且未领取的
                            val = s_dur
                            claim_id = c_id
                            is_claimed = False
                            break

                # 如果完全没找到 session，尝试使用当前计时器
                if not sessions and active_session_info:
                    a_cat_id = active_session_info.get('category_id')
                    a_duration = active_session_info.get('duration_minutes', 0)
                    if a_cat_id == cat_id:
                        val = a_duration
                        # 当前计时器无法领取，因为它还没入库

                conn.close()
                return val, is_claimed, claim_id

            # 以下为累计型逻辑 (daily/weekly/monthly)
            if metric == 'duration':
                # 计算累计时长
                cursor.execute(
                    "SELECT SUM(net_duration_minutes) "
                    "FROM study_sessions "
                    "WHERE category_id = ? AND date BETWEEN ? AND ?",
                    (cat_id, start_str, end_str)
                )
                val = cursor.fetchone()[0] or 0.0
            else:
                # 计算累计次数
                cursor.execute(
                    "SELECT COUNT(*) "
                    "FROM study_sessions "
                    "WHERE category_id = ? AND date BETWEEN ? AND ?",
                    (cat_id, start_str, end_str)
                )
                val = cursor.fetchone()[0] or 0

            # 实时进度叠加：如果当前正在计时且分类匹配
            if active_session_info:
                a_cat_id = active_session_info.get('category_id')
                a_duration = active_session_info.get('duration_minutes', 0)
                if a_cat_id == cat_id:
                    if metric == 'duration':
                        val += a_duration
                    # 次数通常在结束后结算，实时刷新不计次

            # 检查是否已领取
            period_tag = start_str.replace('-', '')
            if period == 'weekly':
                period_tag = f"{start_date.year}W{start_date.isocalendar()[1]}"
            elif period == 'monthly':
                period_tag = start_date.strftime('%Y%m')

            claim_id = f"goal_{goal_dict['id']}_{period_tag}"
            cursor.execute(
                "SELECT 1 FROM external_rewards WHERE ext_id = ?", (claim_id,)
            )
            is_claimed = cursor.fetchone() is not None

            conn.close()
            return val, is_claimed, claim_id
        except Exception as e:
            logging.error(f"计算目标进度失败: {e}")
            return 0, False, ""

    def get_goal_daily_stats(self, goal_dict, start_str, end_str):
        """
        获取目标在指定日期范围内的每日进度统计。

        参数
        ----
        goal_dict : dict
            目标字典，包含 metric、category_id、period 等字段。
        start_str : str
            起始日期字符串，格式 'YYYY-MM-DD'。
        end_str : str
            结束日期字符串，格式 'YYYY-MM-DD'。

        返回
        ----
        dict[str, float]
            以日期字符串为键、当日进度值为值的字典，格式 {'YYYY-MM-DD': value}。
            单次目标（per_session）不提供每日趋势，返回空字典。
            若查询失败则返回空字典。
        """
        metric = goal_dict['metric']
        cat_id = goal_dict['category_id']
        period = goal_dict['period']

        # 单次目标不提供每日趋势
        if period == 'per_session':
            return {}

        try:
            conn = self._connect()
            cursor = conn.cursor()

            if metric == 'duration':
                cursor.execute(
                    "SELECT date, SUM(net_duration_minutes) "
                    "FROM study_sessions "
                    "WHERE category_id = ? AND date BETWEEN ? AND ? "
                    "GROUP BY date",
                    (cat_id, start_str, end_str)
                )
            else:
                cursor.execute(
                    "SELECT date, COUNT(*) "
                    "FROM study_sessions "
                    "WHERE category_id = ? AND date BETWEEN ? AND ? "
                    "GROUP BY date",
                    (cat_id, start_str, end_str)
                )

            rows = cursor.fetchall()
            conn.close()

            return {r[0]: r[1] for r in rows}
        except Exception as e:
            logging.error(f"获取目标趋势失败: {e}")
            return {}
