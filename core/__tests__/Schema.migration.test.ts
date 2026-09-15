import { describe, it, expect } from 'vitest'
import { createBetterSqliteAdapter, type BetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { initDatabase, SCHEMA_VERSION } from '../models/Schema'

const all = (db: BetterSqliteAdapter, sql: string): Record<string, any>[] => {
  const stmt = db.prepare(sql)
  const rows: Record<string, any>[] = []
  while (stmt.step()) rows.push(stmt.getAsObject())
  stmt.free()
  return rows
}

const columnNames = (db: BetterSqliteAdapter, table: string): string[] =>
  all(db, `PRAGMA table_info(${table})`).map(row => String(row.name))

describe('Schema 迁移幂等性测试 (CHG-20260609-007)', () => {
  it('完整库再次初始化不执行字段 ALTER TABLE', () => {
    const sqlDb = createBetterSqliteAdapter()
    const originalRun = sqlDb.run.bind(sqlDb)
    const alterSql: string[] = []
    sqlDb.run = ((sql: string, params?: any[]) => {
      if (/^ALTER TABLE/i.test(sql.trim())) alterSql.push(sql)
      originalRun(sql, params)
    }) as BetterSqliteAdapter['run']

    initDatabase(sqlDb)
    expect(alterSql.length).toBeGreaterThan(0)
    alterSql.length = 0
    initDatabase(sqlDb)

    expect(alterSql).toEqual([])
  })

  it('重复执行 initDatabase 不应报错（learning_objectives 新增字段）', () => {
    const sqlDb = createBetterSqliteAdapter()

    // 第一次执行 initDatabase，创建表并添加新字段
    expect(() => initDatabase(sqlDb)).not.toThrow()

    // 验证 learning_objectives 表存在
    const tableExists = all(sqlDb,
      "SELECT name FROM sqlite_master WHERE type='table' AND name='learning_objectives'"
    )
    expect(tableExists.length).toBeGreaterThan(0)

    // 验证新字段已添加
    const columns = columnNames(sqlDb, 'learning_objectives')

    expect(columns).toContain('duration')
    expect(columns).toContain('baseline')
    expect(columns).toContain('target_description')

    // 第二次执行 initDatabase，应该幂等（不报错）
    expect(() => initDatabase(sqlDb)).not.toThrow()

    // 验证字段仍然存在（没有被重复添加或破坏）
    const columnNamesAfter = columnNames(sqlDb, 'learning_objectives')
    
    expect(columnNamesAfter).toContain('duration')
    expect(columnNamesAfter).toContain('baseline')
    expect(columnNamesAfter).toContain('target_description')
    
    // 字段数量应该保持不变（没有重复添加）
    expect(columnNamesAfter.length).toBe(columns.length)
  })

  it('重复执行 initDatabase 不应报错（learning_tasks 新增字段）', () => {
    const sqlDb = createBetterSqliteAdapter()

    // 第一次执行
    expect(() => initDatabase(sqlDb)).not.toThrow()

    // 验证 learning_tasks 表存在
    const tableExists = all(sqlDb,
      "SELECT name FROM sqlite_master WHERE type='table' AND name='learning_tasks'"
    )
    expect(tableExists.length).toBeGreaterThan(0)

    // 验证新字段已添加
    const columns = columnNames(sqlDb, 'learning_tasks')

    expect(columns).toContain('category_id')
    expect(columns).toContain('priority')
    expect(columns).toContain('reward')
    expect(columns).toContain('due_date')

    // 第二次执行，应该幂等
    expect(() => initDatabase(sqlDb)).not.toThrow()

    // 验证字段仍然存在
    const columnNamesAfter = columnNames(sqlDb, 'learning_tasks')
    
    expect(columnNamesAfter).toContain('category_id')
    expect(columnNamesAfter).toContain('priority')
    expect(columnNamesAfter).toContain('reward')
    expect(columnNamesAfter).toContain('due_date')
    
    // 字段数量保持不变
    expect(columnNamesAfter.length).toBe(columns.length)
  })

  it('模拟旧库升级场景：先创建旧表，再执行两次 initDatabase', () => {
    const sqlDb = createBetterSqliteAdapter()

    // 模拟旧库：只有基础字段的 learning_objectives 表
    sqlDb.run(`
      CREATE TABLE learning_objectives (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        status INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        pushed_at TEXT
      )
    `)

    // 插入测试数据
    sqlDb.run(`
      INSERT INTO learning_objectives (id, title, status, created_at)
      VALUES ('test-obj-1', '测试目标', 0, '2026-06-09 00:00:00')
    `)

    // 验证旧数据存在
    const oldData = all(sqlDb, "SELECT * FROM learning_objectives WHERE id = 'test-obj-1'")
    expect(oldData).toHaveLength(1)

    // 第一次执行 initDatabase（升级）
    expect(() => initDatabase(sqlDb)).not.toThrow()

    // 验证新字段已添加
    const columnNamesAfterFirst = columnNames(sqlDb, 'learning_objectives')
    expect(columnNamesAfterFirst).toContain('duration')
    expect(columnNamesAfterFirst).toContain('baseline')
    expect(columnNamesAfterFirst).toContain('target_description')

    // 验证旧数据仍然存在且可读取
    const dataAfterFirst = all(sqlDb, "SELECT id, title, duration, baseline FROM learning_objectives WHERE id = 'test-obj-1'")
    expect(dataAfterFirst).toHaveLength(1)
    expect(dataAfterFirst[0].title).toBe('测试目标')
    expect(dataAfterFirst[0].duration).toBe(null)

    // 第二次执行 initDatabase（幂等测试）
    expect(() => initDatabase(sqlDb)).not.toThrow()

    // 验证字段仍然存在且数量不变
    const columnNamesAfterSecond = columnNames(sqlDb, 'learning_objectives')
    expect(columnNamesAfterSecond).toContain('duration')
    expect(columnNamesAfterSecond).toContain('baseline')
    expect(columnNamesAfterSecond).toContain('target_description')
    expect(columnNamesAfterSecond.length).toBe(columnNamesAfterFirst.length)

    // 验证旧数据依然完好
    const dataAfterSecond = all(sqlDb, "SELECT id, title FROM learning_objectives WHERE id = 'test-obj-1'")
    expect(dataAfterSecond).toHaveLength(1)
    expect(dataAfterSecond[0].title).toBe('测试目标')
  })

  it('learning_tasks 旧库升级场景：先创建旧表，再执行两次 initDatabase', () => {
    const sqlDb = createBetterSqliteAdapter()

    // 先创建依赖表（因为有外键约束）
    sqlDb.run(`
      CREATE TABLE learning_objectives (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        status INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
      )
    `)
    sqlDb.run(`
      CREATE TABLE learning_krs (
        id TEXT PRIMARY KEY,
        objective_id TEXT NOT NULL,
        title TEXT NOT NULL,
        target_value INTEGER NOT NULL DEFAULT 100,
        current_value INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
      )
    `)

    // 模拟旧库：只有基础字段的 learning_tasks 表
    sqlDb.run(`
      CREATE TABLE learning_tasks (
        id TEXT PRIMARY KEY,
        kr_id TEXT NOT NULL,
        title TEXT NOT NULL,
        status INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        pushed_at TEXT
      )
    `)

    // 插入测试数据
    sqlDb.run(`
      INSERT INTO learning_objectives (id, title, status, created_at)
      VALUES ('obj-1', '目标1', 0, '2026-06-09 00:00:00')
    `)
    sqlDb.run(`
      INSERT INTO learning_krs (id, objective_id, title, target_value, current_value, created_at)
      VALUES ('kr-1', 'obj-1', 'KR1', 100, 0, '2026-06-09 00:00:00')
    `)
    sqlDb.run(`
      INSERT INTO learning_tasks (id, kr_id, title, status, created_at)
      VALUES ('task-1', 'kr-1', '测试任务', 0, '2026-06-09 00:00:00')
    `)

    // 验证旧数据存在
    const oldData = all(sqlDb, "SELECT * FROM learning_tasks WHERE id = 'task-1'")
    expect(oldData).toHaveLength(1)

    // 第一次执行 initDatabase（升级）
    expect(() => initDatabase(sqlDb)).not.toThrow()

    // 验证新字段已添加
    const columnNamesAfterFirst = columnNames(sqlDb, 'learning_tasks')
    expect(columnNamesAfterFirst).toContain('category_id')
    expect(columnNamesAfterFirst).toContain('priority')
    expect(columnNamesAfterFirst).toContain('reward')
    expect(columnNamesAfterFirst).toContain('due_date')

    // 验证旧数据仍然存在且可读取
    const dataAfterFirst = all(sqlDb, "SELECT id, title, category_id, priority, reward FROM learning_tasks WHERE id = 'task-1'")
    expect(dataAfterFirst).toHaveLength(1)
    expect(dataAfterFirst[0].title).toBe('测试任务')
    expect(dataAfterFirst[0].category_id).toBe(null)
    expect(dataAfterFirst[0].priority).toBe(0)
    expect(dataAfterFirst[0].reward).toBe(0)

    // 第二次执行 initDatabase（幂等测试）
    expect(() => initDatabase(sqlDb)).not.toThrow()

    // 验证字段仍然存在且数量不变
    const columnNamesAfterSecond = columnNames(sqlDb, 'learning_tasks')
    expect(columnNamesAfterSecond).toContain('category_id')
    expect(columnNamesAfterSecond).toContain('priority')
    expect(columnNamesAfterSecond).toContain('reward')
    expect(columnNamesAfterSecond).toContain('due_date')
    expect(columnNamesAfterSecond.length).toBe(columnNamesAfterFirst.length)

    // 验证旧数据依然完好
    const dataAfterSecond = all(sqlDb, "SELECT id, title FROM learning_tasks WHERE id = 'task-1'")
    expect(dataAfterSecond).toHaveLength(1)
    expect(dataAfterSecond[0].title).toBe('测试任务')
  })

  it('客户端任务习惯表包含服务端 provider 指纹字段', () => {
    const sqlDb = createBetterSqliteAdapter()

    expect(() => initDatabase(sqlDb)).not.toThrow()

    const taskColumns = columnNames(sqlDb, 'tasks')
    expect(taskColumns).toContain('source_etag')
    expect(taskColumns).toContain('source_modified_time')

    const habitColumns = columnNames(sqlDb, 'habits')
    expect(habitColumns).toContain('raw_json')
    expect(habitColumns).toContain('source_etag')
    expect(habitColumns).toContain('source_modified_time')

    const checkinColumns = columnNames(sqlDb, 'habit_checkins')
    expect(checkinColumns).toContain('raw_json')
    expect(checkinColumns).toContain('source_modified_time')
  })

  it('旧任务和习惯升级后保留镜像来源并识别 local_ 记录', () => {
    const db = createBetterSqliteAdapter()
    db.run('CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT NOT NULL)')
    db.run('CREATE TABLE habits (id TEXT PRIMARY KEY, name TEXT NOT NULL)')
    db.run("INSERT INTO tasks VALUES ('ticktick_task', '镜像任务')")
    db.run("INSERT INTO tasks VALUES ('local_task', '本地任务')")
    db.run("INSERT INTO habits VALUES ('ticktick_habit', '镜像习惯')")
    db.run("INSERT INTO habits VALUES ('local_habit', '本地习惯')")

    initDatabase(db)

    expect(all(db, "SELECT source FROM tasks WHERE id = 'ticktick_task'")[0].source).toBe('ticktick')
    expect(all(db, "SELECT source FROM habits WHERE id = 'ticktick_habit'")[0].source).toBe('ticktick')
    expect(all(db, "SELECT source FROM tasks WHERE id = 'local_task'")[0].source).toBe('local')
    expect(all(db, "SELECT source FROM habits WHERE id = 'local_habit'")[0].source).toBe('local')
  })

  it('幂等补齐旧 ATM 表 pulled_at 并保留 repair 后记录', () => {
    const db = createBetterSqliteAdapter()
    db.run('CREATE TABLE atm_summary (id INTEGER PRIMARY KEY, date TEXT UNIQUE, updated_at TEXT, pushed_at TEXT)')
    db.run('CREATE TABLE atm_activities (id INTEGER PRIMARY KEY, date TEXT, activity_type TEXT, start_time TEXT, end_time TEXT, duration_minutes INTEGER, comment TEXT, updated_at TEXT, pushed_at TEXT)')
    db.run('CREATE TABLE client_sync_state (key TEXT PRIMARY KEY, value TEXT NOT NULL, description TEXT, updated_at TEXT NOT NULL)')
    db.run("INSERT INTO client_sync_state VALUES ('atm_pull_cache_repair_v1','1','done','2026-07-21')")
    db.run("INSERT INTO atm_summary VALUES (1,'2026-07-20','u','p')")
    db.run("INSERT INTO atm_activities VALUES (7,'2026-07-20','work','09:00','10:00',60,'memo','u','p')")

    initDatabase(db)
    const firstColumns = [columnNames(db, 'atm_summary'), columnNames(db, 'atm_activities')]
    initDatabase(db)

    expect(firstColumns.every(columns => columns.includes('pulled_at'))).toBe(true)
    expect(all(db, 'SELECT id FROM atm_summary')[0].id).toBe(1)
    expect(all(db, 'SELECT id FROM atm_activities')[0].id).toBe(7)
  })

  it('只执行一次 ATM pull-only 缓存 repair', () => {
    const db = createBetterSqliteAdapter()
    initDatabase(db)
    db.run("DELETE FROM client_sync_state WHERE key='atm_pull_cache_repair_v1'")
    db.run("INSERT INTO atm_summary (date) VALUES ('2026-07-19')")
    db.run("INSERT INTO atm_activities (date,activity_type,start_time,end_time,duration_minutes) VALUES ('2026-07-19','work','09:00','10:00',60)")
    const categoryCount = all(db, 'SELECT * FROM categories').length
    db.run("INSERT INTO atimelogger_segments (local_session_id,local_segment_key,sync_state,created_at) VALUES ('s','session:s','pending_create','2026-07-21')")

    initDatabase(db)
    expect(all(db, 'SELECT * FROM atm_summary')).toHaveLength(0)
    expect(all(db, 'SELECT * FROM atm_activities')).toHaveLength(0)
    expect(all(db, 'SELECT * FROM categories')).toHaveLength(categoryCount)
    expect(all(db, 'SELECT * FROM atimelogger_segments')).toHaveLength(1)
    expect(all(db, "SELECT * FROM client_sync_state WHERE key='atm_pull_cache_repair_v1'")).toHaveLength(1)

    db.run("INSERT INTO atm_summary (date) VALUES ('2026-07-20')")
    initDatabase(db)
    expect(all(db, 'SELECT * FROM atm_summary')).toHaveLength(1)
  })

  it('幂等补齐旧饮食打卡 pushed_at 且保留逐项事实', () => {
    const db = createBetterSqliteAdapter()
    db.run(`CREATE TABLE exercise_diet_checkins (
      id TEXT PRIMARY KEY, date TEXT NOT NULL, plan_version TEXT NOT NULL,
      rule_key TEXT NOT NULL, status TEXT NOT NULL, occurred_at TEXT, deadline_at TEXT NOT NULL,
      failure_reason TEXT, penalty_source_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, pulled_at TEXT,
      UNIQUE(date, plan_version, rule_key))`)
    for (const [key, status] of [['no_snacks', 'completed'], ['no_sugary_drinks', 'completed'], ['no_refined_staples', 'pending']]) {
      db.run('INSERT INTO exercise_diet_checkins VALUES (?,?,?,?,?,NULL,?,NULL,NULL,?,?,?)',
        [`diet:${key}`, '2026-09-12', 'v4', key, status, '2026-09-13T00:00:00+08:00', '2026-09-12 00:00:00', '2026-09-12 11:00:00', '2026-09-12 00:40:00'])
    }

    initDatabase(db); const firstColumns = columnNames(db, 'exercise_diet_checkins'); initDatabase(db)

    expect(firstColumns).toContain('pushed_at')
    expect(columnNames(db, 'exercise_diet_checkins')).toHaveLength(firstColumns.length)
    expect(all(db, 'SELECT rule_key,status FROM exercise_diet_checkins ORDER BY rule_key')).toEqual([
      { rule_key: 'no_refined_staples', status: 'pending' }, { rule_key: 'no_snacks', status: 'completed' },
      { rule_key: 'no_sugary_drinks', status: 'completed' },
    ])
  })

  it('验证 Schema 版本号正确', () => {
    // Schema 版本应该是 11（根据当前 Schema.ts 文件）
    expect(SCHEMA_VERSION).toBe(11)
  })

  it('幂等升级独立晨晚日记奖励投影且保留旧结算', () => {
    const db = createBetterSqliteAdapter()
    db.run("CREATE TABLE sleep_score_settlements (id TEXT PRIMARY KEY, sleep_date TEXT, rule_version TEXT, updated_at TEXT)")
    db.run("INSERT INTO sleep_score_settlements VALUES ('legacy','2026-09-05','sleep-score-v2','old')")
    initDatabase(db); const first = columnNames(db, 'sleep_score_settlements'); initDatabase(db)
    expect(['morning_diary_reward_status', 'morning_diary_reward_amount', 'morning_diary_reward_reason', 'morning_diary_reward_rule_version', 'evening_diary_reward_status', 'evening_diary_reward_amount', 'evening_diary_reward_reason', 'evening_diary_reward_rule_version'].every(name => first.includes(name))).toBe(true)
    expect(columnNames(db, 'sleep_score_settlements')).toHaveLength(first.length)
    expect(all(db, "SELECT id FROM sleep_score_settlements WHERE id='legacy'")).toHaveLength(1)
  })
})
