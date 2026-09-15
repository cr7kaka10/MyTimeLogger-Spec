import sqlite3
import json
from datetime import datetime


_PROVIDER_TRANSPORT_FIELDS = {"request_id", "trace_id", "fetched_at", "pulled_at", "synced_at", "transport_diagnostics"}


def _canonical_provider_snapshot(value):
    """保留业务事实，剔除每次拉取都会变化的传输元数据。"""
    if isinstance(value, dict):
        return {
            key: _canonical_provider_snapshot(item)
            for key, item in value.items()
            if key not in _PROVIDER_TRANSPORT_FIELDS
        }
    if isinstance(value, list):
        return [_canonical_provider_snapshot(item) for item in value]
    return value

try:
    from .atm_versioning import save_versioned_atm_data
    from .time_utils import normalize_task_record_for_db
    from .store import resolve_server_db_path
    from .domain.reward_config_service import RewardConfigService
except (ImportError, ValueError):
    from atm_versioning import save_versioned_atm_data
    from time_utils import normalize_task_record_for_db
    from store import resolve_server_db_path
    from domain.reward_config_service import RewardConfigService

class ServerDBWrapper:
    def __init__(self, db_path=None):
        self.log_path = resolve_server_db_path(db_path)
        self.db_type = "sqlite"
        # 分类名称→ID 缓存（启动时及变更时重载，避免每次 upsert 都查库）
        self._category_cache: dict[int, dict[str, int]] = {}

    requires_report_user_id = True

    def _get_connection(self):
        """兼容睡眠报告生成器的 SQLite 连接接口。"""
        conn = sqlite3.connect(self.log_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TEMP VIEW IF NOT EXISTS huawei_sleep_data AS
            SELECT
                id, user_id, date, sleep_score, total_sleep_min, deep_sleep_min,
                light_sleep_min, rem_sleep_min, awake_count, sleep_start, sleep_end,
                deep_sleep_ratio, light_sleep_ratio, rem_sleep_ratio, sleep_continuity,
                breathing_score, sleep_cycles, awake_min, fall_asleep_min, wake_up_min,
                atm_sleep_start, atm_sleep_end, calc_trace, analysis_report,
                analysis_html, official_advice, morning_diary, evening_diary,
                report_status, source, synced_at, sync_status, sync_error,
                updated_at, pushed_at
            FROM server_huawei_sleep_data
            """
        )
        return conn

    def reload_category_cache(self):
        """全量同步并预热分类内存 Map（self._category_cache），从 server_categories 表中加载数据"""
        new_cache = {}
        try:
            with sqlite3.connect(self.log_path, timeout=30.0) as conn:
                conn.row_factory = sqlite3.Row
                # 检查表是否存在以防止初次运行报错
                table_exists = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='server_categories'"
                ).fetchone()[0]
                if table_exists:
                    rows = conn.execute("SELECT id, name, user_id FROM server_categories").fetchall()
                    for row in rows:
                        uid = row['user_id']
                        if uid not in new_cache:
                            new_cache[uid] = {}
                        new_cache[uid][row['name']] = row['id']
            self._category_cache = new_cache
        except Exception:
            pass

    def _get_category_id(self, user_id: int, project_name: str, tags, conn=None) -> int | None:
        """通过分类名称 (优先匹配 tags，其次匹配 project_name) 反查 server_categories 表获取 category_id，带内存缓存"""
        # 初始化或兜底加载该用户的缓存
        if user_id not in self._category_cache:
            self.reload_category_cache()
            if user_id not in self._category_cache:
                self._category_cache[user_id] = {}

        # 1. 优先尝试从 tags 中匹配分类名称
        if tags:
            if isinstance(tags, str):
                tags_list = [t.strip() for t in tags.split(",") if t.strip()]
            else:
                tags_list = tags
            for tag in tags_list:
                cat_id = self._category_cache[user_id].get(tag)
                if cat_id is not None:
                    return cat_id

        # 2. 如果 tags 没匹配到，再尝试从 project_name 中匹配
        if project_name:
            return self._category_cache[user_id].get(project_name)
        return None


    def allocate_server_version(self, user_id: int, conn: sqlite3.Connection | None = None) -> int:
        """为用户分配严格递增的服务端同步版本号。"""
        owns_conn = conn is None
        if conn is None:
            conn = sqlite3.connect(self.log_path, timeout=30.0)
        try:
            now = datetime.now().isoformat(' ', 'seconds')
            conn.execute(
                """
                INSERT INTO server_version_counters (user_id, current_version, updated_at)
                VALUES (?, 0, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, now),
            )
            conn.execute(
                """
                UPDATE server_version_counters
                SET current_version = current_version + 1, updated_at = ?
                WHERE user_id = ?
                """,
                (now, user_id),
            )
            row = conn.execute(
                "SELECT current_version FROM server_version_counters WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if owns_conn:
                conn.commit()
            return int(row[0])
        finally:
            if owns_conn:
                conn.close()

    def write_server_change(
        self,
        user_id: int,
        entity_type: str,
        entity_id: str,
        operation: str,
        changed_fields: dict | None = None,
        *,
        change_id: str | None = None,
        device_id: str | None = None,
        table_name: str | None = None,
        status: str = "applied",
        error: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        """写入服务端版本化变更日志，并返回本次 server_version。"""
        owns_conn = conn is None
        if conn is None:
            conn = sqlite3.connect(self.log_path, timeout=30.0)
        try:
            now = datetime.now().isoformat(' ', 'seconds')
            server_version = self.allocate_server_version(user_id, conn)
            effective_change_id = change_id or f"server:{user_id}:{server_version}"
            effective_table_name = table_name or f"server_{entity_type}s"
            fields_json = json.dumps(changed_fields or {}, ensure_ascii=False, sort_keys=True)
            conn.execute(
                """
                INSERT INTO server_change_log (
                    user_id, server_version, change_id, device_id, table_name, record_id,
                    entity_type, entity_id, operation, changed_fields_json,
                    status, error, changed_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    server_version,
                    effective_change_id,
                    device_id,
                    effective_table_name,
                    entity_id,
                    entity_type,
                    entity_id,
                    operation,
                    fields_json,
                    status,
                    error,
                    now,
                    now,
                ),
            )
            if owns_conn:
                conn.commit()
            return server_version
        finally:
            if owns_conn:
                conn.close()


    def upsert_task(self, user_id: int, task: dict) -> bool:
        with sqlite3.connect(self.log_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            now = datetime.now().isoformat(' ', 'microseconds')
            provider_snapshot = dict(task)
            task = normalize_task_record_for_db(task)
            # 滴答清单任务 ID 直接作为主键
            task_id = task.get('id') or task.get('ticktick_id')
            tags = task.get('tags') or []
            # 将 tags 列表拼接为以逗号分隔的纯文本字符串 (例：["输入"] -> "输入")
            if isinstance(tags, list):
                tags_str = ",".join(tags)
            else:
                tags_str = str(tags)
            # 通过 tags 优先/project_name 反查分类表，填充 category_id
            category_id = self._get_category_id(user_id, task.get('project_name', ''), tags_str, conn)
            # 将完整的滴答清单原始数据序列化为 JSON 存入 raw_json
            raw_json = json.dumps(
                _canonical_provider_snapshot(provider_snapshot),
                ensure_ascii=False,
                default=str,
                sort_keys=True,
                separators=(",", ":"),
            )
            source_etag = task.get('etag') or task.get('source_etag') or ''
            source_modified_time = task.get('modifiedTime') or task.get('source_modified_time') or ''
            next_values = {
                "title": task['title'],
                "priority": task['priority'],
                "status": task['status'],
                "category_id": category_id,
                "due_date": task.get('due_date', ''),
                "tags": tags_str,
                "raw_json": raw_json,
                "source_etag": source_etag,
                "source_modified_time": source_modified_time,
                "deleted_at": None,
            }
            existing = conn.execute(
                "SELECT title, priority, status, category_id, due_date, tags, raw_json, source_etag, source_modified_time, deleted_at FROM server_tasks WHERE user_id = ? AND id = ?",
                (user_id, task_id),
            ).fetchone()
            if existing:
                unchanged = True
                for key, value in next_values.items():
                    if existing[key] != value:
                        unchanged = False
                        break
                if unchanged:
                    RewardConfigService().ensure_item(conn, user_id, "task", str(task_id))
                    return False

            conn.execute('''
                INSERT INTO server_tasks (id, user_id, title, priority, status,
                    category_id, due_date, tags, raw_json, source_etag, source_modified_time, deleted_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, id) DO UPDATE SET
                    title=excluded.title, priority=excluded.priority, status=excluded.status,
                    category_id=excluded.category_id,
                    due_date=excluded.due_date, tags=excluded.tags,
                    raw_json=excluded.raw_json,
                    source_etag=excluded.source_etag,
                    source_modified_time=excluded.source_modified_time,
                    deleted_at=excluded.deleted_at,
                    updated_at=excluded.updated_at
            ''', (
                task_id, user_id, task['title'], task['priority'], task['status'],
                category_id, task.get('due_date', ''), tags_str,
                raw_json, source_etag, source_modified_time, None, now
            ))
            RewardConfigService().ensure_item(conn, user_id, "task", str(task_id))
            self.write_server_change(
                user_id,
                "task",
                str(task_id),
                "upsert",
                next_values,
                change_id=f"provider:ticktick:task:{task_id}:{now}",
                device_id="ticktick",
                table_name="server_tasks",
                conn=conn,
            )
            conn.commit()
            return True

    def get_provider_fingerprints(self, user_id: int, table_name: str) -> dict[str, dict]:
        """Read local TickTick fingerprints for fast provider delta classification."""
        allowed = {"server_tasks", "server_habits", "server_habit_checkins"}
        if table_name not in allowed:
            raise ValueError(f"Unsupported provider fingerprint table: {table_name}")

        with sqlite3.connect(self.log_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            result: dict[str, dict] = {}
            if table_name == "server_tasks":
                rows = conn.execute(
                    "SELECT id, source_etag, source_modified_time, status, deleted_at FROM server_tasks WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
                for row in rows:
                    result[str(row["id"])] = {
                        "id": row["id"],
                        "source_etag": row["source_etag"],
                        "source_modified_time": row["source_modified_time"],
                        "status": row["status"],
                        "deleted_at": row["deleted_at"],
                    }
                return result

            if table_name == "server_habits":
                rows = conn.execute(
                    "SELECT id, source_etag, source_modified_time, is_active FROM server_habits WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
                for row in rows:
                    result[str(row["id"])] = {
                        "id": row["id"],
                        "source_etag": row["source_etag"],
                        "source_modified_time": row["source_modified_time"],
                        "status": row["is_active"],
                    }
                return result

            rows = conn.execute(
                "SELECT id, habit_id, checkin_date, source_modified_time, status FROM server_habit_checkins WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            for row in rows:
                key = f"{row['habit_id']}:{row['checkin_date']}"
                result[key] = {
                    "id": row["id"],
                    "habit_id": row["habit_id"],
                    "checkin_date": row["checkin_date"],
                    "source_modified_time": row["source_modified_time"],
                    "status": row["status"],
                }
            return result


    def get_item_reward(self, user_id: int, item_type: str, item_id: str) -> dict:
        with sqlite3.connect(self.log_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            return RewardConfigService.require(conn, user_id, item_type, item_id)

    def save_atm_data(self, user_id, date_str, data):
        """将 aTimeLogger 活动写入指定账号的服务端表。"""
        activities = data.get('activities', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with sqlite3.connect(self.log_path, timeout=30.0) as conn:
            save_versioned_atm_data(conn, self.write_server_change, user_id, date_str, activities, updated_at)
        return True

    def get_atm_data(self, user_id, date_str):
        with sqlite3.connect(self.log_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            summary = conn.execute(
                "SELECT * FROM server_atm_summary WHERE user_id=? AND date=?",
                (user_id, date_str),
            ).fetchone()
            if not summary:
                return None
            rows = conn.execute(
                "SELECT * FROM server_atm_activities WHERE user_id=? AND date=? ORDER BY start_time",
                (user_id, date_str),
            ).fetchall()
            activities = []
            for row in rows:
                item = dict(row)
                item['type'] = item.get('activity_type') or ''
                item['start'] = item.get('start_time') or ''
                item['finish'] = item.get('end_time') or ''
                item['duration'] = (item.get('duration_minutes') or 0) * 60
                activities.append(item)
            return {'date': date_str, 'activities': activities, 'updated_at': dict(summary).get('updated_at', '')}

    def get_huawei_sleep_data(self, user_id, date_str):
        with sqlite3.connect(self.log_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM server_huawei_sleep_data WHERE user_id=? AND date=?",
                (user_id, date_str),
            ).fetchone()
            return dict(row) if row else None

    def save_huawei_sleep_data(self, user_id, date_str, data):
        fields = [
            'sleep_score', 'total_sleep_min', 'deep_sleep_min', 'light_sleep_min',
            'rem_sleep_min', 'awake_count', 'sleep_start', 'sleep_end',
            'deep_sleep_ratio', 'light_sleep_ratio', 'rem_sleep_ratio',
              'sleep_continuity', 'breathing_score', 'sleep_cycles',
              'awake_min', 'fall_asleep_min', 'wake_up_min',
              'atm_sleep_start', 'atm_sleep_end', 'calc_trace', 'analysis_report', 'analysis_html', 'official_advice',
              'morning_diary', 'evening_diary',
              'report_status', 'full_report_state', 'tracked_duration_seconds',
              'source', 'synced_at', 'sync_status', 'sync_error',
          ]
        values = [user_id, date_str]
        for field in fields:
            value = data.get(field)
            if field == 'morning_diary' and value is None:
                value = data.get('sleep_reflection')
            if field == 'calc_trace' and value is not None and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False, default=str)
            values.append(value)
        values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        with sqlite3.connect(self.log_path, timeout=30.0) as conn:
            existing = conn.execute(
                "SELECT id FROM server_huawei_sleep_data WHERE user_id=? AND date=?",
                (user_id, date_str),
            ).fetchone()
            if existing:
                update_fields = [field for index, field in enumerate(fields) if values[index + 2] is not None]
                assignments = [f"{field}=?" for field in update_fields] + ["updated_at=?"]
                update_values = [values[fields.index(field) + 2] for field in update_fields] + [values[-1], user_id, date_str]
                conn.execute(
                    f"UPDATE server_huawei_sleep_data SET {', '.join(assignments)} WHERE user_id=? AND date=?",
                    tuple(update_values),
                )
                record_id = existing[0]
            else:
                placeholders = ", ".join(["?"] * (len(fields) + 3))
                columns = "user_id, date, " + ", ".join(fields) + ", updated_at"
                cursor = conn.execute(
                    f"INSERT INTO server_huawei_sleep_data ({columns}) VALUES ({placeholders})",
                    tuple(values),
                )
                record_id = cursor.lastrowid
            self.write_server_change(
                user_id,
                "huawei_sleep_data",
                str(record_id),
                "upsert",
                {"date": date_str},
                table_name="huawei_sleep_data",
                conn=conn,
            )
            conn.commit()
        return True
