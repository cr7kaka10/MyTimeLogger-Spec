import { DEFAULT_CATEGORY_ATM_ICONS, LEGACY_CATEGORY_ICONS } from '../core/CategoryIconKey'
import { clientSyncTables } from '../core/SyncEntities'
import { LEARNING_SEED_OBJECTIVE } from './LearningSampleDataInitializer'
// @ts-ignore JSON metadata is shared with the Python initializers.
import timerCategoryContract from '../../shared/protocol/default-timer-categories.json'

/** 数据库 Schema — 从 app/models/schema.py export const SCHEMA_VERSION = 9 */

export const SCHEMA_VERSION = 11

const DEFAULT_TIMER_CATEGORIES = (timerCategoryContract as { categories: Array<{
  name: string; icon: string; color: string; group_name: string; sort_order: number
}> }).categories.map(item => ({ ...item, group: item.group_name, sortOrder: item.sort_order, isActive: 1 }))

const DEFAULT_LEARNING_OBJECTIVE = LEARNING_SEED_OBJECTIVE

/** 14 张表 DDL，按外键依赖顺序排列 */
export const DDL_STATEMENTS: string[] = [
  // 1. 时间分类
  `CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT, -- 分类自增ID
    name        TEXT NOT NULL,                    -- 分类名称
    icon        TEXT NOT NULL DEFAULT '📖',       -- 分类图标
    color       TEXT NOT NULL DEFAULT '#5E81AC',  -- 分类颜色HEX值
    group_name  TEXT NOT NULL DEFAULT '输入',      -- 分类分组名称(例如：输入/产出)
    sort_order  INTEGER NOT NULL DEFAULT 0,       -- 排序权重值
    is_active   INTEGER NOT NULL DEFAULT 1,       -- 软删除标记(1启用,0已删除)
    created_at  TEXT NOT NULL,                    -- 创建时间戳
    updated_at  TEXT,                             -- 最后修改时间戳
    pushed_at   TEXT                              -- 服务端同步时间戳
  )`,

  // 2. 专注会话 (🔴 TEXT UUID)
  `CREATE TABLE IF NOT EXISTS study_sessions (
    id TEXT PRIMARY KEY,                          -- 会话唯一UUID
    start_time TEXT NOT NULL,                     -- 专注开始时间
    end_time TEXT NOT NULL,                       -- 专注结束时间
    net_duration_minutes REAL NOT NULL,           -- 扣除暂停后的净专注分钟数
    net_duration_seconds INTEGER,                 -- 扣除暂停后的净专注秒数
    date TEXT NOT NULL,                           -- 专注日期(YYYY-MM-DD)
    day_of_week TEXT,                             -- 星期几
    pause_count INTEGER DEFAULT 0,                -- 暂停次数
    pause_reasons TEXT,                           -- 暂停原因(逗号分隔)
    session_summary TEXT,                         -- 专注总结/日记
    category_id INTEGER DEFAULT NULL,             -- 关联时间分类ID
    updated_at TEXT,                              -- 最后修改时间戳
    pushed_at TEXT                                -- 服务端同步时间戳
  )`,

  // 3. 任务缓存 (🔴 TEXT UUID，移除 ticktick_id，主建直接为滴答ID/UUID)
  `CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,                          -- 任务唯一主键ID (UUID/滴答ID)
    title TEXT NOT NULL,                          -- 任务标题
    priority INTEGER DEFAULT 0,                   -- 优先级 (0=无,1=低,3=中,5=高)
    status INTEGER DEFAULT 0,                     -- 状态 (0=活动中,2=已完成)
    category_id INTEGER DEFAULT NULL,             -- 关联时间分类ID
    due_date TEXT,                                -- 截止日期
    tags TEXT,                                    -- 任务标签JSON数组
    raw_json TEXT,                                -- 滴答清单原始完整JSON数据
    source TEXT NOT NULL DEFAULT 'ticktick',      -- 来源(local/ticktick)
    source_etag TEXT,                             -- 滴答清单 etag 指纹
    source_modified_time TEXT,                    -- 滴答清单 modifiedTime 指纹
    deleted_at TEXT,                              -- 删除墓碑时间戳（NULL=未删除）
    updated_at TEXT,                              -- 最后修改时间戳
    pushed_at TEXT                                -- 服务端同步时间戳
  )`,

  // 4. 习惯定义 (🔴 TEXT UUID，title 重构为 name 并移除 time_start/time_end)
  `CREATE TABLE IF NOT EXISTS habits (
    id TEXT PRIMARY KEY,                          -- 习惯唯一主键ID
    name TEXT NOT NULL,                           -- 习惯名称
    icon TEXT NOT NULL DEFAULT '✅',              -- 习惯图标
    color TEXT NOT NULL DEFAULT '#A3BE8C',        -- 习惯颜色HEX值
    category_id INTEGER DEFAULT NULL,             -- 关联时间分类ID
    sort_order INTEGER NOT NULL DEFAULT 0,        -- 排序权重
    is_active INTEGER NOT NULL DEFAULT 0,         -- 是否归档（1归档,0未归档，正常显示）
    difficulty TEXT DEFAULT 'medium',             -- 习惯难度(trivial/easy/medium/hard)
    repeat_rule TEXT DEFAULT NULL,                -- 重复规则(如一周哪几天，RRULE)
    raw_json TEXT,                                -- 滴答清单原始完整JSON数据
    source TEXT NOT NULL DEFAULT 'ticktick',      -- 来源(local/ticktick)
    source_etag TEXT,                             -- 滴答清单 etag 指纹
    source_modified_time TEXT,                    -- 滴答清单 modifiedTime 指纹
    created_at TEXT NOT NULL,                     -- 习惯创建时间
    updated_at TEXT,                              -- 最后修改时间戳
    pushed_at TEXT                                -- 服务端同步时间戳
  )`,

  // 5. 习惯打卡 (🔴 TEXT UUID，补齐 date 与 created_at)
  `CREATE TABLE IF NOT EXISTS habit_checkins (
    id TEXT PRIMARY KEY,                          -- 打卡记录UUID
    habit_id TEXT NOT NULL,                       -- 关联习惯ID
    habit_name TEXT,                              -- 习惯名称
    date TEXT,                                    -- 打卡日期 (兼容)
    created_at TEXT,                              -- 创建时间
    checkin_date TEXT NOT NULL,                   -- 打卡日期(YYYY-MM-DD)
    checkin_time TEXT,                            -- 打卡具体时间
    status INTEGER DEFAULT 0,                     -- 状态(2=已打卡, 1=打卡失败, 0=未打卡)
    note TEXT,                                    -- 备注/随笔
    raw_json TEXT,                                -- 滴答清单原始打卡JSON数据
    source_modified_time TEXT,                    -- 滴答清单 opTime 指纹
    updated_at TEXT NOT NULL,                     -- 最后修改时间戳
    pushed_at TEXT,                               -- 服务端同步时间戳
    FOREIGN KEY(habit_id) REFERENCES habits(id)
  )`,

  // 6. 目标挑战 (🔴 TEXT UUID)
  `CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,                          -- 目标唯一UUID
    title TEXT NOT NULL,                          -- 目标名称/标题
    category_id INTEGER,                          -- 关联分类ID
    metric TEXT NOT NULL,                         -- 指标类型
    target_value REAL NOT NULL,                   -- 目标数值
    period TEXT NOT NULL,                         -- 目标周期(daily/weekly/monthly)
    reward_coins REAL DEFAULT 0,                  -- 达成奖励金币数
    reward_id TEXT DEFAULT NULL,                  -- 关联绑定的奖品ID
    operator TEXT DEFAULT '>=',                   -- 判定符号(>= / <=)
    penalty_coins REAL DEFAULT 0,                 -- 失败扣减惩罚金币数
    is_active INTEGER DEFAULT 1,                  -- 是否启用
    created_at TEXT NOT NULL,                     -- 创建时间戳
    updated_at TEXT,                              -- 最后修改时间戳
    pushed_at TEXT,                               -- 服务端同步时间戳
    FOREIGN KEY(reward_id) REFERENCES rewards(id)
  )`,
  `CREATE TABLE IF NOT EXISTS goal_category_bindings (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    pushed_at TEXT,
    UNIQUE(goal_id, category_id)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_goal_category_bindings_goal ON goal_category_bindings(goal_id)`,

  // 7. 奖励商品 (🔴 TEXT UUID)
  `CREATE TABLE IF NOT EXISTS rewards (
    id TEXT PRIMARY KEY,                          -- 商品唯一UUID
    title TEXT NOT NULL,                          -- 商品名称
    icon TEXT DEFAULT '🎁',                       -- 商品图标
    price REAL NOT NULL DEFAULT 10,               -- 兑换价格金币数
    redemption_mode TEXT NOT NULL DEFAULT 'coins',
    description TEXT DEFAULT '',                  -- 描述/备注
    unlock_task_id TEXT DEFAULT NULL,             -- 绑定的解锁任务ID
    unlock_task_title TEXT DEFAULT NULL,           -- 解锁任务标题
    unlock_source_type TEXT DEFAULT NULL,
    unlock_source_id TEXT DEFAULT NULL,
    inventory_mode TEXT NOT NULL DEFAULT 'unlimited',
    inventory_limit INTEGER DEFAULT NULL,
    unlock_required_count INTEGER NOT NULL DEFAULT 1,
    unlock_threshold_started_at TEXT DEFAULT NULL,
    fulfillment_mode TEXT NOT NULL DEFAULT 'immediate',
    fragment_target_count INTEGER NOT NULL DEFAULT 1,
    fragment_rule_version INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER DEFAULT 1,                  -- 是否在架(1在架,0下架)
    created_at TEXT NOT NULL,                     -- 商品创建时间
    updated_at TEXT,                              -- 最后修改时间戳
    pushed_at TEXT                                -- 服务端同步时间戳
  )`,

  // 7.1 服务端权威的奖励碎片（客户端只读镜像）
  `CREATE TABLE IF NOT EXISTS reward_fragments (
    id TEXT PRIMARY KEY,
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
    pulled_at TEXT,
    UNIQUE(reward_id, completion_event_key),
    FOREIGN KEY(reward_id) REFERENCES rewards(id)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_reward_fragments_active ON reward_fragments(reward_id, rule_version, status, expires_at)`,

  // 7.2 服务端权威的商品—来源绑定（客户端只读镜像）
  `CREATE TABLE IF NOT EXISTS reward_source_bindings (
    id TEXT PRIMARY KEY,
    reward_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    drop_mode TEXT NOT NULL DEFAULT 'fixed',
    drop_min_units INTEGER,
    drop_max_units INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    pulled_at TEXT,
    UNIQUE(reward_id, source_type, source_id),
    FOREIGN KEY(reward_id) REFERENCES rewards(id)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_reward_source_bindings_source ON reward_source_bindings(source_type, source_id)`,

  // 8. 金币流水 (🔴 TEXT UUID)
  `CREATE TABLE IF NOT EXISTS reward_ledger (
    id          TEXT PRIMARY KEY,                 -- 流水记录UUID
    amount      REAL NOT NULL,                    -- 交易金额(正数为获得,负数为消耗)
    source_type TEXT NOT NULL,                    -- 产生类型(habit_checkin/habit_fail/task_complete/buy_reward等)
    source_id   TEXT,                             -- 产生源关联ID
    description TEXT,                             -- 交易流水描述信息
    target_date TEXT,                             -- 归属打卡日期(YYYY-MM-DD)
    occurred_at  TEXT,                            -- 业务实际发生时间（北京时间，可为空）
    created_at  TEXT NOT NULL,                    -- 流水生成时间戳
    updated_at  TEXT NOT NULL,                    -- 最后修改时间戳
    pushed_at   TEXT                              -- 服务端同步时间戳
  )`,

  // 8.1 用户钱包快照（服务端权威）
  `CREATE TABLE IF NOT EXISTS user_wallets (
    user_id          INTEGER PRIMARY KEY,          -- 用户ID
    balance          REAL NOT NULL DEFAULT 0.0,    -- 当前金币余额
    last_ledger_uuid TEXT,                         -- 最后一笔流水UUID
    updated_at       TEXT NOT NULL,                -- 最后更新时间戳
    pushed_at        TEXT                          -- 服务端同步时间戳
  )`,

  // 9. 待领取奖励 (🔴 TEXT UUID)
  `CREATE TABLE IF NOT EXISTS external_rewards (
    id TEXT PRIMARY KEY,                          -- 奖励项UUID
    ext_id TEXT NOT NULL,                         -- 外部数据唯一去重ID(如习惯打卡_日期标识)
    item_type TEXT NOT NULL,                      -- 外部项类型(habit/task等)
    item_name TEXT NOT NULL,                      -- 外部项名称描述
    coins REAL NOT NULL DEFAULT 0,                -- 应获金币奖励数
    status INTEGER NOT NULL DEFAULT 0,            -- 领取状态(0未领取,1已领取)
    created_at TEXT NOT NULL,                     -- 外部奖励产生时间
    updated_at TEXT,                              -- 最后更新时间戳
    pushed_at TEXT                                -- 服务端同步时间戳
  )`,

  // 10. 奖惩配置
  `CREATE TABLE IF NOT EXISTS reward_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键ID
    item_type   TEXT NOT NULL,                    -- 奖惩配置对象类型(task/habit等)
    item_id     TEXT NOT NULL,                    -- 对应对象ID
    coins       REAL NOT NULL DEFAULT 0.1,        -- 完成时奖励金币数
    penalty     REAL DEFAULT NULL,                -- 失败扣减金币数
    updated_at  TEXT,                             -- 最后更新时间戳
    pushed_at   TEXT                              -- 服务端同步时间戳
  )`,

  // 11. 华为睡眠数据
  `CREATE TABLE IF NOT EXISTS huawei_sleep_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,         -- 自增流水主键ID
    date TEXT UNIQUE,                             -- 睡眠归属日期(YYYY-MM-DD, UNIQUE)
    sleep_score INTEGER,                          -- 华为睡眠总评分
    total_sleep_min INTEGER,                      -- 睡眠总时长(分钟)
    deep_sleep_min INTEGER,                       -- 深睡时长(分钟)
    light_sleep_min INTEGER,                      -- 浅睡时长(分钟)
    rem_sleep_min INTEGER,                        -- 快速眼动时长(分钟)
    awake_count INTEGER,                          -- 醒来次数
    sleep_start TEXT,                             -- 实际入睡时间
    sleep_end TEXT,                               -- 实际醒来时间
    deep_sleep_ratio INTEGER,                     -- 深睡比例%
    light_sleep_ratio INTEGER,                    -- 浅睡比例%
    rem_sleep_ratio INTEGER,                      -- 快速眼动比例%
    sleep_continuity INTEGER,                     -- 睡眠连续性评分
    breathing_score INTEGER,                      -- 呼吸状况评分
    sleep_cycles FLOAT,                           -- 睡眠循环数
    awake_min INTEGER,                            -- 醒来总时长(分钟)
    fall_asleep_min INTEGER,                      -- 入睡准备时长(分钟)
    wake_up_min INTEGER,                          -- 醒来准备时长(分钟)
      atm_sleep_start TEXT,                         -- aTimeLogger 识别出的参考入睡时间
      atm_sleep_end TEXT,                           -- aTimeLogger 识别出的参考醒来时间
      analysis_report TEXT,                         -- AI 生成的睡眠健康建议报告正文
      analysis_html TEXT,                           -- AI 报告渲染后的 HTML
      official_advice TEXT,                         -- 华为运动健康官方建议原文
      morning_diary TEXT,                           -- 晨间总结/晨记
      evening_diary TEXT,                           -- 晚间复盘/晚记
      morning_diary_written_at TEXT,                -- 晨间日记实际保存时间
      evening_diary_written_at TEXT,                -- 晚间日记实际保存时间
    report_status INTEGER DEFAULT 0,              -- 分析状态标记(0未分析, 1分析中, 2已完成)
    full_report_state TEXT,                       -- 完整报告状态
    tracked_duration_seconds INTEGER,             -- 当天累计记录秒数
    source TEXT DEFAULT 'screenshot_ocr',         -- 睡眠数据来源
    synced_at TEXT,                               -- 外部来源同步时间
    sync_status TEXT DEFAULT 'success',           -- 外部同步状态
    sync_error TEXT,                              -- 外部同步错误信息
    updated_at TEXT,                              -- 最后更新时间戳
    pushed_at TEXT                                -- 服务端同步时间戳
  )`,

  // 12. aTimeLogger 汇总
  `CREATE TABLE IF NOT EXISTS atm_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,         -- 自增主键ID
    date TEXT UNIQUE,                             -- 汇总日期(YYYY-MM-DD, UNIQUE)
    updated_at TEXT,                              -- 最后更新时间戳
    pushed_at TEXT,                               -- 服务端同步时间戳
    pulled_at TEXT                                -- 客户端拉取时间戳
  )`,

  // 13. aTimeLogger 明细
  `CREATE TABLE IF NOT EXISTS atm_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,         -- 自增主键ID
    date TEXT NOT NULL,                           -- 活动日期(YYYY-MM-DD)
    activity_type TEXT NOT NULL,                  -- aTimeLogger 活动类型(工作/娱乐等)
    start_time TEXT NOT NULL,                     -- 活动开始时间戳
    end_time TEXT NOT NULL,                       -- 活动结束时间戳
    duration_minutes INTEGER NOT NULL,            -- 活动持续分钟数
    comment TEXT,                                 -- 备注内容
    updated_at TEXT,                              -- 最后更新时间戳
    pushed_at TEXT,                               -- 服务端同步时间戳
    pulled_at TEXT                                -- 客户端拉取时间戳
  )`,

  // 14. 系统配置
  `CREATE TABLE IF NOT EXISTS system_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,         -- 自增主键ID
    key TEXT NOT NULL UNIQUE,                     -- 配置键名(UNIQUE)
    value TEXT NOT NULL,                          -- 配置文本内容
    value_type TEXT NOT NULL DEFAULT 'string',    -- 配置值类型
    description TEXT,                             -- 配置说明
    updated_at TEXT,                              -- 最后更新时间戳
    pushed_at TEXT                                -- 服务端同步时间戳
  )`,

  // 15. aTimeLogger 备份同步映射
  `CREATE TABLE IF NOT EXISTS atimelogger_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,         -- 自增主键ID
    local_session_id TEXT NOT NULL,               -- 本地 study_sessions.id
    local_segment_key TEXT NOT NULL,              -- 本地分段键(默认 session:<id>)
    local_category_id INTEGER,                    -- 本地分类ID
    atimelogger_type_id TEXT,                     -- aTimeLogger 类型ID
    atimelogger_activity_id TEXT,                 -- aTimeLogger activityId
    atimelogger_interval_id TEXT,                 -- aTimeLogger intervalId
    remote_status TEXT DEFAULT 'pending',         -- 远端状态(pending/running/stopped/deleted)
    sync_state TEXT NOT NULL DEFAULT 'pending_create', -- 同步状态
    last_error TEXT,                              -- 最近一次同步错误
    created_at TEXT NOT NULL,                     -- 创建时间
    updated_at TEXT,                              -- 最后更新时间
    UNIQUE(local_session_id, local_segment_key)
  )`,

  // 索引
  `CREATE INDEX IF NOT EXISTS idx_study_sessions_date ON study_sessions(date)`,
  `CREATE INDEX IF NOT EXISTS idx_huawei_sleep_date ON huawei_sleep_data(date)`,
  `CREATE INDEX IF NOT EXISTS idx_atimelogger_segments_session ON atimelogger_segments(local_session_id)`,
  `CREATE INDEX IF NOT EXISTS idx_atimelogger_segments_remote ON atimelogger_segments(atimelogger_activity_id, atimelogger_interval_id)`,

  // 16. 运动打卡每日总记录
  `CREATE TABLE IF NOT EXISTS exercise_plan_versions (
    version TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    exercise_points INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    pushed_at TEXT
  )`,

  `CREATE TABLE IF NOT EXISTS exercise_daily_logs (
    id TEXT PRIMARY KEY,                          -- 每日记录UUID
    date TEXT NOT NULL,                           -- 记录日期(YYYY-MM-DD)
    plan_version TEXT NOT NULL DEFAULT 'v0',       -- 训练计划版本
    week_num INTEGER NOT NULL,                    -- 第几周
    day_name TEXT NOT NULL,                       -- 星期几/第几天(如: 第一天)
    weight REAL,                                  -- 体重
    body_fat_rate REAL,                           -- 体脂率（百分比）
    completed_items INTEGER NOT NULL DEFAULT 0,   -- 完成子项数
    total_items INTEGER NOT NULL DEFAULT 0,       -- 总子项数
    exercise_variant TEXT NOT NULL DEFAULT 'gym',-- 当日健身房/雨天方案
    score_snapshot TEXT,                          -- 当日评分快照JSON
    locked_at TEXT,                               -- 日终锁分时间
    created_at TEXT NOT NULL,                     -- 创建时间
    updated_at TEXT,                              -- 最后修改时间戳
    pushed_at TEXT,                               -- 服务端同步时间戳
    UNIQUE(date, plan_version)
  )`,

  // 17. 运动微项目打卡明细
  `CREATE TABLE IF NOT EXISTS exercise_checkins (
    id TEXT PRIMARY KEY,                          -- 勾选记录UUID
    date TEXT NOT NULL,                           -- 打卡日期(YYYY-MM-DD)
    plan_version TEXT NOT NULL DEFAULT 'v0',       -- 训练计划版本
    item_key TEXT NOT NULL,                       -- 微项目唯一标识(如: ex-第一天-g-0)
    status INTEGER NOT NULL DEFAULT 0,            -- 状态(1=已打卡, 0=未打卡)
    completed_time TEXT,                          -- 完成时刻(HH:mm，北京时间)
    plan_item_id TEXT,                            -- 稳定运动计划项ID
    item_name TEXT,                               -- 打卡时动作名称快照
    note TEXT,                                    -- 具体打卡内容备注(如吃了什么)
    locked_at TEXT,                               -- 09:00 体重体脂不可逆截止锁时间
    lock_reason TEXT,                             -- 服务端锁定原因
    deadline_penalty_source_id TEXT,              -- 服务端截止处罚稳定来源
    deadline_penalty_amount REAL,                 -- 服务端截止处罚金额
    created_at TEXT NOT NULL,                     -- 创建时间
    updated_at TEXT,                              -- 最后修改时间戳
    pushed_at TEXT,                               -- 服务端同步时间戳
    UNIQUE(date, plan_version, item_key)
  )`,

  `CREATE TABLE IF NOT EXISTS exercise_item_scores (
    id TEXT PRIMARY KEY,
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
    pulled_at TEXT,
    UNIQUE(date, plan_version, item_key)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_exercise_item_scores_date ON exercise_item_scores(date, plan_version)`,

  `CREATE TABLE IF NOT EXISTS exercise_settlements (
    id TEXT PRIMARY KEY,
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
    pulled_at TEXT,
    UNIQUE(business_date, plan_version)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_exercise_settlements_date ON exercise_settlements(business_date, plan_version)`,

  `CREATE TABLE IF NOT EXISTS exercise_diet_checkins (
    id TEXT PRIMARY KEY, date TEXT NOT NULL, plan_version TEXT NOT NULL,
    rule_key TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', occurred_at TEXT,
    deadline_at TEXT NOT NULL, failure_reason TEXT, penalty_source_id TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, pushed_at TEXT,
    UNIQUE(date, plan_version, rule_key)
  )`,

  `CREATE TABLE IF NOT EXISTS exercise_deadline_facts (
    id TEXT PRIMARY KEY, date TEXT NOT NULL, plan_version TEXT NOT NULL,
    fact_type TEXT NOT NULL, status TEXT NOT NULL, deadline_at TEXT NOT NULL,
    reason TEXT, penalty_source_id TEXT, penalty_amount REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(date, plan_version, fact_type)
  )`,

  `CREATE TABLE IF NOT EXISTS exercise_plan_items (
    id TEXT PRIMARY KEY, plan_version TEXT NOT NULL DEFAULT 'v0',
    day_key TEXT NOT NULL, variant TEXT NOT NULL,
    section TEXT NOT NULL, sort_order INTEGER NOT NULL, name TEXT NOT NULL,
    sets TEXT, intensity TEXT, tags_json TEXT, progression TEXT, color TEXT,
    is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
    updated_at TEXT, pushed_at TEXT, UNIQUE(plan_version, day_key, variant, sort_order)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_exercise_plan_day ON exercise_plan_items(plan_version, day_key, variant, is_active, sort_order)`,

  `CREATE TABLE IF NOT EXISTS exercise_plan_schedule_items (
    id TEXT PRIMARY KEY,
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
    UNIQUE(plan_version, schedule_type, sort_order)
  )`,

  `CREATE TABLE IF NOT EXISTS exercise_plan_diet_rules (
    id TEXT PRIMARY KEY,
    plan_version TEXT NOT NULL DEFAULT 'v0',
    rule_key TEXT,
    sort_order INTEGER NOT NULL,
    time TEXT NOT NULL,
    content TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    pushed_at TEXT,
    UNIQUE(plan_version, sort_order)
  )`,

  `CREATE TABLE IF NOT EXISTS exercise_plan_score_rules (
    id TEXT PRIMARY KEY,
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
    UNIQUE(plan_version, day_type, sort_order)
  )`,

  `CREATE TABLE IF NOT EXISTS exercise_plan_category_rules (
    id TEXT PRIMARY KEY,
    plan_version TEXT NOT NULL DEFAULT 'v0',
    sort_order INTEGER NOT NULL,
    category TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    pushed_at TEXT,
    UNIQUE(plan_version, sort_order)
  )`,

  `CREATE TABLE IF NOT EXISTS exercise_plan_progress_items (
    id TEXT PRIMARY KEY,
    plan_version TEXT NOT NULL DEFAULT 'v0',
    sort_order INTEGER NOT NULL,
    when_text TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    pushed_at TEXT,
    UNIQUE(plan_version, sort_order)
  )`,

  // 18. 学习核心目标
  `CREATE TABLE IF NOT EXISTS learning_objectives (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status INTEGER DEFAULT 0,
    duration INTEGER,                             -- 持续天数（可为空）
    baseline TEXT,                                -- 当前现状（可为空）
    target_description TEXT,                      -- 预期目标（可为空）
    created_at TEXT NOT NULL,
    updated_at TEXT,
    pushed_at TEXT
  )`,

  // 19. 学习关键结果
  `CREATE TABLE IF NOT EXISTS learning_krs (
    id TEXT PRIMARY KEY,
    objective_id TEXT NOT NULL,
    title TEXT NOT NULL,
    target_value INTEGER NOT NULL DEFAULT 100,
    current_value INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    pushed_at TEXT,
    FOREIGN KEY(objective_id) REFERENCES learning_objectives(id)
  )`,

  // 20. 学习拆解子任务
  `CREATE TABLE IF NOT EXISTS learning_tasks (
    id TEXT PRIMARY KEY,
    kr_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status INTEGER DEFAULT 0,
    category_id INTEGER,                          -- 关联时间分类ID（可为空）
    priority INTEGER DEFAULT 0,                   -- 优先级（0=无,1=低,3=中,5=高）
    reward INTEGER DEFAULT 0,                     -- 奖励金币值（无惩罚）
    due_date TEXT,                                -- 截止日期（可为空）
    created_at TEXT NOT NULL,
    updated_at TEXT,
    pushed_at TEXT,
    FOREIGN KEY(kr_id) REFERENCES learning_krs(id)
  )`,

  // 20.1 时间书闪念卡片
  `CREATE TABLE IF NOT EXISTS flash_cards (
    id TEXT PRIMARY KEY,
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
    pushed_at TEXT
  )`,

  // 20.1 闪念推荐任务（服务端权威 Pull-only 镜像）
  `CREATE TABLE IF NOT EXISTS flash_task_recommendations (
    id TEXT PRIMARY KEY,
    flash_card_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    title TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    creation_mode TEXT NOT NULL DEFAULT 'confirm',
    local_task_id TEXT,
    creation_idempotency_key TEXT,
    provider_task_id TEXT,
    ignored_at TEXT,
    superseded_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    pulled_at TEXT,
    pushed_at TEXT
  )`,

  // 20.2 管理方案配置
  `CREATE TABLE IF NOT EXISTS management_plans (
    id TEXT PRIMARY KEY,
    plan_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    active_revision_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    pushed_at TEXT
  )`,
  
  `CREATE TABLE IF NOT EXISTS management_plan_revisions (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    config_json TEXT NOT NULL,
    logical_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    pushed_at TEXT,
    FOREIGN KEY(plan_id) REFERENCES management_plans(id)
  )`,

  `CREATE TABLE IF NOT EXISTS sleep_automation_commands (
    id TEXT PRIMARY KEY, sleep_date TEXT NOT NULL, command_type TEXT NOT NULL,
    scheduled_at TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, pulled_at TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS sleep_notifications (
    id TEXT PRIMARY KEY, sleep_date TEXT NOT NULL, event_type TEXT NOT NULL,
    title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, pulled_at TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS sleep_score_settlements (
    id TEXT PRIMARY KEY, sleep_date TEXT NOT NULL, metrics_snapshot TEXT NOT NULL,
    score_breakdown TEXT NOT NULL, score_total INTEGER NOT NULL, reward_amount REAL NOT NULL,
    cycle_penalty REAL NOT NULL, net_amount REAL NOT NULL, settlement_status TEXT NOT NULL,
    missing_fields TEXT NOT NULL, rule_version TEXT NOT NULL, occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, pulled_at TEXT,
    diary_completion_status TEXT NOT NULL DEFAULT 'pending',
    diary_completion_reward_amount REAL NOT NULL DEFAULT 0,
    diary_completion_reason TEXT, diary_completion_rule_version TEXT,
    morning_diary_reward_status TEXT NOT NULL DEFAULT 'pending', morning_diary_reward_amount REAL NOT NULL DEFAULT 0,
    morning_diary_reward_reason TEXT, morning_diary_reward_rule_version TEXT,
    evening_diary_reward_status TEXT NOT NULL DEFAULT 'pending', evening_diary_reward_amount REAL NOT NULL DEFAULT 0,
    evening_diary_reward_reason TEXT, evening_diary_reward_rule_version TEXT,
    bedtime_coin_status TEXT NOT NULL DEFAULT 'pending', bedtime_coin_amount REAL NOT NULL DEFAULT 0,
    bedtime_coin_reason TEXT, bedtime_coin_rule_version TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS sleep_command_receipts (
    id TEXT PRIMARY KEY, device_id TEXT NOT NULL, command_id TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, pulled_at TEXT, pushed_at TEXT, UNIQUE(device_id, command_id)
  )`,
  `CREATE TABLE IF NOT EXISTS sleep_notification_receipts (
    id TEXT PRIMARY KEY, device_id TEXT NOT NULL, notification_id TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, pulled_at TEXT, pushed_at TEXT, UNIQUE(device_id, notification_id)
  )`,

  // 21. 本地同步 outbox
  `CREATE TABLE IF NOT EXISTS sync_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,         -- 本地自增主键
    change_id TEXT NOT NULL UNIQUE,               -- 变更唯一ID
    device_id TEXT NOT NULL,                      -- 客户端设备ID
    table_name TEXT NOT NULL,                     -- 业务表名
    record_id TEXT NOT NULL,                      -- 业务记录ID
    operation TEXT NOT NULL,                      -- 操作类型(upsert/delete/archive)
    base_version TEXT,                            -- 修改前已知服务端版本
    payload_json TEXT NOT NULL,                   -- 变更载荷JSON
    status TEXT NOT NULL DEFAULT 'pending',       -- 同步状态(pending/sending/synced/failed)
    retry_count INTEGER NOT NULL DEFAULT 0,       -- 重试次数
    last_error TEXT,                              -- 最近错误信息
    created_at TEXT NOT NULL,                     -- 创建时间戳
    updated_at TEXT NOT NULL                      -- 最后更新时间戳
  )`,

  // 22. 客户端同步状态（非用户设置）
  `CREATE TABLE IF NOT EXISTS client_sync_state (
    key TEXT PRIMARY KEY,                         -- 状态键名
    value TEXT NOT NULL,                          -- 状态值
    description TEXT,                             -- 状态说明
    updated_at TEXT NOT NULL                      -- 最后更新时间戳
  )`,

  `CREATE TABLE IF NOT EXISTS behavior_event_outbox (
    event_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, device_id TEXT NOT NULL,
    runtime TEXT NOT NULL, page TEXT NOT NULL, event_type TEXT NOT NULL,
    action TEXT NOT NULL, target_type TEXT, target_id TEXT, result TEXT NOT NULL,
    error_code TEXT, trace_id TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
    priority TEXT NOT NULL DEFAULT 'normal', created_at TEXT NOT NULL
  )`
]

// SQLite 适配器接口抽象
export interface SqlDB {
  run(sql: string, params?: any[]): void
  exec(sql: string): void
  prepare?(sql: string): {
    bind(params?: any[]): void
    step(): boolean
    getAsObject(): Record<string, any>
    free(): void
  }
}

function tableColumns(db: SqlDB, table: string): Set<string> | null {
  if (!db.prepare) return null
  const statement = db.prepare(`PRAGMA table_info(${table})`)
  const columns = new Set<string>()
  try {
    while (statement.step()) columns.add(String(statement.getAsObject().name || ''))
  } finally {
    statement.free()
  }
  return columns
}

function addColumnIfMissing(db: SqlDB, table: string, column: string, definition: string): void {
  const columns = tableColumns(db, table)
  if (columns?.has(column)) return
  db.run(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`)
}

function runIgnoreError(db: SqlDB, sql: string, params?: any[]): void {
  const addColumn = sql.trim().match(/^ALTER TABLE\s+([A-Za-z_][\w]*)\s+ADD COLUMN\s+([A-Za-z_][\w]*)\s+(.+)$/i)
  if (addColumn) {
    addColumnIfMissing(db, addColumn[1], addColumn[2], addColumn[3])
    return
  }
  try {
    db.run(sql, params)
  } catch {
    // 索引/种子兼容操作保持幂等；字段迁移的真实错误不得吞掉
  }
}

function markSeedInitializedWhenDataExists(db: SqlDB, key: string, description: string, tableName: string): void {
  runIgnoreError(
    db,
    `INSERT OR IGNORE INTO system_config (key, value, value_type, description, updated_at)
     SELECT ?, '1', 'string', ?, datetime('now','localtime')
     WHERE EXISTS (SELECT 1 FROM ${tableName})`,
    [key, description],
  )
}

function markSeedInitialized(db: SqlDB, key: string, description: string): void {
  runIgnoreError(
    db,
    `INSERT OR IGNORE INTO system_config (key, value, value_type, description, updated_at)
     VALUES (?, '1', 'string', ?, datetime('now','localtime'))`,
    [key, description],
  )
}

function hasMarker(db: SqlDB, key: string): boolean {
  if (!db.prepare) return false
  const stmt = db.prepare("SELECT 1 AS exists_flag FROM system_config WHERE key = ? AND value = '1' LIMIT 1")
  try {
    stmt.bind([key])
    return stmt.step()
  } finally {
    stmt.free()
  }
}

function hasRows(db: SqlDB, tableName: string): boolean {
  if (!db.prepare) return false
  const stmt = db.prepare(`SELECT 1 AS exists_flag FROM ${tableName} LIMIT 1`)
  try {
    return stmt.step()
  } finally {
    stmt.free()
  }
}

const ATM_CACHE_REPAIR_MARKER = 'atm_pull_cache_repair_v1'

function repairAtmPullOnlyCache(db: SqlDB): void {
  if (!db.prepare) return
  const stmt = db.prepare('SELECT 1 FROM client_sync_state WHERE key = ? LIMIT 1')
  try {
    stmt.bind([ATM_CACHE_REPAIR_MARKER])
    if (stmt.step()) return
  } finally {
    stmt.free()
  }
  db.exec('BEGIN IMMEDIATE')
  try {
    db.run('DELETE FROM atm_activities')
    db.run('DELETE FROM atm_summary')
    db.run("INSERT INTO client_sync_state (key,value,description,updated_at) VALUES (?, '1', ?, datetime('now','localtime'))", [
      ATM_CACHE_REPAIR_MARKER, 'ATM pull-only 缓存已完成一次性重建',
    ])
    db.exec('COMMIT')
  } catch (error) {
    try { db.exec('ROLLBACK') } catch { /* preserve original migration failure */ }
    throw error
  }
}

function seedTimerCategoriesOnFirstRun(db: SqlDB): void {
  if (hasMarker(db, 'timer_seed_initialized')) return
  if (hasRows(db, 'categories')) {
    markSeedInitialized(db, 'timer_seed_initialized', '计时页初始示例分类已初始化')
    return
  }
  for (const category of DEFAULT_TIMER_CATEGORIES) {
    runIgnoreError(
      db,
      `INSERT INTO categories (name, icon, color, group_name, sort_order, is_active, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))`,
      [category.name, category.icon, category.color, category.group, category.sortOrder, category.isActive],
    )
  }
  markSeedInitialized(db, 'timer_seed_initialized', '计时页初始示例分类已初始化')
}

function applyCompatibilityMigrations(db: SqlDB): void {
  seedTimerCategoriesOnFirstRun(db)
  Object.entries(DEFAULT_CATEGORY_ATM_ICONS).forEach(([name, icon]) =>
    (LEGACY_CATEGORY_ICONS[name] ?? []).forEach(oldIcon => runIgnoreError(db,
      'UPDATE categories SET icon = ? WHERE name = ? AND icon = ?', [icon, name, oldIcon])))
  runIgnoreError(db, 'ALTER TABLE study_sessions ADD COLUMN net_duration_seconds INTEGER')
  for (const table of clientSyncTables()) {
    runIgnoreError(db, `ALTER TABLE ${table} ADD COLUMN pulled_at TEXT`)
  }
  runIgnoreError(db, "ALTER TABLE external_rewards ADD COLUMN ext_id TEXT")
  runIgnoreError(db, "ALTER TABLE reward_ledger ADD COLUMN occurred_at TEXT")
  runIgnoreError(db, "ALTER TABLE external_rewards ADD COLUMN updated_at TEXT")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN unlock_source_type TEXT")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN unlock_source_id TEXT")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN inventory_mode TEXT NOT NULL DEFAULT 'unlimited'")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN inventory_limit INTEGER")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN unlock_required_count INTEGER NOT NULL DEFAULT 1")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN unlock_threshold_started_at TEXT")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN redemption_mode TEXT NOT NULL DEFAULT 'coins'")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN fulfillment_mode TEXT NOT NULL DEFAULT 'immediate'")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN fragment_target_count INTEGER NOT NULL DEFAULT 1")
  runIgnoreError(db, "ALTER TABLE rewards ADD COLUMN fragment_rule_version INTEGER NOT NULL DEFAULT 1")
  runIgnoreError(db, "ALTER TABLE external_rewards ADD COLUMN pushed_at TEXT")
  runIgnoreError(db, "UPDATE external_rewards SET ext_id = id WHERE ext_id IS NULL OR ext_id = ''")
  runIgnoreError(db, "CREATE UNIQUE INDEX IF NOT EXISTS idx_external_rewards_ext_id ON external_rewards(ext_id)")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN note TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN completed_time TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN plan_item_id TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN item_name TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN plan_version TEXT NOT NULL DEFAULT 'v0'")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN locked_at TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN lock_reason TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN deadline_penalty_source_id TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_checkins ADD COLUMN deadline_penalty_amount REAL")
  runIgnoreError(db, "ALTER TABLE exercise_daily_logs ADD COLUMN plan_version TEXT NOT NULL DEFAULT 'v0'")
  runIgnoreError(db, "ALTER TABLE exercise_daily_logs ADD COLUMN score_snapshot TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_daily_logs ADD COLUMN locked_at TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_daily_logs ADD COLUMN exercise_variant TEXT NOT NULL DEFAULT 'gym'")
  runIgnoreError(db, "ALTER TABLE exercise_daily_logs ADD COLUMN body_fat_rate REAL")
  runIgnoreError(db, "ALTER TABLE exercise_item_scores ADD COLUMN pulled_at TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_item_scores ADD COLUMN score_scope TEXT NOT NULL DEFAULT 'schedule'")
  runIgnoreError(db, "ALTER TABLE exercise_plan_diet_rules ADD COLUMN rule_key TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_diet_checkins ADD COLUMN pushed_at TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_settlements ADD COLUMN pulled_at TEXT")
  runIgnoreError(db, "ALTER TABLE exercise_settlements ADD COLUMN is_all_complete INTEGER NOT NULL DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE exercise_settlements ADD COLUMN completion_reward_amount REAL NOT NULL DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE exercise_settlements ADD COLUMN completion_reason TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN report_completed_at TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN completion_reward_amount REAL NOT NULL DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN is_all_complete INTEGER NOT NULL DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN completion_reason TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN diary_completion_status TEXT NOT NULL DEFAULT 'pending'")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN diary_completion_reward_amount REAL NOT NULL DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN diary_completion_reason TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN diary_completion_rule_version TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN morning_diary_reward_status TEXT NOT NULL DEFAULT 'pending'")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN morning_diary_reward_amount REAL NOT NULL DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN morning_diary_reward_reason TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN morning_diary_reward_rule_version TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN evening_diary_reward_status TEXT NOT NULL DEFAULT 'pending'")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN evening_diary_reward_amount REAL NOT NULL DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN evening_diary_reward_reason TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN evening_diary_reward_rule_version TEXT")
  runIgnoreError(db, "ALTER TABLE reward_fragments ADD COLUMN progress_units INTEGER")
  runIgnoreError(db, "ALTER TABLE reward_fragments ADD COLUMN consumed_units INTEGER")
  runIgnoreError(db, "ALTER TABLE reward_source_bindings ADD COLUMN drop_mode TEXT")
  runIgnoreError(db, "ALTER TABLE reward_source_bindings ADD COLUMN drop_min_units INTEGER")
  runIgnoreError(db, "ALTER TABLE reward_source_bindings ADD COLUMN drop_max_units INTEGER")
  runIgnoreError(db, "UPDATE reward_fragments SET progress_units=100 WHERE progress_units IS NULL")
  runIgnoreError(db, "UPDATE reward_fragments SET consumed_units=0 WHERE consumed_units IS NULL")
  runIgnoreError(db, "ALTER TABLE exercise_plan_items ADD COLUMN plan_version TEXT NOT NULL DEFAULT 'v0'")
  runIgnoreError(db, "ALTER TABLE exercise_plan_versions ADD COLUMN exercise_points INTEGER")
  runIgnoreError(db, "CREATE UNIQUE INDEX IF NOT EXISTS idx_exercise_checkins_version_item ON exercise_checkins(date, plan_version, item_key)")
  runIgnoreError(db, "ALTER TABLE flash_cards ADD COLUMN diary_mood TEXT")
  runIgnoreError(db, "ALTER TABLE flash_cards ADD COLUMN diary_content TEXT")
  runIgnoreError(db, "ALTER TABLE flash_cards ADD COLUMN task_recommendations_json TEXT")
  runIgnoreError(db, "ALTER TABLE flash_cards ADD COLUMN analysis_error_code TEXT")
  runIgnoreError(db, "ALTER TABLE flash_task_recommendations ADD COLUMN superseded_at TEXT")
  runIgnoreError(db, "ALTER TABLE flash_task_recommendations ADD COLUMN creation_mode TEXT NOT NULL DEFAULT 'confirm'")
  runIgnoreError(db, "ALTER TABLE flash_task_recommendations ADD COLUMN local_task_id TEXT")
  runIgnoreError(db, "ALTER TABLE flash_task_recommendations ADD COLUMN creation_idempotency_key TEXT")
  runIgnoreError(db, "CREATE UNIQUE INDEX IF NOT EXISTS idx_flash_recommendations_creation_key ON flash_task_recommendations(creation_idempotency_key) WHERE creation_idempotency_key IS NOT NULL")
  runIgnoreError(db, "ALTER TABLE flash_cards ADD COLUMN pushed_at TEXT")
  runIgnoreError(db, "ALTER TABLE management_plans ADD COLUMN pushed_at TEXT")
  runIgnoreError(db, "ALTER TABLE management_plan_revisions ADD COLUMN pushed_at TEXT")
  runIgnoreError(db, "CREATE UNIQUE INDEX IF NOT EXISTS idx_exercise_plan_items_version_order ON exercise_plan_items(plan_version, day_key, variant, sort_order)")
  runIgnoreError(db, "INSERT OR IGNORE INTO system_config (key, value, description, updated_at) VALUES ('exercise_week_num', '1', '运动打卡内部周次', datetime('now','localtime'))")
  runIgnoreError(db, "INSERT OR IGNORE INTO system_config (key, value, description, updated_at) VALUES ('active_exercise_plan_version', 'v0', '当前训练计划版本', datetime('now','localtime'))")
  runIgnoreError(db, "ALTER TABLE tasks ADD COLUMN deleted_at TEXT")
  runIgnoreError(db, "ALTER TABLE tasks ADD COLUMN source_etag TEXT")
  runIgnoreError(db, "ALTER TABLE tasks ADD COLUMN source_modified_time TEXT")
  runIgnoreError(db, "ALTER TABLE tasks ADD COLUMN source TEXT NOT NULL DEFAULT 'ticktick'")
  runIgnoreError(db, "ALTER TABLE habits ADD COLUMN source TEXT NOT NULL DEFAULT 'ticktick'")
  runIgnoreError(db, "UPDATE tasks SET source = 'local' WHERE id LIKE 'local_%'")
  runIgnoreError(db, "UPDATE habits SET source = 'local' WHERE id LIKE 'local_%'")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN source TEXT DEFAULT 'screenshot_ocr'")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN atm_sleep_start TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN atm_sleep_end TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN synced_at TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN sync_status TEXT DEFAULT 'success'")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN sync_error TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN analysis_html TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN official_advice TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN morning_diary_written_at TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN evening_diary_written_at TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN full_report_state TEXT")
  runIgnoreError(db, "ALTER TABLE huawei_sleep_data ADD COLUMN tracked_duration_seconds INTEGER")
  runIgnoreError(db, "ALTER TABLE habits ADD COLUMN raw_json TEXT")
  runIgnoreError(db, "ALTER TABLE habits ADD COLUMN source_etag TEXT")
  runIgnoreError(db, "ALTER TABLE habits ADD COLUMN source_modified_time TEXT")
  runIgnoreError(db, "ALTER TABLE habit_checkins ADD COLUMN raw_json TEXT")
  runIgnoreError(db, "ALTER TABLE habit_checkins ADD COLUMN source_modified_time TEXT")
  runIgnoreError(db, "CREATE INDEX IF NOT EXISTS idx_sync_outbox_status ON sync_outbox(status, id)")
  runIgnoreError(db, "CREATE INDEX IF NOT EXISTS idx_sync_outbox_record ON sync_outbox(table_name, record_id)")
  runIgnoreError(db, "CREATE INDEX IF NOT EXISTS idx_client_sync_state_key ON client_sync_state(key)")
  runIgnoreError(db, "CREATE INDEX IF NOT EXISTS idx_behavior_event_outbox_created ON behavior_event_outbox(created_at, event_id)")
  runIgnoreError(
    db,
    "INSERT OR IGNORE INTO client_sync_state (key, value, description, updated_at) VALUES ('last_server_version', '0', '客户端最后成功应用的服务端版本号', datetime('now','localtime'))",
  )
  repairAtmPullOnlyCache(db)

  // CHG-20260609-007: 学习目标多维度信息增强
  runIgnoreError(db, "ALTER TABLE learning_objectives ADD COLUMN duration INTEGER")
  runIgnoreError(db, "ALTER TABLE learning_objectives ADD COLUMN baseline TEXT")
  runIgnoreError(db, "ALTER TABLE learning_objectives ADD COLUMN target_description TEXT")
  
  // CHG-20260609-007: 学习任务与清单任务对齐
  runIgnoreError(db, "ALTER TABLE learning_tasks ADD COLUMN category_id INTEGER")
  runIgnoreError(db, "ALTER TABLE learning_tasks ADD COLUMN priority INTEGER DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE learning_tasks ADD COLUMN reward INTEGER DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE learning_tasks ADD COLUMN due_date TEXT")

  const syncWatermarks = [
    ["client_to_server_synced_at", "客户端往服务端同步时间"],
    ["server_to_client_synced_at", "服务端往客户端同步时间"],
    ["server_to_ticktick_synced_at", "服务端往滴答清单同步时间"],
    ["ticktick_to_server_synced_at", "滴答清单往服务端同步时间"],
    ["device_id", "客户端设备 ID"],
  ]
  for (const [key, description] of syncWatermarks) {
    runIgnoreError(
      db,
      "INSERT OR IGNORE INTO system_config (key, value, value_type, description, updated_at) VALUES (?, '', 'string', ?, datetime('now','localtime'))",
      [key, description],
    )
  }

  runIgnoreError(
    db,
    `DELETE FROM learning_tasks
     WHERE kr_id IN (
       SELECT id FROM learning_krs WHERE objective_id = ?
     )
     AND EXISTS (
       SELECT 1 FROM learning_objectives WHERE title = ? AND id <> ?
     )`,
    [DEFAULT_LEARNING_OBJECTIVE.id, DEFAULT_LEARNING_OBJECTIVE.title, DEFAULT_LEARNING_OBJECTIVE.id],
  )
  runIgnoreError(
    db,
    `DELETE FROM learning_krs
     WHERE objective_id = ?
     AND EXISTS (
       SELECT 1 FROM learning_objectives WHERE title = ? AND id <> ?
     )`,
    [DEFAULT_LEARNING_OBJECTIVE.id, DEFAULT_LEARNING_OBJECTIVE.title, DEFAULT_LEARNING_OBJECTIVE.id],
  )
  runIgnoreError(
    db,
    `DELETE FROM learning_objectives
     WHERE id = ?
     AND EXISTS (
       SELECT 1 FROM learning_objectives WHERE title = ? AND id <> ?
     )`,
    [DEFAULT_LEARNING_OBJECTIVE.id, DEFAULT_LEARNING_OBJECTIVE.title, DEFAULT_LEARNING_OBJECTIVE.id],
  )
  markSeedInitializedWhenDataExists(db, 'learning_seed_initialized', '学习页初始示例数据已初始化', 'learning_objectives')
  markSeedInitializedWhenDataExists(db, 'exercise_seed_initialized', '运动页初始示例计划已初始化', 'exercise_plan_versions')
  markSeedInitializedWhenDataExists(db, 'exercise_seed_initialized', '运动页初始示例计划已初始化', 'exercise_plan_items')
  markSeedInitializedWhenDataExists(db, 'exercise_seed_initialized', '运动页初始示例计划已初始化', 'exercise_plan_schedule_items')
  markSeedInitializedWhenDataExists(db, 'exercise_seed_initialized', '运动页初始示例计划已初始化', 'exercise_plan_score_rules')
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN bedtime_coin_status TEXT NOT NULL DEFAULT 'pending'")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN bedtime_coin_amount REAL NOT NULL DEFAULT 0")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN bedtime_coin_reason TEXT")
  runIgnoreError(db, "ALTER TABLE sleep_score_settlements ADD COLUMN bedtime_coin_rule_version TEXT")
}

/** 执行全量建表（幂等），传入 SQLite 适配器实例 */
export function initDatabase(db: SqlDB): void {
  try {
    db.run("PRAGMA journal_mode=WAL;")
  } catch {
    // 部分 SQLite 适配器不支持 WAL，安全忽略
  }
  for (const ddl of DDL_STATEMENTS) {
    try {
      db.run(ddl)
    } catch {
      // 表/索引已存在则跳过
    }
  }
  applyCompatibilityMigrations(db)
}
