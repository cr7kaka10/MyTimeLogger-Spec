import { describe, it, expect, beforeAll } from 'vitest'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { Database } from '../models/Database'
import { initDatabase as initSchema } from '../models/Schema'
import { SYNC_TABLES } from '../core/SyncWorker'

describe('Database', () => {
  let db: Database

  beforeAll(() => {
    db = new Database(createBetterSqliteAdapter())
  })

  const createIsolatedDb = () => new Database(createBetterSqliteAdapter())

  it('空PC库只初始化一次默认分类且不预填登录凭据', () => {
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    const first = new Database(sqlDb)
    expect(first.allRaw('SELECT id FROM categories')).toHaveLength(19)
    expect(first.allRaw('SELECT name FROM categories ORDER BY sort_order').map(row => row.name)).toEqual([
      '输入', '输出', '副业生产', '副业营销', '副业研发', '工作', '吃饭', '带娃', '家务', '娱乐',
      '交通', '个人杂事', '休息', '活动', '运动', '松鼠病', '状态切换', '睡觉', '拉屎',
    ])
    expect(first.allRaw("SELECT value FROM system_config WHERE key = 'timer_seed_initialized'")).toEqual([
      expect.objectContaining({ value: '1' }),
    ])
    expect(first.allRaw("SELECT key FROM system_config WHERE key = 'atimelogger_config' OR key LIKE 'env_%_auth_token'")).toHaveLength(0)

    initSchema(sqlDb)
    const second = new Database(sqlDb)
    expect(second.allRaw('SELECT id FROM categories')).toHaveLength(19)
  })

  it('确保设备标识只写本地配置且不创建待同步业务操作', () => {
    const local = createIsolatedDb()
    local.runRaw("DELETE FROM system_config WHERE key = 'device_id'")
    const deviceId = local.ensureDeviceId()
    expect(deviceId).toMatch(/^device_/)
    expect(local.ensureDeviceId()).toBe(deviceId)
    expect(local.getConfig('device_id')).toBe(deviceId)
    expect(local.allRaw('SELECT * FROM sync_outbox')).toHaveLength(0)
  })

  it('原生任务拒绝空标题并写入北京日期、来源与 outbox', () => {
    const local = createIsolatedDb()
    expect(() => local.addTask('   ')).toThrow('任务标题不能为空')
    const id = local.addTask('  本地待办  ')
    expect(local.allRaw('SELECT title, due_date, source FROM tasks WHERE id = ?', [id])[0]).toMatchObject({
      title: '本地待办', source: 'local', due_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    })
    expect(local.getPendingOutbox(10)).toEqual(expect.arrayContaining([
      expect.objectContaining({ table_name: 'tasks', record_id: id }),
    ]))
  })

  it('原生习惯可编辑、打卡、归档并保留本地来源', () => {
    const local = createIsolatedDb()
    const id = local.addHabit('  晨间拉伸  ')
    local.updateHabit(id, { repeat_rule: 'FREQ=DAILY' })
    local.toggleCheckin(id, '2026-09-06')
    local.deleteHabit(id)
    expect(local.allRaw('SELECT name, source, repeat_rule, is_active FROM habits WHERE id = ?', [id])[0]).toMatchObject({
      name: '晨间拉伸', source: 'local', repeat_rule: 'FREQ=DAILY', is_active: 1,
    })
    expect(local.allRaw('SELECT * FROM habit_checkins WHERE habit_id = ?', [id])).toHaveLength(1)
  })

  it('管理方案本地缓存可写入读取但不创建 outbox', () => {
    const local = createIsolatedDb()
    const planId = local.saveManagementPlan({ plan_key: 'cached-plan', title: '缓存方案' })
    local.saveManagementPlanRevision({ plan_id: planId, config_json: '{}', logical_version: '1' })
    expect(local.getManagementPlan(planId)?.title).toBe('缓存方案')
    expect(local.getManagementPlanRevisions(planId)).toHaveLength(1)
    expect(local.getPendingOutbox(20).filter(item => item.table_name.startsWith('management_plan'))).toHaveLength(0)
  })

  it('闪念使用稳定 ID 和 pending 入队且不推送 AI 字段', () => {
    const local = createIsolatedDb()
    const id = local.saveFlashCard({ occurred_at: '2026-08-12 20:00:00', original_text: '写总结', polished_text: '伪造' })
    const card = local.getFlashCard(id)
    const payload = JSON.parse(local.getPendingOutbox(20).find(item => item.table_name === 'flash_cards')!.payload_json)
    expect(card.analysis_status).toBe('pending')
    expect(payload).toEqual({ id, occurred_at: card.occurred_at, original_text: '写总结', analysis_status: 'pending' })
    local.markOutboxSynced(local.getPendingOutbox(20).map(item => item.id), '2026-08-12 20:01:00')
    local.deleteFlashCard(id)
    expect(local.getFlashCard(id)?.deleted_at).toBeTruthy()
    expect(JSON.parse(local.getPendingOutbox(20)[0].payload_json)).toMatchObject({ id, deleted_at: expect.any(String) })
  })

  it('推荐任务查询保留真实来源字段和三种状态', () => {
    const local = createIsolatedDb()
    for (const [id, flashCardId, status] of [['rec-pending', 'flash-a', 'pending'], ['rec-added', 'flash-a', 'added'], ['rec-ignored', 'flash-b', 'ignored']]) {
      local.runRaw(`INSERT INTO flash_task_recommendations
        (id,flash_card_id,ordinal,title,reason,status,created_at,updated_at)
        VALUES (?,?,0,?,?,?,datetime('now','localtime'),datetime('now','localtime'))`, [id, flashCardId, id, status, status])
    }

    expect(local.getFlashTaskRecommendations(['flash-a'])).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'rec-added', flash_card_id: 'flash-a', status: 'added' }),
      expect.objectContaining({ id: 'rec-pending', flash_card_id: 'flash-a', status: 'pending' }),
    ]))
    expect(local.getFlashTaskRecommendations(['flash-b'])[0]).toMatchObject({ flash_card_id: 'flash-b', status: 'ignored' })
  })

  it('分类 CRUD', () => {
    const id = db.addCategory('测试分类', '📖', '#000', '输入')
    expect(id).toBeGreaterThan(0)

    const cats = db.getCategories()
    expect(cats.find(c => c.id === id)).toBeTruthy()

    db.updateCategory(id, { name: '改名分类' })
    const updated = db.getCategories().find(c => c.id === id)
    expect(updated?.name).toBe('改名分类')

    db.deleteCategory(id)
    const after = db.getCategories().find(c => c.id === id)
    // 软删除后 getCategories 不再返回该记录
    expect(after).toBeUndefined()
  })

  it('会话记录', () => {
    const now = new Date().toISOString().replace('T', ' ').slice(0, 19)
    const id = db.logSession({
      startTime: now,
      endTime: now,
      netDurationMinutes: 25,
      date: '2026-05-28',
      dayOfWeek: 'Thursday',
      categoryId: null,
    })
    expect(id).toBeTruthy()

    const sessions = db.getSessionsByDate('2026-05-28')
    expect(sessions.length).toBeGreaterThanOrEqual(1)
  })

  it('手动跨天会话归属覆盖时长更长的日期，并修复错误的历史归属', () => {
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    const local = new Database(sqlDb)
    const id = local.addManualSession({
      startTime: '2026-08-04 05:18:12', endTime: '2026-08-04 06:18:12',
      netDurationMinutes: 60, date: '2026-08-05', categoryId: null,
    })
    expect(local.getRecordById('study_sessions', id)?.date).toBe('2026-08-04')

    local.updateSession(id, { start_time: '2026-08-03 23:50:00' })
    expect(local.getRecordById('study_sessions', id)?.date).toBe('2026-08-04')
    expect(local.getSessionsByDate('2026-08-03')).not.toContainEqual(expect.objectContaining({ id }))
    expect(local.getSessionsByDate('2026-08-04')).toContainEqual(expect.objectContaining({ id }))

    sqlDb.run("UPDATE study_sessions SET date = '2026-08-05' WHERE id = ?", [id])
    expect(local.repairManualSessionBusinessDates()).toBe(1)
    expect(local.getRecordById('study_sessions', id)?.date).toBe('2026-08-04')
  })

  it('习惯打卡', () => {
    const hid = db.addHabit('早起', '🌅', 'easy')
    expect(hid).toBeTruthy()

    const checkin = db.toggleCheckin(hid as any, '2026-05-28')
    expect(checkin.status).toBe(2)
    expect(checkin.coins).toBeGreaterThanOrEqual(0)

    // 取消打卡
    const cancel = db.toggleCheckin(hid as any, '2026-05-28')
    expect(cancel.status).toBe(0)
  })

  it('配置读写', () => {
    db.setConfig('test_key', 'test_value', 'test')
    expect(db.getConfig('test_key')).toBe('test_value')
  })

  it('服务端同步的目标和背包历史可从本地缓存读取且不产生 outbox', () => {
    const isolated = createIsolatedDb()
    const rewardId = isolated.addReward('缓存奖品', '🎁', 0, '')
    isolated.addGoal({ title: '单次目标', category_id: null, metric: 'count', target_value: 1, period: 'per_session', reward_coins: 0, reward_id: rewardId, operator: '>=', penalty_coins: 0 } as any)
    isolated.runRaw("INSERT INTO reward_ledger (id,amount,source_type,source_id,description,target_date,created_at,updated_at) VALUES ('purchase-1',0,'reward_buy',?,'入库','2026-08-01','2026-08-01 10:00:00','2026-08-01 10:00:00')", [`${rewardId}:goal:claim-1`])
    isolated.runRaw("INSERT INTO reward_ledger (id,amount,source_type,source_id,description,target_date,created_at,updated_at) VALUES ('use-1',0,'backpack_use','purchase-1','使用','2026-08-01','2026-08-01 10:01:00','2026-08-01 10:01:00')")

    expect(isolated.getGoals()[0]).toMatchObject({ period: 'per_session', reward_id: rewardId })
    expect(isolated.getBackpackItems()[0]).toMatchObject({ id: 'purchase-1', title: '缓存奖品', is_used: true, used_at: '2026-08-01 10:01:00' })
    expect(isolated.getPendingOutbox(20).filter(item => ['goals', 'rewards', 'reward_ledger'].includes(item.table_name))).toHaveLength(0)
  })

  it('多分类目标在本地 pull 缓存中聚合进度和历史', () => {
    const isolated = createIsolatedDb()
    isolated.runRaw("INSERT INTO categories (id, name, is_active, created_at, updated_at) VALUES (901, '输入测试', 1, '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
    isolated.runRaw("INSERT INTO categories (id, name, is_active, created_at, updated_at) VALUES (902, '输出测试', 1, '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
    isolated.runRaw("INSERT INTO goals (id, title, category_id, metric, target_value, period, reward_coins, operator, is_active, created_at, updated_at) VALUES ('multi-goal', '输入加输出', 901, 'duration', 360, 'daily', 0, '>=', 1, '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
    isolated.runRaw("INSERT INTO goal_category_bindings (id, goal_id, category_id, created_at, updated_at) VALUES ('multi-goal-input', 'multi-goal', 901, '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
    isolated.runRaw("INSERT INTO goal_category_bindings (id, goal_id, category_id, created_at, updated_at) VALUES ('multi-goal-output', 'multi-goal', 902, '2026-08-01 00:00:00', '2026-08-01 00:00:00')")
    const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
    isolated.runRaw("INSERT INTO study_sessions (id, category_id, net_duration_minutes, date, start_time, end_time) VALUES ('input-210', 901, 210, ?, ?, ?)", [today, `${today} 09:00:00`, `${today} 12:30:00`])
    isolated.runRaw("INSERT INTO study_sessions (id, category_id, net_duration_minutes, date, start_time, end_time) VALUES ('output-150', 902, 150, ?, ?, ?)", [today, `${today} 14:00:00`, `${today} 16:30:00`])

    const goal = isolated.getGoals().find(row => row.id === 'multi-goal')!
    expect(goal.category_ids).toEqual([901, 902])
    expect(isolated.getGoalProgress(goal)).toMatchObject({ current: 360, target: 360, percent: 100 })
    expect(isolated.getCategoriesHistory(goal.category_ids!, 'duration', 1)[today]).toBe(360)
  })

  it('按配置的北京时间起点过滤同步任务', () => {
    const isolated = createIsolatedDb()
    isolated.setConfig('checklist_sync_start_date', '2026-07-01')
    isolated.upsertTask({ id: 'before-start', title: '旧任务', dueDate: '2026-06-30 23:59:59' })
    isolated.upsertTask({ id: 'at-start', title: '起点任务', dueDate: '2026-07-01 00:00:00' })

    expect(isolated.allRaw("SELECT id FROM tasks WHERE id = 'before-start'")).toHaveLength(0)
    expect(isolated.allRaw("SELECT id FROM tasks WHERE id = 'at-start'")).toHaveLength(1)
  })

  it('按配置的北京时间起点过滤同步习惯打卡', () => {
    const isolated = createIsolatedDb()
    isolated.setConfig('checklist_sync_start_date', '2026-07-01')
    isolated.upsertHabit({ id: 'habit-start-date', name: '测试习惯', status: 0, sortOrder: 1 })
    isolated.upsertHabitCheckin('habit-start-date', '2026-06-30', 2)
    isolated.upsertHabitCheckin('habit-start-date', '2026-07-01', 2)

    expect(isolated.allRaw("SELECT id FROM habit_checkins WHERE checkin_date = '2026-06-30'")).toHaveLength(0)
    expect(isolated.allRaw("SELECT id FROM habit_checkins WHERE checkin_date = '2026-07-01'")).toHaveLength(1)
  })

  it('睡眠数据同日重复保存会合并报告字段且保留日记', () => {
    const isolated = createIsolatedDb()
    isolated.saveSleepData('2026-06-25', {
      sleep_score: 76,
      morning_diary: '早上记录',
      evening_diary: '晚上记录',
    })

    isolated.saveSleepData('2026-06-25', {
      sleep_score: 81,
      analysis_report: '# 报告',
      analysis_html: '<h1>报告</h1>',
      official_advice: '官方建议原文',
    } as any)

    const row = isolated.getSleepData('2026-06-25')
    expect(row?.sleep_score).toBe(81)
    expect(row?.analysis_report).toBe('# 报告')
    expect((row as any)?.analysis_html).toBe('<h1>报告</h1>')
    expect((row as any)?.official_advice).toBe('官方建议原文')
    expect(row?.morning_diary).toBe('早上记录')
    expect(row?.evening_diary).toBe('晚上记录')
    expect(row?.morning_diary_written_at).toBeTruthy()
    expect(row?.evening_diary_written_at).toBeTruthy()
  })

  it('仅在对应日记正文改变时更新书写时间，清空则移除时间', () => {
    const isolated = createIsolatedDb()
    isolated.saveSleepData('2026-06-26', { morning_diary: '第一次晨记', evening_diary: '晚记' })
    const first = isolated.getDiaryForDate('2026-06-26')!
    isolated.saveSleepData('2026-06-26', { sleep_score: 80 })
    expect(isolated.getDiaryForDate('2026-06-26')?.morning_diary_written_at).toBe(first.morning_diary_written_at)
    isolated.saveSleepData('2026-06-26', { morning_diary: '' })
    expect(isolated.getDiaryForDate('2026-06-26')?.morning_diary_written_at).toBeUndefined()
  })

  it('日记专用保存只入队本次字段并返回可确认 change_id', () => {
    const isolated = createIsolatedDb()
    isolated.saveSleepData('2026-09-08', { evening_diary: '原晚记' })
    isolated.markOutboxSynced(isolated.getPendingOutbox(10).map(item => item.id))
    const saved = isolated.saveSleepDiary('2026-09-08', 'morning', '新晨记')
    const payload = JSON.parse(isolated.getPendingOutbox(10)[0].payload_json)
    expect(saved.changeId).toMatch(/^device_/)
    expect(payload).toMatchObject({ id: saved.recordId, date: '2026-09-08', morning_diary: '新晨记' })
    expect(payload).not.toHaveProperty('evening_diary')
    isolated.saveSleepDiary('2026-09-08', 'morning', '')
    expect(JSON.parse(isolated.getPendingOutbox(10)[1].payload_json)).toMatchObject({ morning_diary: '', morning_diary_written_at: null })
  })

  it('设置同步分类：通用设置入 outbox，本机私有设置不入 outbox', () => {
    const isolated = createIsolatedDb()
    isolated.setConfig('theme', 'dark')
    isolated.setConfig('env_development_username', 'dev-user')
    isolated.setConfig('env_development_auth_token', 'token-secret')
    isolated.setConfig('music_folder', 'fixture-music-folder')
    isolated.setConfig('shortcut_toggle_timer', '<alt>+x')

    const rows = isolated.getPendingOutbox(20).filter(item => item.table_name === 'system_config')
    expect(rows.some(item => item.record_id === 'theme')).toBe(true)
    expect(rows.some(item => item.record_id === 'env_development_username')).toBe(false)
    expect(rows.some(item => item.record_id === 'env_development_auth_token')).toBe(false)
    expect(rows.some(item => item.record_id === 'music_folder')).toBe(false)
    expect(rows.some(item => item.record_id === 'hotkeys')).toBe(false)
    expect(isolated.getAllConfig().server_password).toBeUndefined()
  })

  it('18 张同步表均具备 pulled_at 字段', () => {
    const tables = [
      'categories', 'study_sessions', 'tasks', 'habits', 'habit_checkins', 'goals',
      'rewards', 'reward_ledger', 'external_rewards', 'reward_config', 'huawei_sleep_data',
      'system_config', 'exercise_plan_versions', 'exercise_daily_logs', 'exercise_checkins', 'exercise_plan_items',
      'exercise_plan_schedule_items', 'exercise_plan_diet_rules', 'exercise_plan_score_rules',
      'exercise_plan_category_rules', 'exercise_plan_progress_items', 'learning_objectives',
      'learning_krs', 'learning_tasks', 'user_wallets',
    ]
    for (const table of tables) {
      const columns = (db as any)._all(`PRAGMA table_info(${table})`)
      expect(columns.some((column: any) => column.name === 'pulled_at'), table).toBe(true)
    }
  })

  it('运动计划完整定义表纳入客户端同步白名单', () => {
    expect(SYNC_TABLES).toEqual(expect.arrayContaining([
      'exercise_plan_schedule_items',
      'exercise_plan_diet_rules',
      'exercise_plan_score_rules',
      'exercise_plan_category_rules',
      'exercise_plan_progress_items',
    ]))
  })

  it('客户端空库会初始化计时分类但不初始化学习和运动示例数据', () => {
    const isolated = createIsolatedDb()
    expect(isolated.getCategories()).toHaveLength(19)
    expect(isolated.allRaw("SELECT value FROM system_config WHERE key = 'timer_seed_initialized'")).toEqual([
      expect.objectContaining({ value: '1' }),
    ])
    expect(isolated.allRaw('SELECT * FROM learning_objectives')).toHaveLength(0)
    expect(isolated.allRaw('SELECT * FROM learning_krs')).toHaveLength(0)
    expect(isolated.allRaw('SELECT * FROM learning_tasks')).toHaveLength(0)
    expect(isolated.getActiveExercisePlanVersion()).toBe('v0')
    expect(isolated.getExercisePlanVersions()).toHaveLength(0)
    expect(isolated.getExercisePlanItems('周一', 'gym', 'v1')).toHaveLength(0)
  })

  it('运动计划完整定义来自数据库表', () => {
    const isolated = createIsolatedDb()
    isolated.runRaw("INSERT INTO exercise_plan_versions (version,title,source_name,is_active,exercise_points,created_at,updated_at) VALUES ('v1','每日打卡表','server-sync',1,57,datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_schedule_items (id,plan_version,schedule_type,sort_order,time,item,note,accent,created_at,updated_at) VALUES ('sched-v1-0','v1','weekday',0,'7:30','服务端日程','', 'default', datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_score_rules (id,plan_version,day_type,sort_order,schedule_index,points,category,target_time,created_at,updated_at) VALUES ('score-v1-0','v1','weekday',0,0,3,'作息',NULL,datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("UPDATE exercise_plan_versions SET exercise_points = 66 WHERE version = 'v1'")
    isolated.runRaw("UPDATE exercise_plan_schedule_items SET item = '数据库日程' WHERE plan_version = 'v1' AND schedule_type = 'weekday' AND sort_order = 0")
    isolated.runRaw("UPDATE exercise_plan_score_rules SET points = 9 WHERE plan_version = 'v1' AND day_type = 'weekday' AND sort_order = 0")
    const def = isolated.getExercisePlanDefinition('v1')

    expect(def.exercisePoints).toBe(66)
    expect(def.weekdaySchedule[0].item).toBe('数据库日程')
    expect(def.weekdayScore[0][1]).toBe(9)
  })

  it('V4 饮食规则必须唯一非空，并过滤空键打卡事实', () => {
    const isolated = createIsolatedDb()
    isolated.runRaw("INSERT INTO exercise_plan_versions (version,title,is_active,exercise_points,created_at,updated_at) VALUES ('v4','V4',1,75,'2026-09-12','2026-09-12')")
    for (const [index, key] of ['no_snacks', 'no_sugary_drinks', 'no_refined_staples'].entries()) {
      isolated.runRaw("INSERT INTO exercise_plan_diet_rules (id,plan_version,rule_key,sort_order,time,content,created_at,updated_at) VALUES (?,?,?,?,'全天',?,'2026-09-12','2026-09-12')", [`v4-diet-${index}`, 'v4', key, index, key])
    }
    isolated.runRaw("INSERT INTO exercise_diet_checkins (id,date,plan_version,rule_key,status,deadline_at,created_at,updated_at) VALUES ('diet-empty','2026-09-12','v4','','completed','2026-09-13','2026-09-12','2026-09-12')")
    isolated.runRaw("INSERT INTO exercise_diet_checkins (id,date,plan_version,rule_key,status,deadline_at,created_at,updated_at) VALUES ('diet-snacks','2026-09-12','v4','no_snacks','completed','2026-09-13','2026-09-12','2026-09-12')")

    expect(isolated.getExercisePlanDefinition('v4').dietRulesValid).toBe(true)
    expect(isolated.discardInvalidV4DietCheckins('2026-09-12', 'v4')).toBe(1)
    expect(isolated.getExerciseDietCheckins('2026-09-12', 'v4').map(row => row.rule_key)).toEqual(['no_snacks'])

    isolated.runRaw("UPDATE exercise_plan_diet_rules SET rule_key=NULL WHERE plan_version='v4'")
    const recovered = isolated.getExercisePlanDefinition('v4')
    expect(recovered.dietRulesValid).toBe(true)
    expect(recovered.diet.map(rule => rule.ruleKey)).toEqual(['no_snacks', 'no_sugary_drinks', 'no_refined_staples'])

    isolated.runRaw("INSERT INTO exercise_plan_diet_rules (id,plan_version,rule_key,sort_order,time,content,created_at,updated_at) VALUES ('v4-diet-duplicate','v4','no_snacks',3,'全天','重复','2026-09-12','2026-09-12')")
    expect(isolated.getExercisePlanDefinition('v4').dietRulesValid).toBe(false)
  })

  it('饮食中断事实仅补偿一次且既有服务端 ID 可单条同步', () => {
    const sqlDb = createBetterSqliteAdapter()
    const initial = new Database(sqlDb)
    const facts = [
      ['srv-diet-snacks', 'no_snacks', 'completed', '2026-09-12 11:00:00', '2026-09-12 10:00:00'],
      ['srv-diet-drinks', 'no_sugary_drinks', 'completed', '2026-09-12 11:10:00', '2026-09-12 10:00:00'],
      ['srv-diet-staples', 'no_refined_staples', 'pending', '2026-09-12 09:00:00', '2026-09-12 10:00:00'],
    ]
    facts.forEach(([id, ruleKey, status, updatedAt, pulledAt]) => initial.runRaw(
      `INSERT INTO exercise_diet_checkins
       (id,date,plan_version,rule_key,status,deadline_at,created_at,updated_at,pulled_at,pushed_at)
       VALUES (?,'2099-09-12','v4',?,?,'2099-09-13',?,?,?,NULL)`,
      [id, ruleKey, status, updatedAt, updatedAt, pulledAt],
    ))

    const recovered = new Database(sqlDb)
    const pending = recovered.getPendingOutbox(20).filter(item => item.table_name === 'exercise_diet_checkins')
    expect(pending.map(item => item.record_id).sort()).toEqual(['srv-diet-drinks', 'srv-diet-snacks'])
    expect(new Database(sqlDb).getPendingOutbox(20).filter(item => item.table_name === 'exercise_diet_checkins')).toHaveLength(2)

    recovered.markOutboxSynced(pending.map(item => item.id), '2026-09-12 12:30:00')
    expect(recovered.allRaw("SELECT id FROM exercise_diet_checkins WHERE pushed_at='2026-09-12 12:30:00' ORDER BY id").map(row => row.id))
      .toEqual(['srv-diet-drinks', 'srv-diet-snacks'])
    recovered.toggleExerciseDietCheckin('2099-09-12', 'no_refined_staples', 'failed', 'v4')
    const toggled = recovered.getPendingOutbox(20).filter(item => item.table_name === 'exercise_diet_checkins')
    expect(toggled.map(item => item.record_id)).toEqual(['srv-diet-staples'])
    expect(recovered.getExerciseDietCheckins('2099-09-12', 'v4').find(row => row.rule_key === 'no_refined_staples')).toMatchObject({ status: 'failed', failure_reason: 'user_marked_failed', penalty_source_id: null })
    recovered.toggleExerciseDietCheckin('2099-09-12', 'no_refined_staples', 'pending', 'v4')
    expect(recovered.getExerciseDietCheckins('2099-09-12', 'v4').find(row => row.rule_key === 'no_refined_staples')).toMatchObject({ status: 'pending', occurred_at: null, failure_reason: null })
  })

  it('活动运动版本只加载完整包并保留版本化打卡', () => {
    const isolated = createIsolatedDb()
    isolated.runRaw("INSERT INTO exercise_plan_versions (version,title,is_active,exercise_points,created_at,updated_at) VALUES ('v0','V0',1,63,datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_schedule_items (id,plan_version,schedule_type,sort_order,time,item,created_at,updated_at) VALUES ('v0-s','v0','weekday',0,'08:00','V0',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_score_rules (id,plan_version,day_type,sort_order,schedule_index,points,category,created_at,updated_at) VALUES ('v0-r','v0','weekday',0,0,3,'作息',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_category_rules (id,plan_version,sort_order,category,created_at,updated_at) VALUES ('v0-c','v0',0,'作息',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_items (id,plan_version,day_key,variant,section,sort_order,name,created_at,updated_at) VALUES ('v0-i','v0','周一','gym','无氧',0,'动作',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_versions (version,title,is_active,exercise_points,created_at,updated_at) VALUES ('v1','V1',1,63,datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_versions (version,title,is_active,exercise_points,created_at,updated_at) VALUES ('v2','V2',1,40,datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_schedule_items (id,plan_version,schedule_type,sort_order,time,item,created_at,updated_at) VALUES ('v1-s','v1','weekday',0,'08:00','V1',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_score_rules (id,plan_version,day_type,sort_order,schedule_index,points,category,created_at,updated_at) VALUES ('v1-r','v1','weekday',0,0,3,'作息',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_category_rules (id,plan_version,sort_order,category,created_at,updated_at) VALUES ('v1-c','v1',0,'作息',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_items (id,plan_version,day_key,variant,section,sort_order,name,created_at,updated_at) VALUES ('v1-i','v1','周一','gym','无氧',0,'动作',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("UPDATE exercise_plan_versions SET is_active=1, exercise_points=40 WHERE version='v2'")
    isolated.runRaw("INSERT INTO exercise_plan_schedule_items (id,plan_version,schedule_type,sort_order,time,item,created_at,updated_at) VALUES ('v2-s','v2','weekday',0,'7:30','日程',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_score_rules (id,plan_version,day_type,sort_order,schedule_index,points,category,created_at,updated_at) VALUES ('v2-r','v2','weekday',0,0,5,'检验',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_category_rules (id,plan_version,sort_order,category,created_at,updated_at) VALUES ('v2-c','v2',0,'检验',datetime('now','localtime'),datetime('now','localtime'))")
    isolated.runRaw("INSERT INTO exercise_plan_items (id,plan_version,day_key,variant,section,sort_order,name,created_at,updated_at) VALUES ('v2-i','v2','周一','gym','无氧',0,'动作',datetime('now','localtime'),datetime('now','localtime'))")
    expect(isolated.setActiveExercisePlanVersion('v2')).toEqual({ ok: false, error: 'exercise_plan_version_incomplete' })
    expect(isolated.getExercisePlanVersions().map(row => row.version)).toEqual(['v0', 'v1', 'v2'])
    for (let i=1;i<11;i++) isolated.runRaw(`INSERT INTO exercise_plan_schedule_items (id,plan_version,schedule_type,sort_order,time,item,created_at,updated_at) VALUES ('v2-s${i}','v2','weekday',${i},'08:00','日程',datetime('now','localtime'),datetime('now','localtime'))`)
    for (let i=1;i<90;i++) isolated.runRaw(`INSERT INTO exercise_plan_items (id,plan_version,day_key,variant,section,sort_order,name,created_at,updated_at) VALUES ('v2-i${i}','v2','周一','gym','无氧',${i},'动作',datetime('now','localtime'),datetime('now','localtime'))`)
    for (let i=0;i<4;i++) isolated.runRaw(`INSERT INTO exercise_plan_progress_items (id,plan_version,sort_order,when_text,text,created_at,updated_at) VALUES ('v2-p${i}','v2',${i},'阶段','进阶',datetime('now','localtime'),datetime('now','localtime'))`)
    for (let i=0;i<3;i++) isolated.runRaw(`INSERT INTO exercise_plan_diet_rules (id,plan_version,sort_order,time,content,note,created_at,updated_at) VALUES ('v2-d${i}','v2',${i},'时间','饮食','',datetime('now','localtime'),datetime('now','localtime'))`)
    for (let i=1;i<18;i++) isolated.runRaw(`INSERT INTO exercise_plan_score_rules (id,plan_version,day_type,sort_order,schedule_index,points,category,created_at,updated_at) VALUES ('v2-r${i}','v2','weekday',${i},0,1,'检验',datetime('now','localtime'),datetime('now','localtime'))`)
    for (let i=1;i<6;i++) isolated.runRaw(`INSERT INTO exercise_plan_category_rules (id,plan_version,sort_order,category,created_at,updated_at) VALUES ('v2-c${i}','v2',${i},'分类${i}',datetime('now','localtime'),datetime('now','localtime'))`)
    expect(isolated.setActiveExercisePlanVersion('v2')).toEqual({ ok: true })
    expect(isolated.getActiveExercisePlanVersion()).toBe('v2')
    const date = '2026-08-28'
    isolated.toggleExerciseCheckin(date, 'item', 1, undefined, '08:00', undefined, undefined, 'v0')
    isolated.toggleExerciseCheckin(date, 'item', 1, undefined, '09:00', undefined, undefined, 'v1')
    isolated.toggleExerciseCheckin(date, 'item', 1, undefined, '10:00', undefined, undefined, 'v2')
    isolated.runRaw("INSERT INTO exercise_plan_versions (version,title,source_name,is_active,exercise_points,created_at,updated_at) VALUES ('v3','每日打卡表','server-sync',1,40,datetime('now','localtime'),datetime('now','localtime'))")
    expect(isolated.setActiveExercisePlanVersion('v3')).toEqual({ ok: false, error: 'exercise_plan_version_incomplete' })
    expect(isolated.getExercisePlanVersions().map(row => row.version)).toEqual(['v0', 'v1', 'v2', 'v3'])
    expect(isolated.getActiveExercisePlanVersion()).toBe('v2')
    for (const [version, time] of [['v0', '08:00'], ['v1', '09:00'], ['v2', '10:00']] as const) {
      expect(isolated.setActiveExercisePlanVersion(version)).toEqual({ ok: true })
      expect(isolated.getExerciseCheckins(date, version)).toEqual([expect.objectContaining({ status: 1, completed_time: time })])
    }
  })

  it('已有同名学习目标时不重复初始化默认目标', () => {
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    sqlDb.run(
      `INSERT INTO learning_objectives (id,title,status,created_at,updated_at)
       VALUES ('user-ai-goal','全面了解AI发展脉络 + 掌握数据标注接单技能',0,datetime('now','localtime'),datetime('now','localtime'))`,
    )
    initSchema(sqlDb)
    const isolated = new Database(sqlDb)

    const objectives = isolated.allRaw(
      'SELECT id,title FROM learning_objectives WHERE title = ?',
      ['全面了解AI发展脉络 + 掌握数据标注接单技能'],
    )
    expect(objectives).toHaveLength(1)
    expect(objectives[0].id).toBe('user-ai-goal')
  })

  it('默认学习目标删除后再次初始化不复活', () => {
    const seedObjectiveId = '72fc7161-b6fb-4612-8d19-f90d1e0d94c3'
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    sqlDb.run('DELETE FROM learning_tasks')
    sqlDb.run('DELETE FROM learning_krs')
    sqlDb.run('DELETE FROM learning_objectives WHERE id = ?', [seedObjectiveId])
    initSchema(sqlDb)
    const isolated = new Database(sqlDb)
    const rows = isolated.allRaw('SELECT id FROM learning_objectives WHERE id = ?', [seedObjectiveId])

    expect(rows).toHaveLength(0)
    expect(isolated.allRaw('SELECT id FROM learning_krs')).toHaveLength(0)
    expect(isolated.allRaw('SELECT id FROM learning_tasks')).toHaveLength(0)
  })

  it('默认计时分类删除、停用或改名后再次初始化不复活', () => {
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    sqlDb.run("UPDATE categories SET name = '用户自定义运动' WHERE name = '运动'")
    sqlDb.run("UPDATE categories SET is_active = 0 WHERE name = '娱乐'")
    sqlDb.run("DELETE FROM categories WHERE name = '输入'")
    initSchema(sqlDb)
    const isolated = new Database(sqlDb)

    const renamed = isolated.allRaw("SELECT name FROM categories WHERE name = '运动'")
    const inactive = isolated.allRaw("SELECT is_active FROM categories WHERE name = '娱乐'")
    const deleted = isolated.allRaw("SELECT name FROM categories WHERE name = '输入'")

    expect(renamed).toHaveLength(0)
    expect(inactive[0].is_active).toBe(0)
    expect(deleted).toHaveLength(0)
  })

  it('已有分类但没有计时初始化标记时只补标记不补插默认分类', () => {
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    sqlDb.run('DELETE FROM categories')
    sqlDb.run("DELETE FROM system_config WHERE key = 'timer_seed_initialized'")
    sqlDb.run("INSERT INTO categories (name,icon,color,group_name,sort_order,is_active,created_at,updated_at) VALUES ('用户分类','atm:cat_96','#111111','自定义',1,1,datetime('now','localtime'),datetime('now','localtime'))")

    initSchema(sqlDb)
    const isolated = new Database(sqlDb)
    const categories = isolated.getCategories()

    expect(categories).toHaveLength(1)
    expect(categories[0].name).toBe('用户分类')
    expect(isolated.allRaw("SELECT value FROM system_config WHERE key = 'timer_seed_initialized'")).toEqual([
      expect.objectContaining({ value: '1' }),
    ])
  })

  it('服务端同步来的运动计划版本或动作删除后再次初始化不复活', () => {
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    sqlDb.run("INSERT INTO exercise_plan_versions (version,title,source_name,is_active,exercise_points,created_at,updated_at) VALUES ('v0','每日打卡表','server-sync',1,34,datetime('now','localtime'),datetime('now','localtime'))")
    sqlDb.run("INSERT INTO exercise_plan_items (id,plan_version,day_key,variant,section,sort_order,name,sets,intensity,tags_json,progression,color,is_active,created_at,updated_at) VALUES ('v0-item-0','v0','周一','gym','无氧',0,'服务端动作','1×1','测试','{}',NULL,'#000000',1,datetime('now','localtime'),datetime('now','localtime'))")
    const isolated = new Database(sqlDb)
    const firstItem = isolated.allRaw(
      "SELECT id FROM exercise_plan_items WHERE plan_version = 'v0' ORDER BY day_key, variant, sort_order LIMIT 1",
    )[0]
    expect(firstItem?.id).toBeTruthy()

    sqlDb.run('DELETE FROM exercise_plan_items WHERE id = ?', [firstItem.id])
    initSchema(sqlDb)
    expect(isolated.allRaw('SELECT id FROM exercise_plan_items WHERE id = ?', [firstItem.id])).toHaveLength(0)

    sqlDb.run("DELETE FROM exercise_plan_versions WHERE version = 'v0'")
    initSchema(sqlDb)
    expect(isolated.allRaw("SELECT version FROM exercise_plan_versions WHERE version = 'v0'")).toHaveLength(0)
  })

  it('旧运动计划初始化标记存在时不在客户端补齐示例计划且保留每日数据', () => {
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    sqlDb.run("INSERT OR REPLACE INTO system_config (key,value,value_type,description,updated_at) VALUES ('exercise_seed_initialized_v1','1','string','legacy marker',datetime('now','localtime'))")
    sqlDb.run(
      `INSERT OR REPLACE INTO exercise_daily_logs
        (id,date,plan_version,week_num,day_name,weight,completed_items,total_items,score_snapshot,created_at,updated_at)
       VALUES ('legacy-daily','2026-07-02','v1',1,'周二',80.5,2,9,'{"total":22}',datetime('now','localtime'),datetime('now','localtime'))`,
    )
    sqlDb.run(
      `INSERT OR REPLACE INTO exercise_checkins
        (id,date,plan_version,item_key,status,completed_time,item_name,created_at,updated_at)
       VALUES ('legacy-checkin','2026-07-02','v1','sc-2026-07-02-0',1,'07:20','起床',datetime('now','localtime'),datetime('now','localtime'))`,
    )

    initSchema(sqlDb)
    const isolated = new Database(sqlDb)

    expect(isolated.allRaw("SELECT * FROM exercise_plan_versions WHERE version = 'v1'")).toHaveLength(0)
    expect(isolated.allRaw("SELECT * FROM exercise_plan_items WHERE plan_version = 'v1'")).toHaveLength(0)
    expect(isolated.allRaw("SELECT * FROM exercise_daily_logs WHERE id = 'legacy-daily'")[0]).toMatchObject({
      weight: 80.5,
      completed_items: 2,
      total_items: 9,
    })
    expect(isolated.allRaw("SELECT * FROM exercise_checkins WHERE id = 'legacy-checkin'")).toHaveLength(1)
  })

  it('运动计划按版本追加，不覆盖 v0 数据', () => {
    const sqlDb = createBetterSqliteAdapter()
    initSchema(sqlDb)
    const isolated = new Database(sqlDb)
    isolated.upsertExercisePlanItem({
      id: 'v0-custom-item',
      plan_version: 'v0',
      day_key: '周一',
      variant: 'gym',
      section: '无氧',
      sort_order: 0,
      name: '旧版动作',
      sets: '1×1',
      intensity: '测试',
      tags_json: '{}',
      progression: null,
      color: '#111111',
    })
    isolated.upsertExercisePlanItem({
      id: 'v1-custom-item',
      plan_version: 'v1',
      day_key: '周一',
      variant: 'gym',
      section: '无氧',
      sort_order: 0,
      name: '新版动作',
      sets: '1×1',
      intensity: '测试',
      tags_json: '{}',
      progression: null,
      color: '#000000',
    })

    expect(isolated.getExercisePlanItems('周一', 'gym', 'v1')[0].name).toBe('新版动作')
    expect(isolated.getExercisePlanItems('周一', 'gym', 'v0').some(item => item.name === '新版动作')).toBe(false)
    sqlDb.run("UPDATE system_config SET value = '1' WHERE key = 'exercise_seed_initialized_v1'")
    initSchema(sqlDb)
    expect(isolated.getExercisePlanItems('周一', 'gym', 'v1')).toHaveLength(1)
  })

  it('运动历史日期不可补卡且当日可保存快照', () => {
    const isolated = createIsolatedDb()
    const today = new Date()
    const bj = new Date(today.getTime() + today.getTimezoneOffset() * 60000 + 8 * 3600000)
    const todayText = `${bj.getFullYear()}-${String(bj.getMonth() + 1).padStart(2, '0')}-${String(bj.getDate()).padStart(2, '0')}`
    isolated.toggleExerciseCheckin(todayText, `sc-${todayText}-0`, 1, undefined, '08:00', null, '早餐', 'v0')
    expect(isolated.getExerciseCheckins(todayText, 'v0')).toHaveLength(1)
    isolated.upsertExerciseDailyLog(todayText, 1, '周一', 80, 1, 2, 'v0', { total: 5 })
    expect(isolated.getExerciseDailyLog(todayText, 'v0').score_snapshot).toContain('"total":5')

    isolated.toggleExerciseCheckin('2020-01-01', 'sc-2020-01-01-0', 1, undefined, '08:00', null, '历史补卡', 'v0')
    expect(isolated.getExerciseCheckins('2020-01-01', 'v0')).toHaveLength(0)
  })

  it('体重和体脂率可联合保存且仅在所属版本读取并进入 outbox', () => {
    const isolated = createIsolatedDb()
    const today = new Date()
    const bj = new Date(today.getTime() + today.getTimezoneOffset() * 60000 + 8 * 3600000)
    const date = `${bj.getFullYear()}-${String(bj.getMonth() + 1).padStart(2, '0')}-${String(bj.getDate()).padStart(2, '0')}`
    isolated.upsertExerciseDailyLog(date, 1, '周一', 80.5, 0, 7, 'v0', undefined, 'gym', 21.5)
    expect(isolated.getExerciseDailyLog(date, 'v0')).toMatchObject({ weight: 80.5, body_fat_rate: 21.5 })
    expect(isolated.getExerciseDailyLog(date, 'v1')).toBeUndefined()
    const outbox = isolated.getPendingOutbox(20).find(item => item.table_name === 'exercise_daily_logs')
    expect(outbox).toBeTruthy()
    expect(JSON.parse(outbox!.payload_json)).toMatchObject({ weight: 80.5, body_fat_rate: 21.5 })
    isolated.upsertExerciseDailyLog(date, 1, '周一', undefined, 0, 7, 'v0', undefined, 'gym', 22)
    expect(isolated.getExerciseDailyLog(date, 'v0')).toMatchObject({ weight: 80.5, body_fat_rate: 22 })
  })

  it('V4 不得用同日旧版本的身体数据或评分快照补齐空状态', () => {
    const isolated = createIsolatedDb()
    const date = '2026-09-09'
    isolated.runRaw(`INSERT INTO exercise_daily_logs
      (id,date,plan_version,week_num,day_name,weight,body_fat_rate,completed_items,total_items,score_snapshot,created_at,updated_at)
      VALUES ('v2-only',?,'v2',1,'周三',100,30.7,2,5,?, '2026-09-09 08:00:00','2026-09-09 08:00:00')`, [
      date,
      JSON.stringify({ total: 40, cats: { 守时: { s: 5, m: 5 } } }),
    ])

    expect(isolated.getExerciseDailyLog(date, 'v4')).toBeUndefined()
    expect(isolated.getExerciseDailyLog(date, 'v2')).toMatchObject({ weight: 100, body_fat_rate: 30.7 })
  })

  it('运动流水按打卡来源读取名称，缺少名称时稳定返回空值', () => {
    const isolated = createIsolatedDb()
    isolated.runRaw(
      `INSERT INTO exercise_checkins (id,date,plan_version,item_key,status,item_name,created_at,updated_at)
       VALUES ('exercise-ledger-title','2026-07-25','v0','sc-2026-07-25-0',1,'慢跑 30 分钟','2026-07-25 08:00:00','2026-07-25 08:00:00')`,
    )

    expect(isolated.getExerciseCheckinTitle('2026-07-25', 'exercise-ledger-title')).toBe('慢跑 30 分钟')
    expect(isolated.getExerciseCheckinTitle('2026-07-25', 'missing-checkin')).toBeNull()
  })

  it('同日身体数据和历史评分均按计划版本隔离', () => {
    const isolated = createIsolatedDb()
    const today = new Date()
    const bj = new Date(today.getTime() + today.getTimezoneOffset() * 60000 + 8 * 3600000)
    const todayText = `${bj.getFullYear()}-${String(bj.getMonth() + 1).padStart(2, '0')}-${String(bj.getDate()).padStart(2, '0')}`
    isolated.upsertExerciseDailyLog(todayText, 1, '周一', 80.5, 1, 2, 'v0', { total: 88, cats: { 运动: { s: 40, m: 57 } } })

    const v1Log = isolated.getExerciseDailyLog(todayText, 'v1')

    expect(v1Log).toBeUndefined()
    expect(isolated.getExerciseCheckins(todayText, 'v1')).toHaveLength(0)

    const pastDate = '2020-01-01'
    isolated.runRaw(
      `INSERT INTO exercise_daily_logs (
        id, date, plan_version, week_num, day_name, weight, completed_items, total_items,
        score_snapshot, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        'past-v0-daily',
        pastDate,
        'v0',
        1,
        '周三',
        79.2,
        2,
        3,
        JSON.stringify({ total: 91, cats: { 运动: { s: 52, m: 57 } } }),
        '2020-01-01 23:59:00',
        '2020-01-01 23:59:00',
      ],
    )
    expect(isolated.getExerciseDailyLog(pastDate, 'v1')).toBeUndefined()
  })

  it('历史日期允许补体重但不改锁定评分', () => {
    const isolated = createIsolatedDb()
    const pastDate = '2020-01-02'
    isolated.runRaw(
      `INSERT INTO exercise_daily_logs (
        id, date, plan_version, week_num, day_name, weight, completed_items, total_items,
        score_snapshot, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        'locked-score-daily',
        pastDate,
        'v0',
        1,
        '周四',
        null,
        1,
        5,
        JSON.stringify({ total: 22, cats: { 运动: { s: 12, m: 57 } } }),
        '2020-01-02 23:59:00',
        '2020-01-02 23:59:00',
      ],
    )

    isolated.upsertExerciseDailyLog(pastDate, 1, '周四', 78.6, 5, 5, 'v0', { total: 100 })

    const log = isolated.getExerciseDailyLog(pastDate, 'v0')
    expect(log.weight).toBe(78.6)
    expect(log.completed_items).toBe(1)
    expect(JSON.parse(log.score_snapshot).total).toBe(22)
  })

  it('outbox 成功后才更新业务记录 pushed_at', () => {
    const isolated = createIsolatedDb()
    const id = isolated.addCategory('推送时间测试', 'T', '#000', '输入')
    const outbox = isolated.getPendingOutbox(10).find(item => item.table_name === 'categories' && item.record_id === String(id))
    expect(outbox).toBeTruthy()
    expect((isolated as any)._get('SELECT pushed_at FROM categories WHERE id = ?', [id]).pushed_at).toBeNull()

    isolated.markOutboxSynced([outbox!.id], '2026-06-19 13:00:00')

    expect((isolated as any)._get('SELECT pushed_at FROM categories WHERE id = ?', [id]).pushed_at).toBe('2026-06-19 13:00:00')
  })

  it('恢复进程中断遗留的 sending outbox', () => {
    const isolated = createIsolatedDb()
    const id = isolated.addCategory('强杀恢复', 'R', '#000', '输入')
    const outbox = isolated.getPendingOutbox(10).find(item => item.record_id === String(id))!
    isolated.markOutboxSending([outbox.id])
    expect(isolated.getPendingOutbox(10).some(item => item.id === outbox.id)).toBe(false)
    expect(isolated.recoverInterruptedOutboxSending()).toBe(1)
    expect(isolated.getPendingOutbox(10).find(item => item.id === outbox.id)?.status).toBe('pending')
  })

  it('aTimeLogger 同步开关默认关闭', () => {
    expect(db.getConfig('atimelogger_enabled')).toBe('false')
  })

  it('aTimeLogger 映射表可保存查询删除', () => {
    const sessionId = 'test-atimelogger-session'
    const id = db.upsertATimeLoggerSegment({
      localSessionId: sessionId,
      localCategoryId: 1,
      atimeloggerTypeId: 'type-1',
      atimeloggerActivityId: 'activity-1',
      atimeloggerIntervalId: 'interval-1',
      remoteStatus: 'stopped',
      syncState: 'synced',
    })

    expect(id).toBeGreaterThan(0)
    const segments = db.getATimeLoggerSegmentsForSession(sessionId)
    expect(segments).toHaveLength(1)
    expect(segments[0].atimelogger_activity_id).toBe('activity-1')

    db.markATimeLoggerSegmentError(sessionId, '测试错误')
    expect(db.getATimeLoggerSegmentsForSession(sessionId)[0].sync_state).toBe('failed')

    db.deleteATimeLoggerSegmentsForSession(sessionId)
    expect(db.getATimeLoggerSegmentsForSession(sessionId)).toHaveLength(0)
  })

  it('aTimeLogger 映射表支持同一本地会话多条 segment', () => {
    const sessionId = 'test-atimelogger-multi-segment'
    db.upsertATimeLoggerSegment({
      localSessionId: sessionId,
      localSegmentKey: 'segment:1',
      localCategoryId: 1,
      atimeloggerTypeId: 'type-1',
      atimeloggerActivityId: 'activity-1',
      atimeloggerIntervalId: 'interval-1',
      remoteStatus: 'stopped',
      syncState: 'synced',
    })
    db.upsertATimeLoggerSegment({
      localSessionId: sessionId,
      localSegmentKey: 'segment:2',
      localCategoryId: 1,
      atimeloggerTypeId: 'type-1',
      atimeloggerActivityId: 'activity-2',
      atimeloggerIntervalId: 'interval-2',
      remoteStatus: 'stopped',
      syncState: 'synced',
    })

    const segments = db.getATimeLoggerSegmentsForSession(sessionId)
    expect(segments).toHaveLength(2)
    expect(segments.map(s => s.local_segment_key)).toEqual(['segment:1', 'segment:2'])
    expect(segments.map(s => s.atimelogger_activity_id)).toEqual(['activity-1', 'activity-2'])

    db.deleteATimeLoggerSegmentsForSession(sessionId)
  })

  it('aTimeLogger 可按单个 segment 标记删除并清理映射', () => {
    const sessionId = 'test-atimelogger-single-segment-delete'
    db.upsertATimeLoggerSegment({
      localSessionId: sessionId,
      localSegmentKey: 'segment:1',
      localCategoryId: 1,
      atimeloggerTypeId: 'type-1',
      atimeloggerActivityId: 'activity-1',
      atimeloggerIntervalId: 'interval-1',
      remoteStatus: 'stopped',
      syncState: 'synced',
    })
    db.upsertATimeLoggerSegment({
      localSessionId: sessionId,
      localSegmentKey: 'segment:2',
      localCategoryId: 1,
      atimeloggerTypeId: 'type-1',
      atimeloggerActivityId: 'activity-2',
      atimeloggerIntervalId: 'interval-2',
      remoteStatus: 'stopped',
      syncState: 'synced',
    })

    db.markATimeLoggerSegmentState(sessionId, 'segment:1', 'pending_delete')
    const pending = db.getATimeLoggerPendingSegments().filter(s => s.local_session_id === sessionId)
    expect(pending).toHaveLength(1)
    expect(pending[0].local_segment_key).toBe('segment:1')

    db.deleteATimeLoggerSegment(sessionId, 'segment:1')
    const remaining = db.getATimeLoggerSegmentsForSession(sessionId)
    expect(remaining).toHaveLength(1)
    expect(remaining[0].local_segment_key).toBe('segment:2')

    db.deleteATimeLoggerSegmentsForSession(sessionId)
  })

  it('aTimeLogger 失败队列可查询并保留已有远端 ID 防止重复创建', () => {
    const sessionId = 'test-atimelogger-retry-idempotent'
    db.upsertATimeLoggerSegment({
      localSessionId: sessionId,
      localSegmentKey: 'segment:1',
      localCategoryId: 1,
      atimeloggerTypeId: 'type-1',
      atimeloggerActivityId: 'activity-existing',
      atimeloggerIntervalId: 'interval-existing',
      remoteStatus: 'stopped',
      syncState: 'failed',
      lastError: 'network',
    })

    const pending = db.getATimeLoggerPendingSegments().filter(s => s.local_session_id === sessionId)
    expect(pending).toHaveLength(1)
    expect(pending[0].atimelogger_activity_id).toBe('activity-existing')
    expect(pending[0].atimelogger_interval_id).toBe('interval-existing')

    db.markATimeLoggerSegmentState(sessionId, 'segment:1', 'pending_update', 'stopped')
    const row = db.getATimeLoggerSegment(sessionId, 'segment:1')
    expect(row?.sync_state).toBe('pending_update')
    expect(row?.atimelogger_activity_id).toBe('activity-existing')

    db.deleteATimeLoggerSegmentsForSession(sessionId)
  })

  it('aTimeLogger 分类映射与重新登录标记保存到统一配置', () => {
    db.setConfig('atimelogger_type_map', JSON.stringify({ 输入: 'type-input' }))
    db.setConfig('atimelogger_unmatched_categories', JSON.stringify(['运动']))
    db.setConfig('atimelogger_auth_required', 'true')

    expect(db.getConfig('atimelogger_type_map')).toContain('type-input')
    expect(db.getConfig('atimelogger_unmatched_categories')).toContain('运动')
    expect(db.getConfig('atimelogger_auth_required')).toBe('true')
  })

  it('余额查询', () => {
    const balance = db.getBalance()
    expect(typeof balance).toBe('number')
  })

  it('金币汇总从全量流水计算余额收入支出', () => {
    const isolated = createIsolatedDb()
    isolated.addLedgerEntry(8, 'manual_summary', 'income', '收入', '2026-06-18')
    isolated.addLedgerEntry(-10, 'manual_summary', 'expense-a', '支出A', '2026-06-18')
    isolated.addLedgerEntry(-6, 'manual_summary', 'expense-b', '支出B', '2026-06-18')

    expect(isolated.getLedgerSummary()).toEqual({ balance: -8, income: 8, expense: 16 })
  })

  it('服务端账本快照原子替换孤儿流水并保存权威汇总', () => {
    const isolated = createIsolatedDb()
    isolated.addLedgerEntry(-3, 'goal_penalty', 'orphan', '旧本地惩罚', '2026-08-04')
    const result = isolated.replaceServerLedgerSnapshot({
      rows: [{ id: 'server-income', amount: 2, source_type: 'habit_checkin', target_date: '2026-08-04', created_at: '2026-08-04 10:00:00' }],
      summary: { balance: 2, income: 2, expense: 0 }, integrity: { count: 1, sha256: 'a'.repeat(64) },
    }, 88)

    expect(result).toEqual({ removed: 1, balance: 2 })
    expect(isolated.getLedgerSummary()).toEqual({ balance: 2, income: 2, expense: 0 })
    expect(isolated.getConfig('wallet_balance')).toBe('2')
    expect(isolated.allRaw("SELECT value FROM client_sync_state WHERE key='ledger_snapshot_version'")[0].value).toBe('88')
    expect(isolated.allRaw("SELECT * FROM sync_outbox WHERE table_name='reward_ledger' AND status IN ('pending','failed','sending')")).toHaveLength(0)
    expect(isolated.hasConsistentLedgerSnapshot()).toBe(true)
    isolated.addLedgerEntry(1, 'goal_reward', 'local', '本地回灌', '2026-08-05')
    expect(isolated.hasConsistentLedgerSnapshot()).toBe(false)
  })

  it('读取待领奖励不会在本地结算目标', () => {
    const isolated = createIsolatedDb()
    isolated.autoSettleGoals()
    expect(isolated.getUnclaimedRewards()).toEqual([])
    expect(isolated.allRaw("SELECT * FROM reward_ledger WHERE source_type IN ('goal_reward','goal_penalty')")).toHaveLength(0)
  })

  it('服务端账本汇总不匹配时保留原有流水', () => {
    const isolated = createIsolatedDb()
    isolated.addLedgerEntry(-1, 'goal_penalty', 'orphan', '旧本地惩罚', '2026-08-04')

    expect(() => isolated.replaceServerLedgerSnapshot({
      rows: [{ id: 'server-income', amount: 2, source_type: 'habit_checkin' }],
      summary: { balance: 3, income: 2, expense: 0 }, integrity: { count: 1, sha256: 'a'.repeat(64) },
    }, 88)).toThrow('invalid_server_ledger_snapshot')
    expect(isolated.getLedgerSummary()).toEqual({ balance: -1, income: 0, expense: 1 })
  })

  it('金币余额读取会用流水汇总修正陈旧快照', () => {
    const isolated = createIsolatedDb()
    isolated.addLedgerEntry(-10, 'manual_balance', 'expense-a', '支出A', '2026-06-18')
    isolated.addLedgerEntry(-6, 'manual_balance', 'expense-b', '支出B', '2026-06-18')
    isolated.setConfig('wallet_balance', '0')

    expect(isolated.getBalance()).toBe(-16)
    expect(isolated.getConfig('wallet_balance')).toBe('-16')
  })

  it('金币余额读取会保留与流水一致的有效快照', () => {
    const isolated = createIsolatedDb()
    isolated.addLedgerEntry(3, 'manual_balance', 'income-a', '收入A', '2026-06-18')
    isolated.setConfig('wallet_balance', '3')

    expect(isolated.getBalance()).toBe(3)
    expect(isolated.getConfig('wallet_balance')).toBe('3')
  })

  it('空金币流水汇总为 0', () => {
    const isolated = createIsolatedDb()

    expect(isolated.getLedgerSummary()).toEqual({ balance: 0, income: 0, expense: 0 })
    expect(isolated.getBalance()).toBe(0)
  })

  it('金币流水删除及余额重新计算', () => {
    const initialBalance = db.getBalance()

    // 插入一条 10 金币的流水，使用唯一的 source_id 避免冲突
    const id = db.addLedgerEntry(10, 'habit_checkin', 'test_delete_123', '测试增加金币', '2026-06-01')
    expect(id).toBeTruthy()
    expect(db.getBalance()).toBe(initialBalance + 10)

    // 删除该条流水
    const success = db.deleteLedgerEntry(id as any)
    expect(success).toBe(true)
    expect(db.getBalance()).toBe(initialBalance)

    // 确认流水已在表中物理删除
    const entries = db.getLedgerFull(100)
    expect(entries.find(e => e.id === id)).toBeUndefined()
  })

  it('领取外部奖励会同步领取状态和金币流水', () => {
    const queued: Array<{ table: string; id: number | string }> = []
    db.setEnqueue((table, id) => queued.push({ table, id }))

    db.addExternalReward('test_claim_sync_123', 'habit', '测试领取同步', 1)
    queued.length = 0

    const reward = (db as any)._get('SELECT id FROM external_rewards WHERE ext_id = ?', ['test_claim_sync_123'])
    const claimed = db.claimRewards([reward.id])

    expect(claimed).toBe(1)
    expect(queued.some(item => item.table === 'external_rewards' && item.id === reward.id)).toBe(true)
    expect(queued.some(item => item.table === 'reward_ledger')).toBe(true)
  })

  it('旧 external_rewards 表缺少 ext_id 时初始化会补齐兼容字段', () => {
    const sqlDb = createBetterSqliteAdapter()
    sqlDb.run(`
      CREATE TABLE external_rewards (
        id TEXT PRIMARY KEY,
        item_type TEXT NOT NULL,
        item_name TEXT NOT NULL,
        coins REAL NOT NULL DEFAULT 0,
        status INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
      )
    `)
    sqlDb.run(
      `INSERT INTO external_rewards (id, item_type, item_name, coins, status, created_at)
       VALUES ('legacy-ext-1', 'goal', '旧目标奖励', 2, 0, '2026-06-06 00:00:00')`
    )

    initSchema(sqlDb)
    const migrated = new Database(sqlDb)
    const row = (migrated as any)._get('SELECT ext_id FROM external_rewards WHERE id = ?', ['legacy-ext-1'])

    expect(row.ext_id).toBe('legacy-ext-1')
    expect(() => migrated.getUnclaimedRewards()).not.toThrow()
  })

  it('习惯状态切换不在客户端修改最终奖励流水', () => {
    const hid = db.addHabit('跨天测试', '🧪', 'easy')
    db.addLedgerEntry(1, 'habit_checkin', hid as any, '六月三日', '2026-06-03')
    db.addLedgerEntry(1, 'habit_checkin', hid as any, '六月四日', '2026-06-04')
    db.toggleCheckin(hid as any, '2026-06-03')
    db.toggleCheckin(hid as any, '2026-06-03')

    const rows = db.getLedgerFull(100).filter(e =>
      String(e.source_id) === String(hid) && e.source_type === 'habit_checkin'
    )
    expect(rows.some(e => (e as any).target_date === '2026-06-03')).toBe(true)
    expect(rows.some(e => (e as any).target_date === '2026-06-04')).toBe(true)
  })

  it('同一来源在不同归属日可以产生多条合法流水', () => {
    const id1 = db.addLedgerEntry(1, 'manual_same_source', 'shared', '第一次', '2026-06-03')
    const id2 = db.addLedgerEntry(2, 'manual_same_source', 'shared', '第二次', '2026-06-04')
    const rows = db.getLedgerFull(100).filter(e => e.source_type === 'manual_same_source')

    expect(id2).not.toBe(id1)
    expect(rows).toHaveLength(2)
  })

  it('保存服务端睡眠结果时忽略非本地表字段并保留报告渲染字段', () => {
    db.saveSleepData('', {
      sleep_date: '2026-06-25',
      sleep_score: 81,
      analysis_html: '<h1>extra</h1>',
      extracted_by: 'model',
      analysis: { summary: 'extra' },
    } as any)

    const row = db.getSleepData('2026-06-25') as any
    expect(row.sleep_score).toBe(81)
    expect(row.sleep_date).toBeUndefined()
    expect(row.analysis_html).toBe('<h1>extra</h1>')
    expect(row.extracted_by).toBeUndefined()
  })
})
