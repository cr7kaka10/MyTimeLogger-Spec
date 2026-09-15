# -*- coding: utf-8 -*-
import sqlite3

from ..statistics_start_date import resolve_statistics_start_date
from .provider_mirror_schema_migration import migrate_provider_mirror_identity


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]):
    existing = {
        r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_exercise_daily_logs_unique(conn: sqlite3.Connection):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='server_exercise_daily_logs'"
    ).fetchone()
    sql = (row[0] if row else "") or ""
    if "UNIQUE(user_id, date, exercise_type)" not in sql:
        return

    columns = {
        r[1] for r in conn.execute("PRAGMA table_info(server_exercise_daily_logs)").fetchall()
    }
    select = {
        "id": "id",
        "user_id": "user_id",
        "date": "date",
        "plan_version": "plan_version" if "plan_version" in columns else "'v0'",
        "exercise_type": "exercise_type",
        "week_num": "week_num" if "week_num" in columns else "1",
        "day_name": "day_name" if "day_name" in columns else "NULL",
        "weight": "weight" if "weight" in columns else "NULL",
        "body_fat_rate": "body_fat_rate" if "body_fat_rate" in columns else "NULL",
        "completed_items": "completed_items" if "completed_items" in columns else "0",
        "total_items": "total_items" if "total_items" in columns else "0",
        "exercise_variant": "exercise_variant" if "exercise_variant" in columns else "'gym'",
        "duration_minutes": "duration_minutes" if "duration_minutes" in columns else "0",
        "calories": "calories" if "calories" in columns else "0.0",
        "heart_rate_avg": "heart_rate_avg" if "heart_rate_avg" in columns else "NULL",
        "score_snapshot": "score_snapshot" if "score_snapshot" in columns else "NULL",
        "locked_at": "locked_at" if "locked_at" in columns else "NULL",
        "created_at": "created_at",
        "updated_at": "updated_at" if "updated_at" in columns else "created_at",
        "pushed_at": "pushed_at" if "pushed_at" in columns else "NULL",
    }
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        conn.execute("ALTER TABLE server_exercise_daily_logs RENAME TO server_exercise_daily_logs_legacy")
        conn.execute(
            """
            CREATE TABLE server_exercise_daily_logs (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, date TEXT NOT NULL,
                plan_version TEXT NOT NULL DEFAULT 'v0', exercise_type TEXT NOT NULL,
                week_num INTEGER DEFAULT 1, day_name TEXT, weight REAL, body_fat_rate REAL,
                completed_items INTEGER DEFAULT 0, total_items INTEGER DEFAULT 0,
                exercise_variant TEXT NOT NULL DEFAULT 'gym',
                duration_minutes INTEGER DEFAULT 0, calories REAL DEFAULT 0.0,
                heart_rate_avg INTEGER, score_snapshot TEXT, locked_at TEXT,
                created_at TEXT NOT NULL, updated_at TEXT, pushed_at TEXT,
                UNIQUE(user_id, date, plan_version, exercise_type),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        keys = ",".join(select.keys())
        vals = ",".join(select.values())
        conn.execute(f"INSERT OR REPLACE INTO server_exercise_daily_logs ({keys}) SELECT {vals} FROM server_exercise_daily_logs_legacy")
        conn.execute("DROP TABLE server_exercise_daily_logs_legacy")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

def ensure_server_schema(conn: sqlite3.Connection):
    """创建或更新服务端数据库 Schema，确保所有 18 张表齐全，且字段具有详细注释"""

    # 1. 用户表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 用户自增主键
            username TEXT UNIQUE NOT NULL,        -- 用户名（唯一）
            password_hash TEXT NOT NULL,          -- 密码哈希
            created_at TEXT NOT NULL              -- 创建时间
        )
        """
    )

    # 2. 登录会话表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 会话自增主键
            token TEXT NOT NULL UNIQUE,           -- 登录令牌（唯一）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            created_at TEXT NOT NULL,             -- 创建时间
            expires_at TEXT,                      -- 过期时间
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 3. 睡眠识别任务表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_sleep_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 任务自增主键
            request_id TEXT NOT NULL UNIQUE,      -- 请求唯一标识
            user_id INTEGER,                     -- 所属用户ID
            date TEXT,                           -- 睡眠日期
              status TEXT NOT NULL,                 -- 任务状态（pending/done/error）
              image_path TEXT,                      -- 睡眠截图路径
              image_hash TEXT,                      -- 上传图片 SHA-256
              result_json TEXT,                     -- AI识别结果JSON
            analysis_report TEXT,                 -- AI分析报告文本
            error TEXT,                           -- 错误信息
            created_at TEXT NOT NULL,             -- 创建时间
            updated_at TEXT NOT NULL,             -- 最后更新时间
            sync_count INTEGER DEFAULT 0,         -- 同步推送次数
            acked_at TEXT,                        -- 客户端确认时间
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 4. 分类表 (保持自增)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 分类自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            name TEXT NOT NULL,                   -- 分类名称（如：副业、生活、增益）
            group_name TEXT NOT NULL,             -- 分类分组名
            icon TEXT,                            -- 分类图标
            color TEXT,                           -- 分类颜色（十六进制）
            sort_order INTEGER NOT NULL DEFAULT 0, -- 排序权重值（从1开始）
            updated_at TEXT,                      -- 最后更新时间
            pushed_at TEXT,                       -- 最后推送时间
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, name)
        )
        """
    )

    # 5. 日清单任务表 (主键=滴答清单任务ID)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_tasks (
            id TEXT NOT NULL,                     -- 滴答清单任务ID（账号内唯一）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            title TEXT NOT NULL,                  -- 任务标题
            priority INTEGER DEFAULT 0,           -- 优先级（0=无,1=低,3=中,5=高）
            status INTEGER DEFAULT 0,             -- 状态（0=未完成,2=已完成）
            category_id INTEGER,                  -- 关联分类ID（反查server_categories）
            due_date TEXT,                        -- 截止时间（ISO格式，与滴答清单一致）
            tags TEXT,                            -- 标签列表（JSON数组字符串）
            raw_json TEXT,                        -- 滴答清单原始数据快照（完整JSON）
            source TEXT NOT NULL DEFAULT 'ticktick', -- 来源(local/ticktick)
            source_etag TEXT,                     -- 滴答清单 etag 指纹（用于增量筛选）
            source_modified_time TEXT,            -- 滴答清单 modifiedTime 指纹兜底
            deleted_at TEXT DEFAULT NULL,         -- 删除墓碑时间（NULL=未删除）
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            PRIMARY KEY (user_id, id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (category_id) REFERENCES server_categories(id)
        )
        """
    )

    # 6. 专注会话表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_study_sessions (
            id TEXT PRIMARY KEY,                  -- 会话主键（UUID）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            start_time TEXT NOT NULL,             -- 开始时间
            end_time TEXT NOT NULL,               -- 结束时间
            net_duration_minutes REAL NOT NULL,   -- 净专注时长（分钟）
            net_duration_seconds INTEGER,        -- 净专注时长（秒）
            date TEXT NOT NULL,                   -- 日期（YYYY-MM-DD）
            day_of_week TEXT,                     -- 星期几
            pause_count INTEGER DEFAULT 0,        -- 暂停次数
            pause_reasons TEXT,                   -- 暂停原因
            session_summary TEXT,                 -- 会话小结
            category_id INTEGER,                  -- 关联分类ID
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (category_id) REFERENCES server_categories(id)
        )
        """
    )

    # Stable completed sessions are backed up asynchronously; no live timer state lives here.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_atimelogger_backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            stable_session_id TEXT NOT NULL,
            remote_activity_id TEXT,
            remote_interval_id TEXT,
            sync_state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error_code TEXT,
            last_error_step TEXT,
            running_baseline_json TEXT,
            next_retry_at TEXT,
            claimed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, stable_session_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_atimelogger_backups_due "
        "ON server_atimelogger_backups(sync_state, next_retry_at, claimed_at)"
    )
    _ensure_columns(
        conn,
        "server_atimelogger_backups",
        {"last_error_step": "TEXT", "running_baseline_json": "TEXT"},
    )

    # 7. 习惯配置表（主键=滴答清单习惯ID）
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_habits (
            id TEXT NOT NULL,                     -- 滴答清单习惯ID（账号内唯一）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            name TEXT NOT NULL,                   -- 习惯名称
            icon TEXT,                            -- 习惯图标
            color TEXT DEFAULT '#A3BE8C',         -- 习惯颜色（十六进制）
            sort_order INTEGER DEFAULT 0,         -- 排序权重
            category_id INTEGER DEFAULT NULL,     -- 关联分类ID
            difficulty TEXT DEFAULT 'medium',     -- 难度（easy/medium/hard）
            repeat_rule TEXT DEFAULT NULL,        -- 重复规则（滴答清单 RRULE）
            is_active INTEGER DEFAULT 0,          -- 是否归档（1归档,0未归档，正常显示）
            raw_json TEXT,                        -- 滴答清单原始数据快照（完整JSON）
            source TEXT NOT NULL DEFAULT 'ticktick', -- 来源(local/ticktick)
            source_etag TEXT,                     -- 滴答清单 etag 指纹（用于增量筛选）
            source_modified_time TEXT,            -- 滴答清单 modifiedTime 指纹兜底
            created_at TEXT NOT NULL,             -- 创建时间
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            PRIMARY KEY (user_id, id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )

        """
    )

    # 8. 习惯打卡流水表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_habit_checkins (
            id TEXT NOT NULL,                     -- 打卡记录ID（账号内唯一）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            habit_id TEXT NOT NULL,               -- 关联习惯ID
            habit_name TEXT,                      -- 习惯名称
            date TEXT,                            -- 日期（兼容旧字段）
            created_at TEXT,                      -- 创建时间
            checkin_date TEXT,                    -- 打卡日期（YYYY-MM-DD）
            checkin_time TEXT,                    -- 打卡时间
            status INTEGER DEFAULT 0,             -- 打卡状态（2=已打卡, 1=打卡失败, 0=未打卡）
            note TEXT,                            -- 打卡备注
            raw_json TEXT,                        -- 滴答清单原始打卡数据快照（完整JSON）
            source_modified_time TEXT,            -- 滴答清单 opTime 指纹（用于增量筛选）
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            PRIMARY KEY (user_id, id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (user_id, habit_id) REFERENCES server_habits(user_id, id),
            UNIQUE(user_id, habit_id, checkin_date)
        )
        """
    )

    # 9. 奖励商品配置表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_rewards (
            id TEXT PRIMARY KEY,                  -- 商品主键（UUID）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            title TEXT NOT NULL,                  -- 商品名称
            icon TEXT DEFAULT '🎁',                -- 商品图标
            price REAL NOT NULL,                  -- 兑换价格（金币）
            redemption_mode TEXT NOT NULL DEFAULT 'coins', -- coins/task/goal/pending_binding/custom_spend
            description TEXT,                     -- 商品描述
            unlock_task_id TEXT,                  -- 绑定任务ID（完成后自动解锁）
            unlock_task_title TEXT,               -- 绑定任务标题
            unlock_source_type TEXT,              -- 显式解锁来源类型（checklist_task/habit/learning_task/exercise_checkin/goal）
            unlock_source_id TEXT,                -- 显式解锁来源稳定ID
            inventory_mode TEXT NOT NULL DEFAULT 'unlimited', -- 不限量/日/周/月库存
            inventory_limit INTEGER,              -- 限量库存的每窗口上限
            unlock_required_count INTEGER NOT NULL DEFAULT 1, -- 习惯累计打卡解锁阈值
            unlock_threshold_started_at TEXT,     -- 阈值开始累计的服务端时间
            fulfillment_mode TEXT NOT NULL DEFAULT 'immediate', -- immediate/fragment
            fragment_target_count INTEGER NOT NULL DEFAULT 1, -- 碎片目标数 n，也是有效期自然日数
            fragment_rule_version INTEGER NOT NULL DEFAULT 1, -- 配置切换后的隔离版本
            is_active INTEGER DEFAULT 1,          -- 是否上架（1=是,0=否）
            created_at TEXT NOT NULL,             -- 创建时间
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_reward_fragments (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            reward_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            completion_event_key TEXT NOT NULL,
            rule_version INTEGER NOT NULL,
            progress_units INTEGER NOT NULL DEFAULT 100,
            consumed_units INTEGER NOT NULL DEFAULT 0,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            compose_batch_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, reward_id, completion_event_key),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(reward_id) REFERENCES server_rewards(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_server_reward_fragments_active "
        "ON server_reward_fragments(user_id, reward_id, rule_version, status, expires_at)"
    )

    # 9.2 完成奖励商品与完成来源的独立多对多绑定（服务端权威、仅下拉）。
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_reward_source_bindings (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            reward_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            drop_mode TEXT NOT NULL DEFAULT 'fixed',
            drop_min_units INTEGER,
            drop_max_units INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, reward_id, source_type, source_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(reward_id) REFERENCES server_rewards(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reward_source_bindings_source "
        "ON server_reward_source_bindings(user_id, source_type, source_id)"
    )
    _ensure_columns(conn, "server_reward_fragments", {"progress_units": "INTEGER", "consumed_units": "INTEGER"})
    _ensure_columns(conn, "server_reward_source_bindings", {
        "drop_mode": "TEXT", "drop_min_units": "INTEGER", "drop_max_units": "INTEGER",
    })
    conn.execute("""UPDATE server_reward_fragments SET progress_units=MAX(1, CAST((99 + COALESCE((SELECT fragment_target_count FROM server_rewards r WHERE r.id=reward_id),1)) / COALESCE((SELECT fragment_target_count FROM server_rewards r WHERE r.id=reward_id),1) AS INTEGER)) WHERE progress_units IS NULL""")
    conn.execute("UPDATE server_reward_fragments SET consumed_units=0 WHERE consumed_units IS NULL")
    # 运动奖励从单项打卡迁移到每日总分；保留既有账本，不再保留可触发的单项绑定。
    conn.execute("DELETE FROM server_reward_source_bindings WHERE source_type='exercise_checkin'")

    # 10.1 目标与分类的服务端权威多对多绑定。id 用于版本化增量同步。
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_goal_category_bindings (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            goal_id TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            pushed_at TEXT DEFAULT NULL,
            UNIQUE(user_id, goal_id, category_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(goal_id) REFERENCES server_goals(id),
            FOREIGN KEY(category_id) REFERENCES server_categories(id)
        )
        """
    )

    # 10. 目标挑战配置表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_goals (
            id TEXT PRIMARY KEY,                  -- 目标主键（UUID）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            title TEXT NOT NULL,                  -- 目标标题
            category_id INTEGER,                  -- 关联分类ID
            metric TEXT NOT NULL,                 -- 度量类型（duration/count）
            target_value REAL NOT NULL,           -- 目标值
            period TEXT NOT NULL,                 -- 周期（daily/weekly/monthly/per_session）
            operator TEXT DEFAULT '>=',           -- 判断运算符
            reward_coins REAL NOT NULL,           -- 达标奖励金币数
            reward_id TEXT,                       -- 关联奖励商品ID
            penalty_coins REAL,                   -- 未达标惩罚金币数
            is_active INTEGER DEFAULT 1,          -- 是否激活（1=是,0=否）
            created_at TEXT NOT NULL,             -- 创建时间
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (category_id) REFERENCES server_categories(id),
            FOREIGN KEY (reward_id) REFERENCES server_rewards(id)
        )
        """
    )

    # 11. 金币收支流水表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_reward_ledger (
            id TEXT PRIMARY KEY,                  -- 流水主键（UUID）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            amount REAL NOT NULL,                 -- 金额（正=收入,负=支出）
            source_type TEXT NOT NULL,            -- 来源类型（task_complete/habit_checkin/goal_settle等）
            source_id TEXT,                       -- 来源唯一标识
            description TEXT,                     -- 流水描述
            target_date TEXT,                     -- 归属日期（补卡时为被补卡日期）
            occurred_at TEXT,                     -- 业务实际发生时间（北京时间，可为空）
            created_at TEXT NOT NULL,             -- 创建时间
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    # 同一奖励来源事件只允许生成一件零价自动入包物品。
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_server_reward_unlock_event
        ON server_reward_ledger(user_id, source_type, source_id)
        WHERE source_type = 'reward_buy' AND source_id LIKE 'unlock:%'
        """
    )

    # 12. 待发放奖励队列表（幂等去重）
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_external_rewards (
            id TEXT PRIMARY KEY,                  -- 记录主键（UUID）
            ext_id TEXT NOT NULL,                 -- 外部唯一标识（如 task_{id}、habit_{id}_{stamp}）
            user_id INTEGER NOT NULL,             -- 所属用户ID
            item_type TEXT NOT NULL,              -- 类型（task/habit/goal）
            item_name TEXT NOT NULL,              -- 名称描述
            coins REAL NOT NULL,                  -- 待发金币数
            status INTEGER DEFAULT 0,             -- 状态（0=待发放,1=已发放）
            created_at TEXT NOT NULL,             -- 创建时间
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            UNIQUE(user_id, ext_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 13. 任务/习惯单独奖惩系数配置表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_reward_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 配置自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            item_type TEXT NOT NULL,              -- 条目类型（task/habit）
            item_id TEXT NOT NULL,                -- 条目ID（任务ID或习惯ID）
            coins REAL NOT NULL,                  -- 奖励金币数（reward）
            penalty REAL,                         -- 惩罚金币数
            updated_at TEXT,                      -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, item_type, item_id)
        )
        """
    )

    # 14. 睡眠指标记录表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_huawei_sleep_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            date TEXT NOT NULL,                   -- 睡眠日期（YYYY-MM-DD）
            sleep_score INTEGER,                  -- 睡眠评分（0-100）
            total_sleep_min INTEGER,              -- 总睡眠时长（分钟）
            deep_sleep_min INTEGER,               -- 深睡时长（分钟）
            light_sleep_min INTEGER,              -- 浅睡时长（分钟）
            rem_sleep_min INTEGER,                -- REM睡眠时长（分钟）
            awake_count INTEGER,                  -- 夜醒次数
            sleep_start TEXT,                     -- 入睡时间
            sleep_end TEXT,                       -- 起床时间
            deep_sleep_ratio INTEGER,             -- 深睡占比（%）
            light_sleep_ratio INTEGER,            -- 浅睡占比（%）
            rem_sleep_ratio INTEGER,              -- REM占比（%）
            sleep_continuity INTEGER,             -- 睡眠连续性评分
            breathing_score INTEGER,              -- 呼吸质量评分
            sleep_cycles REAL,                    -- 睡眠周期数
            awake_min INTEGER,                    -- 清醒时长（分钟）
            fall_asleep_min INTEGER,              -- 入睡耗时（分钟）
            wake_up_min INTEGER,                  -- 清醒耗时（分钟）
              atm_sleep_start TEXT,                 -- aTimeLogger记录的入睡时间
              atm_sleep_end TEXT,                   -- aTimeLogger记录的起床时间
              calc_trace TEXT,                       -- 睡眠派生指标计算链路
              analysis_report TEXT,                 -- AI睡眠分析报告
              analysis_html TEXT,                   -- AI睡眠分析报告HTML
              official_advice TEXT,                 -- 华为运动健康官方建议原文
            morning_diary TEXT,                   -- 晨间日记
            evening_diary TEXT,                   -- 晚间日记
            morning_diary_written_at TEXT,        -- 晨间日记实际保存时间
            evening_diary_written_at TEXT,        -- 晚间日记实际保存时间
            report_status INTEGER DEFAULT 0,      -- 报告状态（0=未生成,1=已生成）
            full_report_state TEXT,               -- 完整报告状态（generated/insufficient_time_records）
            tracked_duration_seconds INTEGER,     -- aTimeLogger 当天累计记录秒数
            source TEXT DEFAULT 'screenshot_ocr', -- 睡眠数据来源
            synced_at TEXT,                       -- 外部来源同步时间
            sync_status TEXT DEFAULT 'success',   -- 外部同步状态
            sync_error TEXT,                      -- 外部同步错误信息
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            UNIQUE(user_id, date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    _ensure_columns(
        conn,
        "server_huawei_sleep_data",
        {
            "source": "TEXT DEFAULT 'screenshot_ocr'",
            "synced_at": "TEXT",
            "sync_status": "TEXT DEFAULT 'success'",
            "sync_error": "TEXT",
            "analysis_html": "TEXT",
            "official_advice": "TEXT",
            "calc_trace": "TEXT",
            "morning_diary_written_at": "TEXT",
            "evening_diary_written_at": "TEXT",
            "full_report_state": "TEXT",
            "tracked_duration_seconds": "INTEGER",
            "atm_sleep_start": "TEXT",
            "atm_sleep_end": "TEXT",
        },
    )

    # 15. 云端钱包快照表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_user_wallets (
            user_id INTEGER PRIMARY KEY,          -- 用户ID（主键）
            balance REAL NOT NULL DEFAULT 0.0,    -- 当前金币余额
            last_ledger_uuid TEXT,                -- 最后一笔流水UUID（防重复计算）
            updated_at TEXT NOT NULL,             -- 最后更新时间
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 16. aTimeLogger 备份汇总表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_atm_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            date TEXT NOT NULL,                   -- 汇总日期（YYYY-MM-DD）
            updated_at TEXT NOT NULL,             -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, date)
        )
        """
    )

    # 17. aTimeLogger 备份活动流水表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_atm_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            date TEXT NOT NULL,                   -- 活动日期（YYYY-MM-DD）
            activity_type TEXT NOT NULL,          -- 活动类型名称
            start_time TEXT NOT NULL,             -- 开始时间
            end_time TEXT NOT NULL,               -- 结束时间
            duration_minutes INTEGER NOT NULL,    -- 持续时长（分钟）
            comment TEXT,                         -- 备注
            updated_at TEXT,                      -- 最后更新时间
            pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 18. 系统配置表（多端同步用）
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            key TEXT NOT NULL,                    -- 配置键名（如 ticktick_config）
            value TEXT NOT NULL,                  -- 配置值（JSON字符串）
            value_type TEXT NOT NULL DEFAULT 'string', -- 值类型（string/json/int）
            description TEXT,                     -- 配置描述
            updated_at TEXT NOT NULL,             -- 最后更新时间
            UNIQUE(user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS server_reward_action_events (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, event_type TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0, occurred_at TEXT NOT NULL,
            subject_id TEXT, payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
            UNIQUE(user_id, id), FOREIGN KEY(user_id) REFERENCES users(id))"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reward_action_user_time "
        "ON server_reward_action_events(user_id, occurred_at)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS server_reward_rebuild_jobs (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, status TEXT NOT NULL,
            statistics_start_date TEXT NOT NULL, preview_hash TEXT NOT NULL,
            frozen_revision TEXT NOT NULL, pull_diagnostics_json TEXT,
            result_json TEXT, error TEXT, trace_id TEXT, failure_report_json TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id))"""
    )
    _ensure_columns(conn, "server_reward_rebuild_jobs", {
        "trace_id": "TEXT", "failure_report_json": "TEXT",
    })
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_reward_rebuild_running
           ON server_reward_rebuild_jobs(user_id)
           WHERE status IN ('queued','running')"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS server_reward_rebuild_snapshots (
            job_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, epoch INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id))"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS server_reward_rebuild_epochs (
            user_id INTEGER PRIMARY KEY, active_epoch INTEGER NOT NULL DEFAULT 0,
            published_version INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id))"""
    )
    _ensure_columns(conn, "server_reward_rebuild_epochs", {"published_version": "INTEGER NOT NULL DEFAULT 0"})

    # 19. 同步状态水位表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_sync_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            system TEXT NOT NULL,                 -- 同步系统（client/ticktick）
            direction TEXT NOT NULL,              -- 同步方向（client_to_server/server_to_client/server_to_ticktick/ticktick_to_server）
            last_synced_at TEXT,                  -- 最后成功同步时间（北京时间）
            last_attempted_at TEXT,               -- 最后尝试同步时间（北京时间）
            last_status TEXT NOT NULL DEFAULT 'pending', -- 最后同步状态（pending/success/error）
            last_error TEXT,                      -- 最后错误信息
            last_merged_count INTEGER DEFAULT 0,  -- 最后合并记录数
            diagnostics_json TEXT,                -- 最近一次同步诊断详情（JSON）
            created_at TEXT NOT NULL,             -- 创建时间（北京时间）
            updated_at TEXT NOT NULL,             -- 最后更新时间（北京时间）
            UNIQUE(user_id, system, direction),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 20. 服务端版本计数表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_version_counters (
            user_id INTEGER PRIMARY KEY,          -- 所属用户ID（每个用户独立递增版本）
            current_version INTEGER NOT NULL DEFAULT 0, -- 当前服务端版本号（严格递增）
            updated_at TEXT NOT NULL,             -- 最后分配版本时间（北京时间）
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS server_sync_migrations (
            user_id INTEGER NOT NULL, migration_key TEXT NOT NULL,
            completed_at TEXT NOT NULL, PRIMARY KEY(user_id, migration_key),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )"""
    )

    # 21. 服务端变更日志表（兼容旧 change_id 幂等日志，并承载 server_version 变更流）
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            server_version INTEGER,               -- 服务端变更版本号（按用户严格递增）
            change_id TEXT NOT NULL,              -- 客户端变更唯一ID
            device_id TEXT,                       -- 客户端设备ID
            table_name TEXT NOT NULL,             -- 业务表名
            record_id TEXT NOT NULL,              -- 业务记录ID
            entity_type TEXT,                     -- 同步实体类型（如 task/habit/reward_ledger）
            entity_id TEXT,                       -- 同步实体ID
            operation TEXT NOT NULL,              -- 操作类型(upsert/delete/archive)
            changed_fields_json TEXT,             -- 本次变更字段快照（JSON）
            status TEXT NOT NULL DEFAULT 'applied', -- 处理状态(applied/ignored/failed)
            error TEXT,                           -- 失败原因
            changed_at TEXT,                      -- 业务变更时间（北京时间）
            created_at TEXT NOT NULL,             -- 创建时间（北京时间）
            UNIQUE(user_id, change_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 22. 同步冲突日志表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_sync_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
            user_id INTEGER NOT NULL,             -- 所属用户ID
            device_id TEXT,                       -- 客户端设备ID
            table_name TEXT NOT NULL,             -- 冲突表名
            record_id TEXT NOT NULL,              -- 冲突记录ID
            field_name TEXT,                      -- 冲突字段名
            client_base_version INTEGER,          -- 客户端提交基于的服务端版本
            server_version INTEGER,               -- 冲突发生时的服务端版本
            client_value TEXT,                    -- 客户端提交值
            server_value TEXT,                    -- 服务端已有值
            strategy TEXT,                        -- 冲突处理策略
            result TEXT,                          -- 冲突处理结果
            resolution TEXT NOT NULL,             -- 处理策略和结果（兼容旧字段）
            created_at TEXT NOT NULL,             -- 创建时间（北京时间）
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # 22. 运动日记录表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_exercise_plan_versions (
            version TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            source_name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            exercise_points INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            PRIMARY KEY(version, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_exercise_daily_logs (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            exercise_type TEXT NOT NULL,
            week_num INTEGER DEFAULT 1,
            day_name TEXT,
            weight REAL,
            body_fat_rate REAL,
            completed_items INTEGER DEFAULT 0,
            total_items INTEGER DEFAULT 0,
            exercise_variant TEXT NOT NULL DEFAULT 'gym',
            duration_minutes INTEGER DEFAULT 0,
            calories REAL DEFAULT 0.0,
            heart_rate_avg INTEGER,
            score_snapshot TEXT,
            locked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            UNIQUE(user_id, date, plan_version, exercise_type),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    # 20. 运动打卡表
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_exercise_checkins (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            log_id TEXT NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            status INTEGER DEFAULT 0,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(log_id) REFERENCES server_exercise_daily_logs(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_exercise_item_scores (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            item_key TEXT NOT NULL,
            earned_points REAL NOT NULL DEFAULT 0,
            max_points REAL NOT NULL DEFAULT 0,
            difficulty TEXT,
            score_rule_version TEXT NOT NULL DEFAULT 'v1',
            score_reason TEXT,
            score_scope TEXT NOT NULL DEFAULT 'schedule',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            UNIQUE(user_id, date, plan_version, item_key),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_exercise_settlements (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            business_date TEXT NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            score_snapshot TEXT,
            score_total REAL NOT NULL DEFAULT 0,
            category_scores TEXT,
            completed_items INTEGER NOT NULL DEFAULT 0,
            total_items INTEGER NOT NULL DEFAULT 0,
            settlement_status TEXT NOT NULL DEFAULT 'pending',
            reason_code TEXT,
            rule_version TEXT NOT NULL DEFAULT 'v1',
            coin_amount REAL NOT NULL DEFAULT 0,
            is_all_complete INTEGER NOT NULL DEFAULT 0,
            completion_reward_amount REAL NOT NULL DEFAULT 0,
            completion_reason TEXT,
            occurred_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            UNIQUE(user_id, business_date, plan_version),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_exercise_diet_checkins (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, date TEXT NOT NULL,
            plan_version TEXT NOT NULL, rule_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', occurred_at TEXT,
            deadline_at TEXT NOT NULL, failure_reason TEXT, penalty_source_id TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(user_id,date,plan_version,rule_key), FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_exercise_deadline_facts (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, date TEXT NOT NULL,
            plan_version TEXT NOT NULL, fact_type TEXT NOT NULL,
            status TEXT NOT NULL, deadline_at TEXT NOT NULL, reason TEXT,
            penalty_source_id TEXT, penalty_amount REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(user_id,date,plan_version,fact_type), FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_sleep_automation_runs (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, sleep_date TEXT NOT NULL,
            step TEXT NOT NULL, status TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, UNIQUE(user_id, sleep_date, step),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_sleep_automation_commands (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, sleep_date TEXT NOT NULL,
            command_type TEXT NOT NULL, scheduled_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(user_id, sleep_date, command_type),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_sleep_notifications (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, sleep_date TEXT NOT NULL,
            event_type TEXT NOT NULL, title TEXT NOT NULL, body TEXT, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(user_id, sleep_date, event_type),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_sleep_command_receipts (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, device_id TEXT NOT NULL, command_id TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(user_id, device_id, command_id), FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_sleep_notification_receipts (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, device_id TEXT NOT NULL, notification_id TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(user_id, device_id, notification_id), FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_sleep_score_settlements (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, sleep_date TEXT NOT NULL,
            metrics_snapshot TEXT NOT NULL, score_breakdown TEXT NOT NULL, score_total INTEGER NOT NULL,
            reward_amount REAL NOT NULL, cycle_penalty REAL NOT NULL, net_amount REAL NOT NULL,
            settlement_status TEXT NOT NULL, missing_fields TEXT, rule_version TEXT NOT NULL,
            occurred_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            report_completed_at TEXT, completion_reward_amount REAL NOT NULL DEFAULT 0,
            is_all_complete INTEGER NOT NULL DEFAULT 0, completion_reason TEXT,
            diary_completion_status TEXT NOT NULL DEFAULT 'pending',
            diary_completion_reward_amount REAL NOT NULL DEFAULT 0,
            diary_completion_reason TEXT,
            diary_completion_rule_version TEXT,
            morning_diary_reward_status TEXT NOT NULL DEFAULT 'pending',
            morning_diary_reward_amount REAL NOT NULL DEFAULT 0,
            morning_diary_reward_reason TEXT, morning_diary_reward_rule_version TEXT,
            evening_diary_reward_status TEXT NOT NULL DEFAULT 'pending',
            evening_diary_reward_amount REAL NOT NULL DEFAULT 0,
            evening_diary_reward_reason TEXT, evening_diary_reward_rule_version TEXT,
            bedtime_coin_status TEXT NOT NULL DEFAULT 'pending',
            bedtime_coin_amount REAL NOT NULL DEFAULT 0,
            bedtime_coin_reason TEXT, bedtime_coin_rule_version TEXT,
            UNIQUE(user_id, sleep_date, rule_version), FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    _ensure_columns(conn, "server_sleep_score_settlements", {
        "report_completed_at": "TEXT", "completion_reward_amount": "REAL NOT NULL DEFAULT 0",
        "is_all_complete": "INTEGER NOT NULL DEFAULT 0", "completion_reason": "TEXT",
        "diary_completion_status": "TEXT NOT NULL DEFAULT 'pending'",
        "diary_completion_reward_amount": "REAL NOT NULL DEFAULT 0",
        "diary_completion_reason": "TEXT", "diary_completion_rule_version": "TEXT",
        "morning_diary_reward_status": "TEXT NOT NULL DEFAULT 'pending'",
        "morning_diary_reward_amount": "REAL NOT NULL DEFAULT 0",
        "morning_diary_reward_reason": "TEXT", "morning_diary_reward_rule_version": "TEXT",
        "evening_diary_reward_status": "TEXT NOT NULL DEFAULT 'pending'",
        "evening_diary_reward_amount": "REAL NOT NULL DEFAULT 0",
        "evening_diary_reward_reason": "TEXT", "evening_diary_reward_rule_version": "TEXT",
        "bedtime_coin_status": "TEXT NOT NULL DEFAULT 'pending'",
        "bedtime_coin_amount": "REAL NOT NULL DEFAULT 0",
        "bedtime_coin_reason": "TEXT", "bedtime_coin_rule_version": "TEXT",
    })

    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_exercise_plan_items (
            id TEXT NOT NULL, user_id INTEGER NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0', day_key TEXT NOT NULL,
            variant TEXT NOT NULL, section TEXT NOT NULL, sort_order INTEGER NOT NULL,
            name TEXT NOT NULL, sets TEXT, intensity TEXT, tags_json TEXT,
            progression TEXT, color TEXT, is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT, pushed_at TEXT,
            PRIMARY KEY (id, user_id), FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_exercise_plan_schedule_items (
            id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            schedule_type TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            time TEXT NOT NULL,
            item TEXT NOT NULL,
            note TEXT,
            accent TEXT NOT NULL DEFAULT 'default',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            PRIMARY KEY (id, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_exercise_plan_diet_rules (
            id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            rule_key TEXT,
            sort_order INTEGER NOT NULL,
            time TEXT NOT NULL,
            content TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            PRIMARY KEY (id, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_exercise_plan_score_rules (
            id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            day_type TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            schedule_index INTEGER NOT NULL,
            points REAL NOT NULL,
            category TEXT NOT NULL,
            target_time TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            PRIMARY KEY (id, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_exercise_plan_category_rules (
            id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            sort_order INTEGER NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            PRIMARY KEY (id, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_exercise_plan_progress_items (
            id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            plan_version TEXT NOT NULL DEFAULT 'v0',
            sort_order INTEGER NOT NULL,
            when_text TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            PRIMARY KEY (id, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_seed_initializations (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            module TEXT NOT NULL,
            seed_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'applied',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(user_id, module, seed_version),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_sample_data_initializations (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            module TEXT NOT NULL,
            sample_data_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'applied',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE(user_id, module, sample_data_version),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO server_sample_data_initializations
          (id, user_id, module, sample_data_version, status, created_at, updated_at)
        SELECT id, user_id, module, seed_version, status, created_at, updated_at
        FROM server_seed_initializations
    """)
    for column, ddl in (("plan_item_id", "TEXT"), ("item_name", "TEXT"), ("item_key", "TEXT"), ("date", "TEXT"), ("completed_time", "TEXT"), ("plan_version", "TEXT NOT NULL DEFAULT 'v0'"), ("note", "TEXT"), ("locked_at", "TEXT"), ("lock_reason", "TEXT"), ("deadline_penalty_source_id", "TEXT"), ("deadline_penalty_amount", "REAL")):
        try:
            conn.execute(f"ALTER TABLE server_exercise_checkins ADD COLUMN {column} {ddl}")
        except Exception:
            pass
    try:
        conn.execute("ALTER TABLE server_exercise_plan_diet_rules ADD COLUMN rule_key TEXT")
    except Exception:
        pass
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_server_exercise_checkins_user_date_version_item ON server_exercise_checkins(user_id,date,plan_version,item_key)")
    except Exception:
        pass
    for column, ddl in (
        ("unlock_source_type", "TEXT"),
        ("unlock_source_id", "TEXT"),
        ("inventory_mode", "TEXT NOT NULL DEFAULT 'unlimited'"),
        ("inventory_limit", "INTEGER"),
        ("unlock_required_count", "INTEGER NOT NULL DEFAULT 1"),
        ("unlock_threshold_started_at", "TEXT"),
        ("redemption_mode", "TEXT NOT NULL DEFAULT 'coins'"),
        ("fulfillment_mode", "TEXT NOT NULL DEFAULT 'immediate'"),
        ("fragment_target_count", "INTEGER NOT NULL DEFAULT 1"),
        ("fragment_rule_version", "INTEGER NOT NULL DEFAULT 1"),
    ):
        try:
            conn.execute(f"ALTER TABLE server_rewards ADD COLUMN {column} {ddl}")
        except Exception:
            pass
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_server_reward_inventory "
        "ON server_reward_ledger(user_id, source_type, target_date)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS server_backpack_events (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, ledger_id TEXT NOT NULL,
            event_type TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id))"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_backpack_events_user ON server_backpack_events(user_id, created_at)")
    # 碎片活动没有完整物品流水，额外保存关联奖励、碎片和可读说明；旧记录保持兼容。
    for column, ddl in (
        ("reward_id", "TEXT"),
        ("fragment_id", "TEXT"),
        ("quantity", "INTEGER NOT NULL DEFAULT 1"),
        ("detail", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE server_backpack_events ADD COLUMN {column} {ddl}")
        except Exception:
            pass
    # 旧单分类目标和旧前缀解锁记录一次性映射到新模型；INSERT OR IGNORE 保证重复启动安全。
    conn.execute(
        """
        INSERT OR IGNORE INTO server_goal_category_bindings
            (id, user_id, goal_id, category_id, created_at, updated_at)
        SELECT
            'goal-category:' || g.id || ':' || g.category_id,
            g.user_id, g.id, g.category_id,
            COALESCE(g.created_at, datetime('now', 'localtime')),
            COALESCE(g.updated_at, g.created_at, datetime('now', 'localtime'))
        FROM server_goals g
        WHERE g.category_id IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE server_rewards
        SET unlock_source_type = CASE
                WHEN unlock_task_id LIKE 'goal_%' THEN 'goal'
                WHEN unlock_task_id IS NOT NULL AND unlock_task_id <> '' THEN 'checklist_task'
                ELSE NULL
            END,
            unlock_source_id = CASE
                WHEN unlock_task_id LIKE 'goal_%' THEN substr(unlock_task_id, 6)
                WHEN unlock_task_id IS NOT NULL AND unlock_task_id <> '' THEN unlock_task_id
                ELSE NULL
            END
        WHERE unlock_source_type IS NULL
          AND unlock_task_id IS NOT NULL
          AND unlock_task_id <> ''
        """
    )
    conn.execute("UPDATE server_rewards SET inventory_mode='unlimited', inventory_limit=NULL WHERE inventory_mode='weekly'")
    conn.execute(
        """
        UPDATE server_rewards
        SET fulfillment_mode=CASE WHEN unlock_source_type IS NOT NULL AND unlock_source_id IS NOT NULL THEN 'fragment' ELSE 'immediate' END,
            fragment_target_count=CASE WHEN unlock_source_type='habit' THEN MAX(1, COALESCE(unlock_required_count, 1)) ELSE 1 END,
            fragment_rule_version=COALESCE(fragment_rule_version, 1)
        WHERE unlock_source_type IS NOT NULL AND unlock_source_id IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE server_rewards
        SET redemption_mode = CASE
            WHEN unlock_source_type = 'goal' THEN 'goal'
            WHEN unlock_source_type IS NOT NULL OR unlock_task_id IS NOT NULL THEN 'task'
            ELSE 'coins'
        END
        WHERE redemption_mode IS NULL OR redemption_mode = ''
        """
    )
    # 旧商品上的单来源字段迁入独立绑定表。保留历史列以便旧端读取，但新模型不再写入它们。
    conn.execute(
        """INSERT OR IGNORE INTO server_reward_source_bindings
              (id,user_id,reward_id,source_type,source_id,created_at,updated_at)
           SELECT 'reward-source:' || id || ':' || unlock_source_type || ':' || unlock_source_id,
                  user_id,id,unlock_source_type,unlock_source_id,
                  COALESCE(created_at, datetime('now','localtime')),
                  COALESCE(updated_at, created_at, datetime('now','localtime'))
             FROM server_rewards
            WHERE unlock_source_type IN ('checklist_task','habit','learning_task','learning_objective','exercise_checkin')
              AND unlock_source_id IS NOT NULL AND unlock_source_id<>''"""
    )
    conn.execute("DROP INDEX IF EXISTS uq_server_rewards_active_source")
    conn.execute(
        """UPDATE server_rewards
           SET unlock_task_id=NULL,unlock_task_title=NULL,unlock_source_type=NULL,unlock_source_id=NULL,
               unlock_required_count=1,unlock_threshold_started_at=NULL,
               redemption_mode=CASE WHEN fulfillment_mode='fragment' THEN 'task' ELSE redemption_mode END
         WHERE unlock_source_type IS NOT NULL OR unlock_source_id IS NOT NULL OR unlock_task_id IS NOT NULL"""
    )
    for table, columns in {
        "server_reward_ledger": [("occurred_at", "TEXT")],
        "server_exercise_daily_logs": [
            ("plan_version", "TEXT NOT NULL DEFAULT 'v0'"),
            ("week_num", "INTEGER DEFAULT 1"),
            ("day_name", "TEXT"),
            ("weight", "REAL"),
            ("body_fat_rate", "REAL"),
            ("completed_items", "INTEGER DEFAULT 0"),
            ("total_items", "INTEGER DEFAULT 0"),
            ("exercise_variant", "TEXT NOT NULL DEFAULT 'gym'"),
            ("score_snapshot", "TEXT"),
            ("locked_at", "TEXT"),
        ],
        "server_exercise_plan_items": [("plan_version", "TEXT NOT NULL DEFAULT 'v0'")],
        "server_exercise_plan_versions": [("exercise_points", "INTEGER")],
        "server_exercise_item_scores": [
            ("earned_points", "REAL NOT NULL DEFAULT 0"), ("max_points", "REAL NOT NULL DEFAULT 0"),
            ("difficulty", "TEXT"), ("score_rule_version", "TEXT NOT NULL DEFAULT 'v1'"),
            ("score_reason", "TEXT"), ("score_scope", "TEXT NOT NULL DEFAULT 'schedule'"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
        ],
        "server_exercise_settlements": [
            ("score_snapshot", "TEXT"), ("score_total", "REAL NOT NULL DEFAULT 0"),
            ("category_scores", "TEXT"), ("completed_items", "INTEGER NOT NULL DEFAULT 0"),
            ("total_items", "INTEGER NOT NULL DEFAULT 0"), ("settlement_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("reason_code", "TEXT"), ("rule_version", "TEXT NOT NULL DEFAULT 'v1'"),
            ("coin_amount", "REAL NOT NULL DEFAULT 0"), ("occurred_at", "TEXT"),
            ("is_all_complete", "INTEGER NOT NULL DEFAULT 0"),
            ("completion_reward_amount", "REAL NOT NULL DEFAULT 0"), ("completion_reason", "TEXT"),
        ],
    }.items():
        for column, ddl in columns:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            except Exception:
                pass
    _migrate_exercise_daily_logs_unique(conn)
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_server_exercise_daily_logs_user_date_plan_type "
            "ON server_exercise_daily_logs(user_id, date, plan_version, exercise_type)"
        )
    except Exception:
        pass

    # 21. 学习核心目标
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_learning_objectives (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            status INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    # 22. 学习关键结果
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_learning_krs (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            objective_id TEXT NOT NULL,
            title TEXT NOT NULL,
            target_value INTEGER NOT NULL DEFAULT 100,
            current_value INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(objective_id) REFERENCES server_learning_objectives(id)
        )
        """
    )

    # 23. 学习拆解子任务
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_learning_tasks (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            kr_id TEXT NOT NULL,
            title TEXT NOT NULL,
            status INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            pushed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(kr_id) REFERENCES server_learning_krs(id)
        )
        """
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS server_learning_checklist_links (
            user_id INTEGER NOT NULL, learning_task_id TEXT NOT NULL, checklist_task_id TEXT NOT NULL,
            completed_at TEXT, created_at TEXT NOT NULL,
            PRIMARY KEY(user_id, learning_task_id, checklist_task_id)
        )"""
    )

    # 24. 跨端用户级当前计时（不进入普通同步游标）
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS live_timer_lease (
            user_id INTEGER PRIMARY KEY,             -- 所属用户ID（每用户唯一当前状态）
            session_id TEXT NOT NULL UNIQUE,         -- 跨端计时会话UUID
            owner_device_id TEXT NOT NULL,           -- 最近操作设备，仅诊断，不是所有权
            category_id INTEGER,                     -- 当前分类ID
            category_name TEXT NOT NULL,             -- 当前分类名称
            current_note TEXT NOT NULL DEFAULT '',    -- 当前计时备注
            state TEXT NOT NULL,                     -- running/paused/stopped
            started_at TEXT NOT NULL,                -- 服务端接受的开始时间
            segment_started_at TEXT,                 -- 当前运行段服务端开始时间
            active_elapsed_ms INTEGER NOT NULL DEFAULT 0, -- 已累计有效毫秒
            timer_mode TEXT NOT NULL DEFAULT 'countup', -- countup/countdown
            duration_ms INTEGER NOT NULL DEFAULT 0,   -- countdown 总时长
            pause_count INTEGER NOT NULL DEFAULT 0,   -- 权威暂停次数
            revision INTEGER NOT NULL DEFAULT 1,     -- 服务端单调递增版本
            last_command_seq INTEGER NOT NULL DEFAULT 0, -- 来源设备命令序号
            last_idempotency_key TEXT NOT NULL,      -- 最近成功命令幂等键
            last_user_intent_id TEXT,                -- 最近前台用户意图
            last_heartbeat_at TEXT NOT NULL,         -- 最近心跳时间
            updated_at TEXT NOT NULL,                -- 服务端最后更新时间
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS live_timer_commands (
            user_id INTEGER NOT NULL,                -- 所属用户ID
            idempotency_key TEXT NOT NULL,           -- 命令幂等键
            user_intent_id TEXT,                     -- 同一次用户意图（允许 stale 后重试）
            session_id TEXT NOT NULL,                -- 计时会话UUID
            command TEXT NOT NULL,                   -- acquire/switch/state/release/recover
            revision INTEGER NOT NULL,               -- 命令处理后的版本
            result_json TEXT NOT NULL,               -- 脱敏确定结果
            created_at TEXT NOT NULL,                -- 服务端处理时间
            PRIMARY KEY(user_id, idempotency_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS live_timer_segments (
            segment_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            category_id INTEGER,
            category_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            active_elapsed_ms INTEGER NOT NULL DEFAULT 0,
            end_revision INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS live_timer_audit (
            event_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, session_id TEXT NOT NULL,
            event_type TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_user_behavior_events (
            event_id TEXT NOT NULL, user_id INTEGER NOT NULL,
            occurred_at TEXT NOT NULL, received_at TEXT NOT NULL,
            device_id TEXT NOT NULL, runtime TEXT NOT NULL, page TEXT NOT NULL,
            event_type TEXT NOT NULL, action TEXT NOT NULL, target_type TEXT,
            target_id TEXT, result TEXT NOT NULL, error_code TEXT,
            trace_id TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(user_id, event_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    for column_sql in [
        "ALTER TABLE server_sleep_jobs ADD COLUMN image_hash TEXT",
        "ALTER TABLE server_study_sessions ADD COLUMN net_duration_seconds INTEGER",
        "ALTER TABLE server_sync_state ADD COLUMN diagnostics_json TEXT",
        "ALTER TABLE server_change_log ADD COLUMN server_version INTEGER",
        "ALTER TABLE server_change_log ADD COLUMN entity_type TEXT",
        "ALTER TABLE server_change_log ADD COLUMN entity_id TEXT",
        "ALTER TABLE server_change_log ADD COLUMN changed_fields_json TEXT",
        "ALTER TABLE server_change_log ADD COLUMN changed_at TEXT",
        "ALTER TABLE server_sync_conflicts ADD COLUMN client_base_version INTEGER",
        "ALTER TABLE server_sync_conflicts ADD COLUMN server_version INTEGER",
        "ALTER TABLE server_sync_conflicts ADD COLUMN strategy TEXT",
        "ALTER TABLE server_sync_conflicts ADD COLUMN result TEXT",
        "ALTER TABLE live_timer_lease ADD COLUMN segment_started_at TEXT",
        "ALTER TABLE live_timer_lease ADD COLUMN timer_mode TEXT NOT NULL DEFAULT 'countup'",
        "ALTER TABLE live_timer_lease ADD COLUMN duration_ms INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE live_timer_lease ADD COLUMN pause_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE live_timer_lease ADD COLUMN last_user_intent_id TEXT",
        "ALTER TABLE live_timer_lease ADD COLUMN current_note TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE live_timer_commands ADD COLUMN user_intent_id TEXT",
    ]:
        try:
            conn.execute(column_sql)
        except Exception:
            pass

    # 索引优化。旧库必须先补齐兼容列，再创建依赖新列的索引。
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sleep_jobs_user_hash_status ON server_sleep_jobs(user_id, image_hash, status, updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sleep_jobs_user_date_status ON server_sleep_jobs(user_id, date, status, updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON server_study_sessions(user_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON server_tasks(user_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_habits_user ON server_habits(user_id, is_active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_checkins_date ON server_habit_checkins(user_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_user ON server_reward_ledger(user_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_atm_summary_user ON server_atm_summary(user_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_atm_activities_user ON server_atm_activities(user_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_state_user ON server_sync_state(user_id, system, direction)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_change_log_user_change ON server_change_log(user_id, change_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_change_log_user_version ON server_change_log(user_id, server_version)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_change_log_user_record_version ON server_change_log(user_id, table_name, record_id, server_version)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_change_log_entity ON server_change_log(user_id, entity_type, entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_conflicts_user_record ON server_sync_conflicts(user_id, table_name, record_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_live_timer_commands_user_session ON live_timer_commands(user_id, session_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_live_timer_audit_user_session ON live_timer_audit(user_id, session_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_behavior_events_user_time ON server_user_behavior_events(user_id, occurred_at DESC, event_id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_behavior_events_user_trace ON server_user_behavior_events(user_id, trace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_live_timer_segments_user_session ON live_timer_segments(user_id, session_id, created_at)")
    conn.execute(
        "UPDATE live_timer_lease SET segment_started_at=started_at "
        "WHERE state='running' AND segment_started_at IS NULL"
    )

    try:
        conn.execute("PRAGMA writable_schema = ON")
        conn.execute("UPDATE sqlite_master SET sql = replace(sql, '是否激活（1=是,0=否）', '是否归档（1归档,0未归档，正常显示）') WHERE type='table' AND name='server_habits'")
        conn.execute("PRAGMA writable_schema = OFF")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE server_tasks ADD COLUMN deleted_at TEXT DEFAULT NULL")
    except Exception:
        pass
    for column_sql in [
        "ALTER TABLE server_tasks ADD COLUMN source_etag TEXT",
        "ALTER TABLE server_tasks ADD COLUMN source_modified_time TEXT",
        "ALTER TABLE server_tasks ADD COLUMN source TEXT NOT NULL DEFAULT 'ticktick'",
        "ALTER TABLE server_habits ADD COLUMN raw_json TEXT",
        "ALTER TABLE server_habits ADD COLUMN source_etag TEXT",
        "ALTER TABLE server_habits ADD COLUMN source_modified_time TEXT",
        "ALTER TABLE server_habits ADD COLUMN source TEXT NOT NULL DEFAULT 'ticktick'",
        "ALTER TABLE server_habit_checkins ADD COLUMN raw_json TEXT",
        "ALTER TABLE server_habit_checkins ADD COLUMN source_modified_time TEXT",
    ]:
        try:
            conn.execute(column_sql)
        except Exception:
            pass

    # 补丁：给 server_habits 表添加 repeat_rule 字段
    try:
        conn.execute("SELECT repeat_rule FROM server_habits LIMIT 0")
    except Exception:
        try:
            conn.execute("ALTER TABLE server_habits ADD COLUMN repeat_rule TEXT DEFAULT NULL")
        except Exception:
            pass

    # 补丁：平滑物理删除冗余列（如果存在于旧表里）
    for col in ["project_id", "project_name"]:
        try:
            conn.execute(f"ALTER TABLE server_tasks DROP COLUMN {col}")
        except Exception:
            pass
    try:
        conn.execute("ALTER TABLE server_habits DROP COLUMN frequency")
    except Exception:
        pass

    # 补丁：修复 server_habit_checkins 外键错误地引用到 old_server_habits 的问题
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='server_habit_checkins'").fetchone()
        if row and "old_server_habits" in row[0]:
            conn.execute("ALTER TABLE server_habit_checkins RENAME TO _server_habit_checkins_temp")
            conn.execute("""
                CREATE TABLE server_habit_checkins (
                    id TEXT PRIMARY KEY,                  -- 打卡记录主键（UUID）
                    user_id INTEGER NOT NULL,             -- 所属用户ID
                    habit_id TEXT NOT NULL,               -- 关联习惯ID
                    date TEXT,                            -- 日期（兼容旧字段）
                    created_at TEXT,                      -- 创建时间
                    checkin_date TEXT,                    -- 打卡日期（YYYY-MM-DD）
                    checkin_time TEXT,                    -- 打卡时间
                    status INTEGER DEFAULT 0,             -- 打卡状态（2=已打卡, 1=打卡失败, 0=未打卡）
                    note TEXT,                            -- 打卡备注
                    raw_json TEXT,                        -- 滴答清单原始打卡数据快照（完整JSON）
                    source_modified_time TEXT,            -- 滴答清单 opTime 指纹（用于增量筛选）
                    updated_at TEXT NOT NULL,             -- 最后更新时间
                    pushed_at TEXT DEFAULT NULL,          -- 最后推送时间（NULL=待推送）
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (habit_id) REFERENCES server_habits(id),
                    UNIQUE(user_id, habit_id, checkin_date)
                )
            """)
            conn.execute("""
                INSERT INTO server_habit_checkins
                SELECT id, user_id, habit_id, date, created_at, checkin_date, checkin_time, status, note, NULL, NULL, updated_at, pushed_at
                FROM _server_habit_checkins_temp
            """)
            conn.execute("DROP TABLE _server_habit_checkins_temp")
    except Exception:
        pass

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_ticktick_task_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            request_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            task_id TEXT,
            project_id TEXT,
            title_fingerprint TEXT,
            expected_fingerprint TEXT,
            patch_fingerprint TEXT,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            result_task_id TEXT,
            http_status INTEGER,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT,
            UNIQUE(user_id, request_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticktick_task_operations_status "
        "ON server_ticktick_task_operations(user_id, status, updated_at)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_habit_checkin_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL,
            habit_id TEXT NOT NULL,
            checkin_date TEXT NOT NULL,
            desired_status INTEGER NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            error_code TEXT,
            provider_confirmed_at TEXT,
            confirmed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, idempotency_key),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_habit_checkin_commands_status "
        "ON server_habit_checkin_commands(user_id, status, updated_at)"
    )
    operation_columns = {row[1] for row in conn.execute("PRAGMA table_info(server_ticktick_task_operations)").fetchall()}
    for name in ("title_fingerprint", "expected_fingerprint", "patch_fingerprint"):
        if name not in operation_columns:
            conn.execute(f"ALTER TABLE server_ticktick_task_operations ADD COLUMN {name} TEXT")

    # 补丁：清理废弃的服务端系统配置项
    try:
        conn.execute("DELETE FROM server_system_config WHERE key IN ('mysql_config', 'server_sleep_sync')")
        conn.commit()
    except Exception:
        pass

    # 补丁：为 server_habit_checkins 添加 habit_name 字段
    try:
        conn.execute("SELECT habit_name FROM server_habit_checkins LIMIT 0")
    except Exception:
        try:
            conn.execute("ALTER TABLE server_habit_checkins ADD COLUMN habit_name TEXT DEFAULT NULL")
            conn.commit()
        except Exception:
            pass

    # 补丁：为旧版 server_external_rewards 补齐 ext_id 及同步字段
    try:
        conn.execute("ALTER TABLE server_external_rewards ADD COLUMN ext_id TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE server_external_rewards ADD COLUMN pushed_at TEXT DEFAULT NULL")
    except Exception:
        pass
    try:
        conn.execute("UPDATE server_external_rewards SET ext_id = id WHERE ext_id IS NULL OR ext_id = ''")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_server_external_rewards_user_ext "
            "ON server_external_rewards(user_id, ext_id)"
        )
        conn.commit()
    except Exception:
        pass

    # 兼容迁移只建立统一配置；日期变更必须由用户确认后走原子重建，启动时不得删账。
    try:
        users = conn.execute("SELECT id FROM users").fetchall()
        for u in users:
            uid = u[0]
            config_row = conn.execute(
                "SELECT value FROM server_system_config WHERE user_id = ? AND key = ?",
                (uid, "checklist_sync_start_date"),
            ).fetchone()
            start = resolve_statistics_start_date(config_row[0] if config_row else None)
            conn.execute(
                """INSERT INTO server_system_config(user_id,key,value,value_type,description,updated_at)
                   VALUES (?, 'statistics_start_date', ?, 'string', '金币统计起始日期', datetime('now','localtime'))
                   ON CONFLICT(user_id,key) DO NOTHING""",
                (uid, start.date),
            )
        conn.commit()
    except Exception:
        pass

    # 补丁：为 server_categories 添加 sort_order 字段（CHG-20260610-003）
    try:
        conn.execute("SELECT sort_order FROM server_categories LIMIT 0")
    except Exception:
        try:
            conn.execute("ALTER TABLE server_categories ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            # 为现有分类按 id 顺序分配 sort_order
            rows = conn.execute("SELECT id FROM server_categories ORDER BY id ASC").fetchall()
            for idx, row in enumerate(rows, start=1):
                conn.execute("UPDATE server_categories SET sort_order = ? WHERE id = ?", (idx, row[0]))
            conn.commit()
        except Exception:
            pass

    # AI 管理方案：临时草案/应用记录与长期版本资产。所有表均按用户隔离，
    # manifest 只保存方案定义，不保存流水、钱包或其他运行事实。
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_management_plan_drafts (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            request_text TEXT NOT NULL,
            context_version TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            plan_digest TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_management_plan_applications (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            draft_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            plan_digest TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (draft_id) REFERENCES server_management_plan_drafts(id),
            UNIQUE(user_id, idempotency_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_management_plans (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plan_key TEXT NOT NULL,
            title TEXT NOT NULL,
            active_revision_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, plan_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_management_plan_revisions (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            revision_kind TEXT NOT NULL,
            parent_revision_id TEXT,
            manifest_json TEXT NOT NULL,
            manifest_digest TEXT NOT NULL,
            approval_status TEXT NOT NULL DEFAULT 'draft',
            reason TEXT,
            created_at TEXT NOT NULL,
            published_at TEXT,
            FOREIGN KEY (plan_id) REFERENCES server_management_plans(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (parent_revision_id) REFERENCES server_management_plan_revisions(id),
            UNIQUE(plan_id, version),
            UNIQUE(plan_id, manifest_digest)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_management_plan_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            logical_key TEXT NOT NULL,
            domain_type TEXT NOT NULL,
            record_id TEXT,
            provider TEXT,
            provider_id TEXT,
            match_method TEXT,
            binding_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (revision_id) REFERENCES server_management_plan_revisions(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(revision_id, logical_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_management_plan_change_log (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            revision_id TEXT,
            user_id INTEGER NOT NULL,
            actor_type TEXT NOT NULL,
            actor_id TEXT,
            request_summary TEXT,
            reason TEXT,
            change_type TEXT NOT NULL,
            logical_key TEXT,
            before_json TEXT,
            after_json TEXT,
            application_result TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (plan_id) REFERENCES server_management_plans(id),
            FOREIGN KEY (revision_id) REFERENCES server_management_plan_revisions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mgmt_drafts_user_status ON server_management_plan_drafts(user_id, status, expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mgmt_revisions_user_plan ON server_management_plan_revisions(user_id, plan_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mgmt_bindings_user_key ON server_management_plan_bindings(user_id, logical_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mgmt_change_log_user_plan ON server_management_plan_change_log(user_id, plan_id, created_at)")
    conn.execute("""CREATE TABLE IF NOT EXISTS server_management_object_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        domain_type TEXT NOT NULL, record_id TEXT NOT NULL, logical_key TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, domain_type, record_id), UNIQUE(user_id, logical_key)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mgmt_object_keys_user_domain ON server_management_object_keys(user_id, domain_type, record_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS server_flash_cards (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            occurred_at TEXT NOT NULL,
            original_text TEXT NOT NULL,
            polished_text TEXT,
            diary_mood TEXT,
            diary_content TEXT,
            task_recommendations_json TEXT,
            analysis_error_code TEXT,
            analysis_status TEXT NOT NULL DEFAULT 'pending',
            analysis_draft_id TEXT,
            deleted_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_cards_user_time ON server_flash_cards(user_id, occurred_at DESC)")
    _ensure_columns(conn, "server_flash_cards", {"diary_mood": "TEXT", "diary_content": "TEXT",
                                                  "task_recommendations_json": "TEXT", "analysis_error_code": "TEXT"})
    conn.execute("""CREATE TABLE IF NOT EXISTS server_flash_task_recommendations (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, flash_card_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL, title TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','added','ignored')),
        creation_mode TEXT NOT NULL DEFAULT 'confirm' CHECK(creation_mode IN ('direct','confirm')),
        local_task_id TEXT, creation_idempotency_key TEXT,
        provider_task_id TEXT, ignored_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(flash_card_id) REFERENCES server_flash_cards(id),
        UNIQUE(user_id, flash_card_id, ordinal)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_recommendations_user_card ON server_flash_task_recommendations(user_id, flash_card_id, ordinal)")
    _ensure_columns(conn, "server_flash_task_recommendations", {
        "superseded_at": "TEXT", "creation_mode": "TEXT NOT NULL DEFAULT 'confirm'",
        "local_task_id": "TEXT", "creation_idempotency_key": "TEXT",
    })
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_flash_recommendations_user_creation_key ON server_flash_task_recommendations(user_id, creation_idempotency_key) WHERE creation_idempotency_key IS NOT NULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS server_flash_classification_feedback (
        user_id INTEGER NOT NULL, flash_card_id TEXT NOT NULL,
        label TEXT NOT NULL CHECK(label IN ('todo','mood')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(user_id, flash_card_id),
        FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(flash_card_id) REFERENCES server_flash_cards(id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_feedback_user_updated ON server_flash_classification_feedback(user_id, updated_at DESC)")
    conn.execute("""CREATE TABLE IF NOT EXISTS server_flash_feedback_reanalysis_runs (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, flash_card_id TEXT NOT NULL, label TEXT NOT NULL CHECK(label IN ('todo','mood')),
        skill_version TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','done','failed')),
        error_code TEXT, created_at TEXT NOT NULL, completed_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(flash_card_id) REFERENCES server_flash_cards(id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_feedback_runs_user_card ON server_flash_feedback_reanalysis_runs(user_id, flash_card_id, created_at DESC)")
    conn.execute("""CREATE TABLE IF NOT EXISTS server_flash_skill_candidates (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, version TEXT NOT NULL, content TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','passed','failed','active')), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS server_flash_skill_evaluations (
          id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, candidate_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('passed','failed')),
          summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(candidate_id) REFERENCES server_flash_skill_candidates(id)
      )""")
    _ensure_columns(conn, "server_flash_skill_evaluations", {"user_id": "INTEGER"})
    conn.execute(
        """UPDATE server_flash_skill_evaluations SET user_id=(
               SELECT user_id FROM server_flash_skill_candidates c
               WHERE c.id=server_flash_skill_evaluations.candidate_id
           ) WHERE user_id IS NULL"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_skill_evaluations_user_candidate ON server_flash_skill_evaluations(user_id, candidate_id, created_at DESC)")
    conn.execute("""CREATE TABLE IF NOT EXISTS server_flash_polish_corrections (
        id TEXT PRIMARY KEY, request_id TEXT NOT NULL, user_id INTEGER NOT NULL, flash_card_id TEXT NOT NULL,
        original_text_snapshot TEXT NOT NULL, previous_polished_text TEXT, corrected_polished_text TEXT NOT NULL,
        skill_version TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(flash_card_id) REFERENCES server_flash_cards(id)
    )""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_flash_polish_correction_request ON server_flash_polish_corrections(user_id, request_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_polish_correction_card ON server_flash_polish_corrections(user_id, flash_card_id, created_at DESC)")
    conn.execute("""CREATE TABLE IF NOT EXISTS server_flash_skill_change_events (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, candidate_id TEXT, version TEXT NOT NULL,
        parent_version TEXT, event_type TEXT NOT NULL CHECK(event_type IN ('candidate_created','evaluated','activated','failed','rolled_back')),
        rule_diff_json TEXT NOT NULL DEFAULT '{}', sample_summary_json TEXT NOT NULL DEFAULT '{}',
        evaluation_summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(candidate_id) REFERENCES server_flash_skill_candidates(id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_skill_events_history ON server_flash_skill_change_events(user_id, created_at DESC, id DESC)")
    conn.execute("""CREATE TABLE IF NOT EXISTS server_flash_processing_logs (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, flash_card_id TEXT NOT NULL,
        input_text TEXT NOT NULL, prompt_snapshot TEXT NOT NULL, prompt_version TEXT NOT NULL,
        raw_output TEXT, normalized_output TEXT, status TEXT NOT NULL, error_code TEXT,
        started_at TEXT NOT NULL, completed_at TEXT, deleted_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (flash_card_id) REFERENCES server_flash_cards(id))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flash_processing_logs_user_card ON server_flash_processing_logs(user_id, flash_card_id, started_at DESC)")

    # 学习模型兼容字段：客户端已有这些配置字段，服务端旧库需幂等补齐。
    _ensure_columns(conn, "server_learning_objectives", {
        "duration": "INTEGER", "baseline": "TEXT", "target_description": "TEXT",
    })
    _ensure_columns(conn, "server_learning_tasks", {
        "category_id": "INTEGER", "priority": "INTEGER DEFAULT 0", "reward": "REAL DEFAULT 0", "due_date": "TEXT",
    })
    migrate_provider_mirror_identity(conn)
