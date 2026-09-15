# -*- coding: utf-8 -*-
"""
数据库模块 (database.py)
=========================
核心职责：
- StudyLogger: 会话/任务/睡眠/ATM 数据的 SQLite 存储层

已迁移的职责（请使用对应 Store 类）：
- 习惯系统  → server.models.habit_store.HabitStore
- 积分/奖励 → server.models.reward_store.RewardStore
- 目标挑战  → server.models.goal_store.GoalStore
- Schema 管理 → server.models.schema.ensure_schema
"""

import os
import json
import sqlite3
import logging
from datetime import datetime

from server.utils.utils import resource_path, get_db_path
from server.utils.config import DEFAULT_CONFIG

class StudyLogger:
    """
    会话/任务/睡眠/ATM 数据的 SQLite 数据库读写层。

    职责范围（精简后）
    ------------------
    StudyLogger 只负责以下核心数据的读写：

    - **专注会话**：log_session / get_all_sessions
    - **任务持久化**：upsert_task / update_task_status / get_all_active_tasks
    - **华为睡眠数据**：save_huawei_sleep_data / get_huawei_sleep_data /
      get_sleep_history / save_sleep_reflection
    - **aTimeLogger 数据**：save_atm_data / get_atm_data

    与各 Store 的分工
    -----------------
    以下职责已迁移到独立 Store 类，StudyLogger 通过代理方法保持向后兼容：

    - **习惯系统** → :class:`server.models.habit_store.HabitStore`
      （add_habit / toggle_checkin / get_today_checkins 等）
    - **积分与奖励** → :class:`server.models.reward_store.RewardStore`
      （get_balance / add_ledger_entry / buy_reward / get_backpack_items 等）
    - **目标挑战** → :class:`server.models.goal_store.GoalStore`
      （add_goal / get_goal_progress / auto_settle_goals 等）
    - **Schema 管理** → :func:`server.models.schema.ensure_schema`
      （SQLite 表结构创建与版本迁移）
    - **分类管理** → :class:`server.models.category_manager.CategoryManager`
      （get_category_id_by_name 等）

    使用示例
    --------
    ::

        logger = StudyLogger(config)
        logger.log_session(start_time, end_time, net_duration_seconds=3600)
        sessions = logger.get_all_sessions()
    """

    def __init__(self, config=None):
        self.config = config if config else DEFAULT_CONFIG
        self.db_type = "sqlite"
        self.log_path = get_db_path()
        db_dir = os.path.dirname(self.log_path)
        old_path = os.path.join(db_dir, "study_log.db")
        if os.path.exists(old_path):
            if not os.path.exists(self.log_path) or os.path.getsize(old_path) > os.path.getsize(self.log_path):
                try:
                    if os.path.exists(self.log_path):
                        os.rename(self.log_path, self.log_path + ".bak")
                    os.rename(old_path, self.log_path)
                    logging.info(f"已将数据库从 {old_path} 迁移至 {self.log_path}")
                except Exception as e:
                    logging.error(f"数据库迁移失败: {e}")
        from server.models.schema import ensure_schema
        ensure_schema(self.log_path)
        self._migrate_from_json()

    @property
    def api_client(self):
        from server.utils.api_client import APIClient
        return APIClient(self.config)

    def _get_connection(self):
        """获取启用外键约束的 SQLite 连接。"""
        conn = sqlite3.connect(self.log_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrate_from_json(self):
        """将旧版 study_log.json 数据迁移到 SQLite 数据库（一次性操作）。"""
        json_path = resource_path("study_log.json")
        if not os.path.exists(json_path):
            return
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                records = json.load(f)
            if records:
                conn = sqlite3.connect(self.log_path)
                cursor = conn.cursor()
                for r in records:
                    cursor.execute(
                        "INSERT INTO study_sessions "
                        "(start_time, end_time, net_duration_minutes, date, day_of_week, "
                        "pause_count, pause_reasons, session_summary) VALUES (?,?,?,?,?,?,?,?)",
                        (r.get("start_time"), r.get("end_time"), r.get("net_duration_minutes"),
                         r.get("date"), r.get("day_of_week"), r.get("pause_count"),
                         r.get("pause_reasons"), r.get("session_summary")))
                conn.commit()
                conn.close()
            os.rename(json_path, json_path + ".bak")
        except Exception as e:
            logging.error(f"数据迁移失败: {e}")

    # ======================== 会话记录 ========================

    def log_session(self, start_time, end_time, net_duration_seconds,
                    pause_count=0, pause_reasons="无", session_summary="", category_id=None):
        """记录一条专注会话到 study_sessions 表（本地优先，异步同步）。"""
        net_minutes = round(net_duration_seconds / 60, 2)
        date_str = start_time.strftime('%Y-%m-%d') if isinstance(start_time, datetime) else str(start_time)[:10]
        day_of_week = start_time.strftime('%A') if isinstance(start_time, datetime) else ""
        start_str = start_time.strftime('%Y-%m-%d %H:%M:%S') if isinstance(start_time, datetime) else str(start_time)
        end_str = end_time.strftime('%Y-%m-%d %H:%M:%S') if isinstance(end_time, datetime) else str(end_time)

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT INTO study_sessions (start_time, end_time, net_duration_minutes, date, "
                f"day_of_week, pause_count, pause_reasons, session_summary, category_id) "
                f"VALUES (?,?,?,?,?,?,?,?,?)",
                (start_str, end_str, net_minutes, date_str, day_of_week,
                 pause_count, pause_reasons, session_summary, category_id))
            local_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # 标记待同步
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.log_path, 'study_sessions', local_id, self.config)

            # 云端异步双写（保留兼容）
            if self.config.get("server_mode", False):
                def upload():
                    ok, res = self.api_client.post("/api/sessions", json={
                        "start_time": start_str,
                        "end_time": end_str,
                        "net_duration_minutes": net_minutes,
                        "date": date_str,
                        "day_of_week": day_of_week,
                        "pause_count": pause_count,
                        "pause_reasons": pause_reasons,
                        "session_summary": session_summary,
                        "category_id": category_id
                    })
                    if ok and isinstance(res, dict) and res.get("status") == "ok":
                        cloud_id = res.get("session_id")
                        if cloud_id and cloud_id != local_id:
                            try:
                                conn_up = self._get_connection()
                                cursor_up = conn_up.cursor()
                                cursor_up.execute("UPDATE study_sessions SET id = ? WHERE id = ?", (cloud_id, local_id))
                                conn_up.commit()
                                conn_up.close()
                            except Exception as db_e:
                                logging.error(f"同步云端 Session ID 失败: {db_e}")
                import threading
                threading.Thread(target=upload, daemon=True).start()
        except Exception as e:
            logging.error(f"记录会话失败: {e}")

    def get_all_sessions(self):
        """获取所有专注会话记录，按开始时间倒序排列（100% 只读本地 SQLite）。"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM study_sessions ORDER BY start_time DESC")
            rows = cursor.fetchall()
            conn.close()
            return rows
        except Exception as e:
            logging.error(f"获取会话列表失败: {e}")
            return []

    def get_today_group_summary(self, date_str: str) -> dict:
        """
        查询指定日期各分组的专注时长汇总（分钟数）（100% 只读本地 SQLite）。
        """
        summary = {"输入": 0, "输出": 0, "生活": 0, "未分类": 0}
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.group_name, SUM(s.net_duration_minutes)
                FROM study_sessions s
                LEFT JOIN categories c ON s.category_id = c.id
                WHERE s.date = ?
                GROUP BY c.group_name
                """,
                (date_str,),
            )
            rows = cursor.fetchall()
            conn.close()
            for row in rows:
                grp = row[0] if row[0] else "未分类"
                mins = int(row[1]) if row[1] else 0
                if grp in summary:
                    summary[grp] = mins
                else:
                    summary["未分类"] += mins
        except Exception as e:
            logging.warning(f"get_today_group_summary 查询失败: {e}")
        return summary

    # ======================== 时间书专用数据方法 ========================

    def get_sessions_by_date(self, date_str: str) -> list:
        """
        获取指定日期的所有专注会话，按 start_time 正序排列（时间书时间轴用）。

        返回 dict 列表，每条包含：
            id, start_time, end_time, net_duration_minutes, date,
            pause_count, pause_reasons, session_summary,
            category_id, category_name, category_color, group_name
        """
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.id, s.start_time, s.end_time, s.net_duration_minutes,
                       s.date, s.pause_count, s.pause_reasons, s.session_summary,
                       s.category_id,
                       c.name  AS category_name,
                       c.color AS category_color,
                       c.group_name AS group_name
                FROM study_sessions s
                LEFT JOIN categories c ON s.category_id = c.id
                WHERE s.date = ?
                ORDER BY s.start_time ASC
                """,
                (date_str,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logging.error(f"get_sessions_by_date 失败: {e}")
            return []

    def get_available_dates(self, limit: int = 90) -> list:
        """
        查询有 session 记录的日期列表，按日期倒序（时间书翻页用）。

        返回字符串列表，如 ['2026-05-26', '2026-05-25', ...]
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT date FROM study_sessions "
                "WHERE date IS NOT NULL ORDER BY date DESC LIMIT ?",
                (limit,),
            )
            rows = [row[0] for row in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logging.error(f"get_available_dates 失败: {e}")
            return []

    def update_session(self, session_id: int, fields: dict) -> bool:
        """
        更新指定 session 的字段（时间书编辑用）。

        Args:
            session_id: study_sessions 的 id
            fields: 允许更新的键值对，支持：
                start_time, end_time, net_duration_minutes,
                session_summary, category_id

        Returns:
            True 表示更新成功，False 表示失败
        """
        allowed = {"start_time", "end_time", "net_duration_minutes",
                   "session_summary", "category_id"}
        update_dict = {k: v for k, v in fields.items() if k in allowed}
        if not update_dict:
            return False
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in update_dict])
            values = list(update_dict.values()) + [session_id]
            cursor.execute(
                f"UPDATE study_sessions SET {set_clause} WHERE id = ?",
                values,
            )
            conn.commit()
            conn.close()
            logging.info(f"[TimeBook] 更新 session id={session_id}, fields={list(update_dict.keys())}")
            return True
        except Exception as e:
            logging.error(f"update_session 失败: {e}")
            return False

    def delete_session(self, session_id: int) -> bool:
        """
        硬删除指定 session（时间书删除用）。

        Returns:
            True 表示删除成功，False 表示失败
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM study_sessions WHERE id = ?", (session_id,))
            conn.commit()
            conn.close()
            logging.info(f"[TimeBook] 删除 session id={session_id}")
            return True
        except Exception as e:
            logging.error(f"delete_session 失败: {e}")
            return False

    def insert_session(self, fields: dict) -> int:
        """
        手动新增一条专注 session（时间书手动录入用）。

        Args:
            fields: 必须包含 start_time(str)、end_time(str)、
                    net_duration_minutes(float)，可选 session_summary、
                    category_id、pause_count、pause_reasons

        Returns:
            新记录的 id（int），失败返回 -1
        """
        try:
            from datetime import datetime as _dt
            start_time = fields.get("start_time", "")
            # 从 start_time 提取 date 和 day_of_week
            try:
                dt = _dt.fromisoformat(start_time)
                date_str = dt.strftime("%Y-%m-%d")
                day_of_week = dt.strftime("%A")
            except Exception:
                date_str = start_time[:10] if start_time else ""
                day_of_week = ""

            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO study_sessions
                    (start_time, end_time, net_duration_minutes, date, day_of_week,
                     pause_count, pause_reasons, session_summary, category_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    start_time,
                    fields.get("end_time", ""),
                    fields.get("net_duration_minutes", 0.0),
                    date_str,
                    day_of_week,
                    fields.get("pause_count", 0),
                    fields.get("pause_reasons", "无"),
                    fields.get("session_summary", ""),
                    fields.get("category_id"),
                ),
            )
            conn.commit()
            new_id = cursor.lastrowid
            conn.close()
            logging.info(f"[TimeBook] 新增 session id={new_id}, date={date_str}")
            return new_id
        except Exception as e:
            logging.error(f"insert_session 失败: {e}")
            return -1

    # ======================== 任务持久化 ========================

    def upsert_task(self, task_dict):
        """插入或更新一条任务记录（以 ticktick_id 为唯一键）（本地优先，异步同步）。"""
        try:
            task_id = task_dict.get("id", "")
            title = task_dict.get("title", "")
            priority = task_dict.get("priority", 0)
            status = task_dict.get("status", 0)
            category_id = task_dict.get("category_id")
            project_name = task_dict.get("project_name", "")
            due_date = task_dict.get("due_date", "")
            raw_json = json.dumps(task_dict, ensure_ascii=False)
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn = self._get_connection()
            cursor = conn.cursor()

            # 查询已有状态做防降级保护
            existing_status = None
            try:
                cursor.execute("SELECT status FROM tasks WHERE ticktick_id = ?", (task_id,))
                row = cursor.fetchone()
                if row:
                    # Row supports column index both in SQLite and MySQL
                    existing_status = row[0]
            except Exception as ex:
                logging.warning(f"查询已有任务状态失败: {ex}")

            # 若本地已完成，拒绝覆盖降级为活跃
            if existing_status == 2 and status == 0:
                status = 2
                if isinstance(task_dict, dict):
                    task_dict["status"] = 2
                    raw_json = json.dumps(task_dict, ensure_ascii=False)

            vals = (task_id, title, priority, status, category_id, project_name, due_date, raw_json, updated_at)
            cursor.execute(
                "INSERT INTO tasks (ticktick_id, title, priority, status, category_id, "
                "project_name, due_date, raw_json, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(ticktick_id) DO UPDATE SET title=excluded.title, "
                "priority=excluded.priority, status=excluded.status, "
                "category_id=excluded.category_id, project_name=excluded.project_name, "
                "due_date=excluded.due_date, raw_json=excluded.raw_json, updated_at=excluded.updated_at",
                vals)
            conn.commit()
            conn.close()

            # 标记待同步
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.log_path, 'tasks', where_col='ticktick_id',
                            where_val=task_id, config=self.config)

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload():
                    self.api_client.post("/api/tasks", json={"task": task_dict})
                import threading
                threading.Thread(target=upload, daemon=True).start()

            return True
        except Exception as e:
            logging.error(f"upsert_task 失败: {e}")
            return False

    def update_task_status(self, task_id, status):
        """更新指定任务的状态（0=活跃, 2=已完成, 4=已忽略）（本地优先，异步同步）。"""
        try:
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET status=?, updated_at=? WHERE ticktick_id=?",
                           (status, updated_at, task_id))
            conn.commit()
            conn.close()

            # 标记待同步
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.log_path, 'tasks', where_col='ticktick_id',
                            where_val=task_id, config=self.config)

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload():
                    self.api_client.put(f"/api/tasks/{task_id}/status", json={"status": status})
                import threading
                threading.Thread(target=upload, daemon=True).start()

            return True
        except Exception as e:
            logging.error(f"update_task_status 失败: {e}")
            return False

    def get_all_active_tasks(self):
        """获取所有活跃任务（status=0），按 priority 降序、updated_at 降序排列（100% 只读本地 SQLite）。"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE status = 0 ORDER BY priority DESC, updated_at DESC")
            rows = []
            for r in cursor.fetchall():
                d = dict(r)
                if d.get('ticktick_id'):
                    d['id'] = d['ticktick_id']
                rows.append(d)
            conn.close()
            return rows
        except Exception as e:
            logging.error(f"get_all_active_tasks 失败: {e}")
            return []

    # ======================== 华为睡眠数据 ========================

    def save_huawei_sleep_data(self, date_str, data):
        """保存或更新指定日期的华为睡眠数据（本地优先，异步同步）。"""
        try:
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            fields = [
                'sleep_score', 'total_sleep_min', 'deep_sleep_min', 'light_sleep_min',
                'rem_sleep_min', 'awake_count', 'sleep_start', 'sleep_end',
                'deep_sleep_ratio', 'light_sleep_ratio', 'rem_sleep_ratio',
                'sleep_continuity', 'breathing_score', 'sleep_cycles',
                'awake_min', 'fall_asleep_min', 'wake_up_min',
                'atm_sleep_start', 'atm_sleep_end', 'analysis_report', 'morning_diary', 'evening_diary',
                'report_status'
            ]
            values = []
            for f in fields:
                val = data.get(f)
                if f == 'morning_diary' and val is None:
                    val = data.get('sleep_reflection')
                values.append(val)
            conn = self._get_connection()
            cursor = conn.cursor()
            placeholders = ', '.join(['?'] * len(fields))
            cursor.execute(
                f"INSERT OR REPLACE INTO huawei_sleep_data "
                f"(date, {', '.join(fields)}, updated_at) VALUES (?, {placeholders}, ?)",
                [date_str] + values + [updated_at])
            conn.commit()
            conn.close()

            # 标记待同步
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.log_path, 'huawei_sleep_data', where_col='date',
                            where_val=date_str, config=self.config)

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload():
                    self.api_client.post("/api/sleep/data", json={"date": date_str, "data": data})
                import threading
                threading.Thread(target=upload, daemon=True).start()
        except Exception as e:
            logging.error(f"save_huawei_sleep_data 失败: {e}")

    def get_huawei_sleep_data(self, date_str):
        """获取指定日期的华为睡眠数据，无记录时返回 None（100% 只读本地 SQLite）。"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM huawei_sleep_data WHERE date=?", (date_str,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logging.error(f"get_huawei_sleep_data 失败: {e}")
            return None

    def get_sleep_history(self, days=14):
        """获取最近 N 天的睡眠历史记录（升序），用于趋势图表展示（100% 只读本地 SQLite）。"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM huawei_sleep_data ORDER BY date DESC LIMIT ?", (days,))
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return list(reversed(rows))
        except Exception as e:
            logging.error(f"get_sleep_history 失败: {e}")
            return []

    def save_morning_diary(self, date_str, diary_text):
        """保存或更新指定日期的晨间日记文字（本地优先，异步同步）。"""
        try:
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO huawei_sleep_data (date, morning_diary, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(date) DO UPDATE SET "
                "morning_diary=excluded.morning_diary, updated_at=excluded.updated_at",
                (date_str, diary_text, updated_at))
            conn.commit()
            conn.close()

            # 标记待同步
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.log_path, 'huawei_sleep_data', where_col='date',
                            where_val=date_str, config=self.config)

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload():
                    self.api_client.post("/morning_diary", json={"date": date_str, "text": diary_text})
                import threading
                threading.Thread(target=upload, daemon=True).start()
        except Exception as e:
            logging.error(f"save_morning_diary 失败: {e}")

    def save_evening_diary(self, date_str, diary_text):
        """保存或更新指定日期的晚间复盘文字（本地优先，异步同步）。"""
        try:
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO huawei_sleep_data (date, evening_diary, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(date) DO UPDATE SET "
                "evening_diary=excluded.evening_diary, updated_at=excluded.updated_at",
                (date_str, diary_text, updated_at))
            conn.commit()
            conn.close()

            # 标记待同步
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.log_path, 'huawei_sleep_data', where_col='date',
                            where_val=date_str, config=self.config)

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload():
                    self.api_client.post("/evening_diary", json={"date": date_str, "text": diary_text})
                import threading
                threading.Thread(target=upload, daemon=True).start()
        except Exception as e:
            logging.error(f"save_evening_diary 失败: {e}")

    # ======================== aTimeLogger 数据 ========================

    def save_atm_data(self, date_str, data):
        """保存或更新指定日期的 aTimeLogger 活动数据（本地优先，异步同步）。"""
        try:
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            activities = (data.get('activities', []) if isinstance(data, dict)
                          else (data if isinstance(data, list) else []))
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO atm_summary (date, updated_at) VALUES (?,?)",
                           (date_str, updated_at))
            cursor.execute("DELETE FROM atm_activities WHERE date=?", (date_str,))
            for act in activities:
                act_type = act.get('activity_type') or act.get('type') or ''
                st = act.get('start_time') or act.get('start') or ''
                if isinstance(st, datetime):
                    st = st.isoformat()
                et = act.get('end_time') or act.get('finish_time') or act.get('finish') or ''
                if isinstance(et, datetime):
                    et = et.isoformat()
                dur = act.get('duration_minutes') or (act.get('duration', 0) // 60) or 0
                comment = act.get('comment') or ''

                cursor.execute(
                    f"INSERT INTO atm_activities "
                    f"(date, activity_type, start_time, end_time, duration_minutes, comment) "
                    f"VALUES (?,?,?,?,?,?)",
                    (date_str, act_type, st, et, dur, comment))
            conn.commit()
            conn.close()

            # 标记待同步
            from server.utils.utils import mark_pending_sync
            mark_pending_sync(self.log_path, 'atm_summary', where_col='date',
                            where_val=date_str, config=self.config)

            # 云端异步双写
            if self.config.get("server_mode", False):
                def upload():
                    self.api_client.post("/api/atm/data", json={"date": date_str, "data": data})
                import threading
                threading.Thread(target=upload, daemon=True).start()
        except Exception as e:
            logging.error(f"save_atm_data 失败: {e}")

    def get_atm_data(self, date_str):
        """获取指定日期的 aTimeLogger 活动数据，无记录时返回 None（100% 只读本地 SQLite）。"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM atm_summary WHERE date=?", (date_str,))
            summary = cursor.fetchone()
            if not summary:
                conn.close()
                return None
            cursor.execute(
                "SELECT * FROM atm_activities WHERE date=? ORDER BY start_time", (date_str,))
            raw_activities = [dict(r) for r in cursor.fetchall()]
            conn.close()

            # 向下映射兼容，提供 type, start, finish 等属性以供分析器与计算引擎直接读取
            activities = []
            for act in raw_activities:
                activities.append({
                    "type": act.get("activity_type") or "",
                    "start": act.get("start_time") or "",
                    "finish": act.get("end_time") or "",
                    "duration": (act.get("duration_minutes") or 0) * 60,
                    "comment": act.get("comment") or ""
                })
            return {"date": date_str, "activities": activities}
        except Exception as e:
            logging.error(f"get_atm_data 失败: {e}")
            return None

    # ======================== 代理方法（兼容旧调用方） ========================
    # 委托给对应 Store 类，保持对 ticktick_sync.py、daily_checklist.py 等的向后兼容。

    def _get_reward_store(self):
        if not hasattr(self, '_reward_store') or self._reward_store is None:
            from server.models.reward_store import RewardStore
            self._reward_store = RewardStore(self.log_path, self.config)
        return self._reward_store

    def get_item_reward(self, item_type: str, item_id: str, default: float = 0.1) -> dict:
        return self._get_reward_store().get_item_reward(item_type, item_id, default)

    def set_item_reward(self, item_type: str, item_id: str, coins: float, penalty: float = None):
        return self._get_reward_store().set_item_reward(item_type, item_id, coins, penalty)

    def add_external_reward(self, ext_id: str, item_type: str, item_name: str,
                            coins: float, status: int = 0):
        return self._get_reward_store().add_external_reward(ext_id, item_type, item_name, coins, status)

    def add_ledger_entry(self, amount, source_type, source_id=None, description='', created_at=None):
        return self._get_reward_store().add_ledger_entry(amount, source_type, source_id, description, created_at)

    def get_balance(self):
        return self._get_reward_store().get_balance()

    def get_unclaimed_rewards(self) -> list:
        return self._get_reward_store().get_unclaimed_rewards()

    def claim_rewards(self, ext_ids: list) -> float:
        return self._get_reward_store().claim_rewards(ext_ids)

    def get_ledger_history(self, limit=30):
        return self._get_reward_store().get_ledger_history(limit)

    def get_category_id_by_name(self, name: str):
        """通过分类名称查询分类 ID。→ CategoryManager"""
        try:
            from server.models.category_manager import CategoryManager
            return CategoryManager(self.log_path, self.config).get_id_by_name(name)
        except Exception as e:
            logging.error(f"get_category_id_by_name 失败: {e}")
            return None

    def auto_settle_goals(self):
        """自动结算目标挑战。→ GoalStore"""
        try:
            from server.models.goal_store import GoalStore
            GoalStore(self.log_path, self.config).auto_settle_goals()
        except Exception as e:
            logging.error(f"auto_settle_goals 代理失败: {e}")

    # ---- GoalStore 代理方法 ----

    def _get_goal_store(self):
        if not hasattr(self, '_goal_store') or self._goal_store is None:
            from server.models.goal_store import GoalStore
            self._goal_store = GoalStore(self.log_path, self.config)
        return self._goal_store

    def get_all_goals(self) -> list:
        """获取所有激活目标。→ GoalStore"""
        return self._get_goal_store().get_all_goals()

    def add_goal(self, title, category_id, metric, target_value, period,
                 reward_coins, reward_id=None, operator='>=', penalty_coins=None) -> bool:
        """添加新目标。→ GoalStore"""
        return self._get_goal_store().add_goal(
            title, category_id, metric, target_value, period,
            reward_coins, reward_id, operator, penalty_coins)

    def remove_goal(self, goal_id) -> bool:
        """软删除目标。→ GoalStore"""
        return self._get_goal_store().remove_goal(goal_id)

    def update_goal(self, goal_id, **kwargs) -> bool:
        """更新目标字段。→ GoalStore"""
        return self._get_goal_store().update_goal(goal_id, **kwargs)

    def get_goal_progress(self, goal_dict, active_session_info=None):
        """计算目标当前进度。→ GoalStore"""
        return self._get_goal_store().get_goal_progress(goal_dict, active_session_info)

    def get_goal_daily_stats(self, goal_dict, start_str, end_str) -> dict:
        """获取目标每日统计趋势。→ GoalStore"""
        return self._get_goal_store().get_goal_daily_stats(goal_dict, start_str, end_str)

    # ---- RewardStore 奖励商品代理方法 ----

    def get_all_rewards(self) -> list:
        """获取所有激活奖励商品。→ RewardStore"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rewards WHERE is_active = 1 ORDER BY id ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logging.error(f"get_all_rewards 失败: {e}")
            return []

    def add_reward(self, title, icon='🎁', price=10, description='',
                   unlock_task_id=None, unlock_task_title=None) -> bool:
        """新增奖励商品。→ RewardStore"""
        return self._get_reward_store().add_reward(
            title, icon, price, description, unlock_task_id, unlock_task_title)

    def remove_reward(self, reward_id) -> bool:
        """软删除奖励商品。→ RewardStore"""
        return self._get_reward_store().remove_reward(reward_id)

    def update_reward(self, reward_id, title, icon='🎁', price=10, description='',
                      unlock_task_id=None, unlock_task_title=None) -> bool:
        """修改奖励商品配置。→ RewardStore"""
        return self._get_reward_store().update_reward(
            reward_id, title, icon, price, description, unlock_task_id, unlock_task_title)

    def buy_reward(self, reward_id):
        """购买奖励。→ RewardStore"""
        return self._get_reward_store().buy_reward(reward_id)

    def get_available_unlocks(self, unlock_task_id: str, reward_id: int) -> int:
        """计算解锁条件剩余兑换额度。→ RewardStore"""
        return self._get_reward_store().get_available_unlocks(unlock_task_id, reward_id)

    def get_backpack_items(self) -> list:
        """获取背包物品列表。→ RewardStore"""
        return self._get_reward_store().get_backpack_items()

    def mark_backpack_item_used(self, ledger_id: int) -> bool:
        """将背包物品标记为已使用。→ RewardStore"""
        return self._get_reward_store().mark_backpack_item_used(ledger_id)

    def reset_coins(self) -> bool:
        """重置金币（清空流水和待领取奖励）。→ RewardStore"""
        return self._get_reward_store().reset_coins()
