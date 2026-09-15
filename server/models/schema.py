# -*- coding: utf-8 -*-
"""
数据库 Schema 管理模块 (schema.py)
====================================
统一管理 SQLite 数据库的表结构创建与版本迁移。

设计原则：
- 使用 PRAGMA user_version 追踪 schema 版本号
- 按序执行缺失的迁移，保证幂等性（多次调用结果相同）
- 与 database.py 中的 _initialize_db() / _migrate_habits_table() 逻辑完全对应

版本历史：
  v0 → v1：初始建表（study_sessions, tasks, habits, atm_summary,
            atm_activities, huawei_sleep_data, habit_checkins）
  v1 → v2：huawei_sleep_data 补充字段
            （sleep_reflection, light_sleep_ratio, rem_sleep_ratio,
              atm_sleep_start, atm_sleep_end）
  v2 → v3：habits 补充字段 + habit_checkins.status +
            reward_ledger / rewards / reward_config / external_rewards /
            goals 表创建及字段迁移
"""

import sqlite3
import logging
from datetime import datetime, timedelta

# 当前最新 schema 版本号
SCHEMA_VERSION = 9


def ensure_schema(db_path: str) -> None:
    """
    确保数据库 schema 是最新版本。

    使用 PRAGMA user_version 追踪版本，按序执行缺失的迁移。
    本函数是幂等的：多次调用结果相同，不会重复执行已完成的迁移。

    参数：
        db_path (str): SQLite 数据库文件的绝对路径。
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()

        # 读取当前版本
        cursor.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]

        # 按序执行缺失的迁移
        if current_version < 1:
            _migrate_v0_to_v1(cursor)
        if current_version < 2:
            _migrate_v1_to_v2(cursor)
        if current_version < 3:
            _migrate_v2_to_v3(cursor)
        if current_version < 4:
            _migrate_v3_to_v4(cursor)
        if current_version < 5:
            _migrate_v4_to_v5(cursor)
        if current_version < 6:
            _migrate_v5_to_v6(cursor)
        if current_version < 7:
            _migrate_v6_to_v7(cursor)
        if current_version < 8:
            _migrate_v7_to_v8(cursor)
        if current_version < 9:
            _migrate_v8_to_v9(cursor)

        # 更新版本号（仅在有迁移执行时才有意义，但无论如何都设置为最新）
        if current_version < SCHEMA_VERSION:
            cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()
            logging.info(f"数据库 schema 已从 v{current_version} 升级至 v{SCHEMA_VERSION}: {db_path}")
        else:
            logging.debug(f"数据库 schema 已是最新版本 v{SCHEMA_VERSION}，无需迁移。")

        # 清理已废弃的系统冗余配置脏数据
        try:
            cursor.execute("DELETE FROM system_config WHERE key IN ('mysql_config', 'server_sleep_sync')")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        conn.close()
    except Exception as e:
        logging.error(f"ensure_schema 执行失败: {e}")


# ============================================================
# 内部迁移函数（每个函数只负责一个版本区间的变更）
# ============================================================

def _migrate_v0_to_v1(cursor: sqlite3.Cursor) -> None:
    """
    v0 → v1：初始建表。

    创建以下表（均使用 CREATE TABLE IF NOT EXISTS，保证幂等）：
    - study_sessions：专注会话记录
    - tasks：任务持久化缓存
    - habits：习惯定义
    - atm_summary：aTimeLogger 日期汇总
    - atm_activities：aTimeLogger 活动明细
    - huawei_sleep_data：华为睡眠数据
    - habit_checkins：习惯打卡记录
    """
    logging.info("执行 schema 迁移 v0 → v1：初始建表")

    # 1. 专注会话表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            net_duration_minutes REAL NOT NULL,
            date TEXT NOT NULL,
            day_of_week TEXT,
            pause_count INTEGER DEFAULT 0,
            pause_reasons TEXT,
            session_summary TEXT,
            category_id INTEGER DEFAULT NULL
        )
    ''')

    # 2. 任务持久化缓存表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticktick_id TEXT UNIQUE,
            title TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            status INTEGER DEFAULT 0,
            category_id INTEGER DEFAULT NULL,
            project_name TEXT,
            due_date TEXT,
            raw_json TEXT,
            updated_at TIMESTAMP
        )
    ''')

    # 3. 习惯定义表（含完整字段，避免 v2→v3 迁移时重复 ALTER）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT '✅',
            color TEXT NOT NULL DEFAULT '#A3BE8C',
            frequency TEXT NOT NULL DEFAULT 'daily',
            category_id INTEGER DEFAULT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 4. aTimeLogger 日期汇总表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS atm_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            updated_at TIMESTAMP
        )
    ''')

    # 5. aTimeLogger 活动明细表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS atm_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            duration_minutes INTEGER NOT NULL,
            comment TEXT
        )
    ''')

    # 6. 华为睡眠数据表（基础字段，v1→v2 会补充额外字段）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS huawei_sleep_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            sleep_score INTEGER,
            total_sleep_min INTEGER,
            deep_sleep_min INTEGER,
            light_sleep_min INTEGER,
            rem_sleep_min INTEGER,
            awake_count INTEGER,
            sleep_start TEXT,
            sleep_end TEXT,
            deep_sleep_ratio INTEGER,
            sleep_continuity INTEGER,
            breathing_score INTEGER,
            sleep_cycles FLOAT,
            awake_min INTEGER,
            fall_asleep_min INTEGER,
            wake_up_min INTEGER,
            report_status INTEGER DEFAULT 0,
            updated_at TIMESTAMP
        )
    ''')

    # 7. 习惯打卡记录表
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

    # 8. 常用查询索引（幂等，IF NOT EXISTS 保证多次执行安全）
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_study_sessions_date ON study_sessions(date)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_huawei_sleep_date ON huawei_sleep_data(date)"
    )

    cursor.connection.commit()


def _migrate_v1_to_v2(cursor: sqlite3.Cursor) -> None:
    """
    v1 → v2：huawei_sleep_data 表补充字段。

    新增字段：
    - sleep_reflection：睡眠自我评价
    - light_sleep_ratio：浅睡比例
    - rem_sleep_ratio：REM 比例
    - atm_sleep_start：aTimeLogger 记录的入睡时间
    - atm_sleep_end：aTimeLogger 记录的起床时间
    - analysis_report：AI 分析报告
    """
    logging.info("执行 schema 迁移 v1 → v2：huawei_sleep_data 补充字段")

    cursor.execute("PRAGMA table_info(huawei_sleep_data)")
    existing_cols = {c[1] for c in cursor.fetchall()}

    additions = [
        ("sleep_reflection", "TEXT"),
        ("light_sleep_ratio", "INTEGER"),
        ("rem_sleep_ratio", "INTEGER"),
        ("atm_sleep_start", "TEXT"),
        ("atm_sleep_end", "TEXT"),
        ("analysis_report", "TEXT"),
    ]
    for col_name, col_type in additions:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE huawei_sleep_data ADD COLUMN {col_name} {col_type}")

    cursor.connection.commit()


def _migrate_v2_to_v3(cursor: sqlite3.Cursor) -> None:
    """
    v2 → v3：习惯系统、积分系统、目标系统完整迁移。

    包含：
    1. habits 表补充字段（difficulty 等）
    2. habit_checkins 表补充 status 字段
    3. 新建 reward_ledger（积分流水）表
    4. 新建 rewards（奖励商品）表及补充字段
    5. 新建 reward_config（自定义奖励配置）表及补充字段
    6. 新建 external_rewards（外部系统静默打卡奖励）表
    7. 新建 goals（目标挑战）表及补充字段
    8. 修正历史数据中的 UTC 时间偏差（+8h 补正）
    """
    logging.info("执行 schema 迁移 v2 → v3：习惯/积分/目标系统")

    # ── 1. habits 表补充字段 ──────────────────────────────────────
    cursor.execute("PRAGMA table_info(habits)")
    habit_cols = {c[1] for c in cursor.fetchall()}

    habit_additions = [
        ("icon",       "TEXT NOT NULL DEFAULT '✅'"),
        ("color",      "TEXT NOT NULL DEFAULT '#A3BE8C'"),
        ("frequency",  "TEXT NOT NULL DEFAULT 'daily'"),
        ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
        ("is_active",  "INTEGER NOT NULL DEFAULT 1"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("difficulty", "TEXT DEFAULT 'easy'"),
    ]
    for col_name, col_def in habit_additions:
        if col_name not in habit_cols:
            cursor.execute(f"ALTER TABLE habits ADD COLUMN {col_name} {col_def}")

    # ── 2. habit_checkins 表补充 status 字段 ─────────────────────
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
    checkin_cols = {c[1] for c in cursor.fetchall()}
    if 'status' not in checkin_cols:
        cursor.execute("ALTER TABLE habit_checkins ADD COLUMN status INTEGER DEFAULT 1")

    # ── 3. 积分流水表 ─────────────────────────────────────────────
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

    # ── 4. 奖励商品表及补充字段 ───────────────────────────────────
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
    reward_cols = {c[1] for c in cursor.fetchall()}
    if 'unlock_task_id' not in reward_cols:
        cursor.execute("ALTER TABLE rewards ADD COLUMN unlock_task_id TEXT DEFAULT NULL")
        cursor.execute("ALTER TABLE rewards ADD COLUMN unlock_task_title TEXT DEFAULT NULL")

    # ── 5. 自定义奖励配置表及补充字段 ────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reward_config (
            item_type TEXT NOT NULL,
            item_id TEXT NOT NULL,
            coins REAL NOT NULL DEFAULT 0.1,
            PRIMARY KEY (item_type, item_id)
        )
    ''')
    cursor.execute("PRAGMA table_info(reward_config)")
    rc_cols = {c[1] for c in cursor.fetchall()}
    if 'penalty' not in rc_cols:
        cursor.execute("ALTER TABLE reward_config ADD COLUMN penalty REAL DEFAULT NULL")

    # ── 6. 外部系统静默打卡奖励表 ────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS external_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ext_id TEXT NOT NULL UNIQUE,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            coins REAL NOT NULL DEFAULT 0,
            status INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── 7. 目标挑战表及补充字段 ───────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category_id INTEGER,
            metric TEXT NOT NULL,
            target_value REAL NOT NULL,
            period TEXT NOT NULL,
            reward_coins REAL DEFAULT 0,
            reward_id INTEGER DEFAULT NULL,
            operator TEXT DEFAULT '>=',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
        )
    ''')
    cursor.execute("PRAGMA table_info(goals)")
    goal_cols = {c[1] for c in cursor.fetchall()}
    if 'reward_id' not in goal_cols:
        cursor.execute("ALTER TABLE goals ADD COLUMN reward_id INTEGER DEFAULT NULL")
    if 'operator' not in goal_cols:
        cursor.execute("ALTER TABLE goals ADD COLUMN operator TEXT DEFAULT '>='")
    if 'penalty_coins' not in goal_cols:
        cursor.execute("ALTER TABLE goals ADD COLUMN penalty_coins REAL DEFAULT 0")

    # ── 8. 修正历史数据中的 UTC 时间偏差（+8h 补正） ─────────────
    # 针对之前因 DEFAULT CURRENT_TIMESTAMP 产生的 UTC 时间（比本地时间少 8 小时）
    try:
        now = datetime.now()
        tables_to_fix = ['habits', 'reward_ledger', 'rewards', 'external_rewards', 'goals']
        for t in tables_to_fix:
            cursor.execute(f"SELECT rowid, created_at FROM {t} WHERE created_at LIKE '2026-%'")
            for rowid, c_at in cursor.fetchall():
                if not c_at or " " not in c_at:
                    continue
                try:
                    dt = datetime.strptime(c_at, '%Y-%m-%d %H:%M:%S')
                    # 补正逻辑：小时数 < 12 且加 8 小时后不超前于当前时间（容错 5 分钟）
                    if dt.hour < 12:
                        new_dt = dt + timedelta(hours=8)
                        if new_dt <= now + timedelta(minutes=5):
                            new_at = new_dt.strftime('%Y-%m-%d %H:%M:%S')
                            cursor.execute(
                                f"UPDATE {t} SET created_at = ? WHERE rowid = ?",
                                (new_at, rowid)
                            )
                except Exception:
                    continue
    except Exception as e:
        logging.error(f"v2→v3 全局时间修正迁移失败: {e}")

    cursor.connection.commit()


def _migrate_v3_to_v4(cursor: sqlite3.Cursor) -> None:
    """
    v3 → v4：重命名 sleep_reflection 为 morning_diary，且添加 evening_diary 字段。
    """
    logging.info("执行 schema 迁移 v3 → v4：重命名 sleep_reflection 且追加 evening_diary")

    cursor.execute("PRAGMA table_info(huawei_sleep_data)")
    existing_cols = {c[1] for c in cursor.fetchall()}

    # 1. 迁移 sleep_reflection 到 morning_diary
    if "sleep_reflection" in existing_cols and "morning_diary" not in existing_cols:
        cursor.execute("ALTER TABLE huawei_sleep_data RENAME COLUMN sleep_reflection TO morning_diary")
    elif "morning_diary" not in existing_cols:
        cursor.execute("ALTER TABLE huawei_sleep_data ADD COLUMN morning_diary TEXT")

    # 2. 迁移 evening_diary
    if "evening_diary" not in existing_cols:
        cursor.execute("ALTER TABLE huawei_sleep_data ADD COLUMN evening_diary TEXT")

    cursor.connection.commit()


def _migrate_v4_to_v5(cursor: sqlite3.Cursor) -> None:
    """
    v4 → v5：在 huawei_sleep_data 表中新增 report_status 字段。
    0: 无报告, 1: 仅有 Part1 睡眠报告, 2: 有完整报告。
    """
    logging.info("执行 schema 迁移 v4 → v5：huawei_sleep_data 补充 report_status 字段")

    cursor.execute("PRAGMA table_info(huawei_sleep_data)")
    existing_cols = {c[1] for c in cursor.fetchall()}

    if "report_status" not in existing_cols:
        cursor.execute("ALTER TABLE huawei_sleep_data ADD COLUMN report_status INTEGER DEFAULT 0")

    cursor.connection.commit()


def _migrate_v5_to_v6(cursor: sqlite3.Cursor) -> None:
    """
    v5 → v6：在数据库中新增 system_config 系统配置表。
    """
    logging.info("执行 schema 迁移 v5 → v6：创建 system_config 系统配置表")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            value_type TEXT NOT NULL,
            description TEXT
        )
    ''')

    cursor.connection.commit()


def _migrate_v6_to_v7(cursor: sqlite3.Cursor) -> None:
    """
    v6 → v7：多端同步基础设施 — 为所有业务表补充 updated_at / pushed_at 列。
    """
    logging.info("执行 schema 迁移 v6 → v7：为所有业务表补充 updated_at / pushed_at 字段")

    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    tables_need_both = [
        'categories', 'habits', 'habit_checkins', 'goals', 'rewards',
        'reward_config', 'external_rewards', 'system_config',
        'study_sessions', 'tasks', 'huawei_sleep_data'
    ]
    tables_need_pushed_only = []

    for table in tables_need_both:
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {c[1] for c in cursor.fetchall()}
            if 'updated_at' not in existing:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN updated_at TIMESTAMP DEFAULT '{now_ts}'"
                )
            if 'pushed_at' not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN pushed_at TIMESTAMP DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # 表由其他模块按需创建，此时尚不存在

    for table in tables_need_pushed_only:
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {c[1] for c in cursor.fetchall()}
            if 'pushed_at' not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN pushed_at TIMESTAMP DEFAULT NULL")
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("PRAGMA table_info(reward_ledger)")
        ledger_cols = {c[1] for c in cursor.fetchall()}
        if 'pushed_at' not in ledger_cols:
            cursor.execute("ALTER TABLE reward_ledger ADD COLUMN pushed_at TIMESTAMP DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    cursor.connection.commit()


def _migrate_v7_to_v8(cursor: sqlite3.Cursor) -> None:
    """
    v7 → v8：将 external_rewards 和 system_config 的主键改为自增 id，原主键改为 ext_id / key UNIQUE。
    """
    logging.info("执行 schema 迁移 v7 → v8：重构 external_rewards 和 system_config 的主键")

    # 迁移 external_rewards
    try:
        cursor.execute("SELECT ext_id FROM external_rewards LIMIT 0")
    except sqlite3.OperationalError:
        # 表中没有 ext_id，说明是旧表
        cursor.execute("ALTER TABLE external_rewards RENAME TO old_external_rewards")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS external_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ext_id TEXT NOT NULL UNIQUE,
                item_type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                coins REAL NOT NULL DEFAULT 0,
                status INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                pushed_at TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO external_rewards (ext_id, item_type, item_name, coins, status, created_at, updated_at, pushed_at)
            SELECT id, item_type, item_name, coins, status, created_at, updated_at, pushed_at FROM old_external_rewards
        """)
        cursor.execute("DROP TABLE old_external_rewards")

    # 迁移 system_config
    try:
        cursor.execute("SELECT id FROM system_config LIMIT 0")
    except sqlite3.OperationalError:
        # 表中没有 id，说明是旧表
        cursor.execute("ALTER TABLE system_config RENAME TO old_system_config")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'string',
                description TEXT,
                updated_at TIMESTAMP,
                pushed_at TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO system_config (key, value, value_type, description, updated_at, pushed_at)
            SELECT key, value, value_type, description, updated_at, pushed_at FROM old_system_config
        """)
        cursor.execute("DROP TABLE old_system_config")

    cursor.connection.commit()
