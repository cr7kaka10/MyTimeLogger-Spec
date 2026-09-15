/**
 * 逻辑层 E2E 演示脚本
 * 读取 PC 端 my_time_logger.db，用 TypeScript 逻辑层操作
 *
 * 用法: npx tsx e2e_demo.ts [数据库路径]
 */

import { createBetterSqliteAdapter } from './models/BetterSqliteAdapter'
import { Database } from './models/Database'
import { LogicEngine } from './core/LogicEngine'
import { resolve, SyncAction } from './core/SyncResolver'
import { EventBus } from './core/EventBus'
import * as fs from 'fs'
import * as path from 'path'

async function main() {
  // 1. 找到 PC 端数据库
  const dbPath = process.argv[2] || path.resolve('../desktop/local_data/my_time_logger.db')
  console.log(`📂 数据库: ${dbPath}`)
  console.log(`   文件大小: ${(fs.statSync(dbPath).size / 1024).toFixed(1)} KB`)

  // 2. 读取并加载
  const sqlDb = createBetterSqliteAdapter(dbPath)
  const db = new Database(sqlDb)

  // 3. 验证数据
  console.log('\n── 数据盘点 ──')

  const cats = db.getCategories()
  console.log(`\n📁 分类: ${cats.length} 个`)
  cats.slice(0, 5).forEach(c => console.log(`   ${c.icon} ${c.name} (${c.group_name})`))
  if (cats.length > 5) console.log(`   ... 还有 ${cats.length - 5} 个`)

  const sessions = db.getAvailableDates(90)
  console.log(`\n📅 有数据的日期: ${sessions.length} 天`)
  sessions.slice(0, 5).forEach(d => {
    const recs = db.getSessionsByDate(d)
    const totalMin = recs.reduce((s, r) => s + (r.net_duration_minutes || 0), 0)
    console.log(`   ${d}: ${recs.length} 条会话, 共 ${totalMin.toFixed(0)} 分钟`)
  })

  const habits = db.getHabits()
  const today = new Date().toISOString().slice(0, 10)
  const todayCheckins = db.getTodayCheckins(today)
  console.log(`\n✅ 习惯: ${habits.length} 个, 今日打卡: ${todayCheckins.length} 次`)
  habits.slice(0, 3).forEach(h => console.log(`   ${h.icon} ${h.title} (${h.difficulty})`))

  const goals = db.getGoals()
  console.log(`\n🎯 目标: ${goals.length} 个`)
  goals.forEach(g => console.log(`   ${g.title}: ${g.metric} ${g.operator} ${g.target_value}/${g.period}`))

  const balance = db.getBalance()
  console.log(`\n💰 金币余额: ${balance.toFixed(1)}`)

  const sleep = db.getSleepData(today)
  if (sleep) {
    console.log(`\n🌙 今日睡眠: 评分 ${sleep.sleep_score ?? '?'}, 总时长 ${sleep.total_sleep_min ?? '?'}min`)
  }

  // 4. 状态机演示
  console.log('\n── 状态机演示 ──')
  const engine = new LogicEngine({ studyTimeMin: 2, studyTimeMax: 2 })
  const events: string[] = []

  engine.setCallbacks({
    onStateChange: (label, state) => events.push(`  [${state}] ${label}`),
    onTick: () => {},
    onAudioCue: (cue) => events.push(`  🔊 ${cue}`),
    onSummaryRequested: () => {},
    onPauseReasonRequested: () => {},
    onSessionCommitted: (r) => {
      events.push(`  💾 会话提交: ${r.date} ${r.netDurationMinutes.toFixed(1)}min category=${r.categoryId}`)
    },
  })

  console.log(`  初始: ${engine.state}`)
  engine.start(1, '输入', '编程')
  console.log(`  启动: ${engine.state} (第${engine.cycleCount}轮)`)

  engine.togglePause()
  console.log(`  暂停: isPaused=${engine.isPaused}`)

  engine.togglePause()
  console.log(`  恢复: isPaused=${engine.isPaused}`)

  const record = engine.submitSummary('逻辑层 E2E 测试')
  if (record) {
    const savedId = db.logSession({
      startTime: record.startTime,
      endTime: record.endTime,
      netDurationMinutes: record.netDurationMinutes,
      date: record.date,
      dayOfWeek: record.dayOfWeek,
      pauseCount: record.pauseCount,
      pauseReasons: record.pauseReasons,
      sessionSummary: record.sessionSummary,
      categoryId: record.categoryId,
    })
    console.log(`  落库: id=${savedId}`)
  }

  // 5. SyncResolver 验证
  console.log('\n── LWW 仲裁验证 ──')
  console.log(`  仅服务端有 → ${resolve(null, { id: 1, updated_at: '2026-01-01' })}`)
  console.log(`  仅本地有   → ${resolve({ id: 1, updated_at: '2026-01-01', pushed_at: '2026-01-01' }, null)}`)
  console.log(`  服务端更新 → ${resolve(
    { id: 1, updated_at: '2026-01-01', pushed_at: '2026-01-01' },
    { id: 1, updated_at: '2026-06-01' },
  )}`)
  console.log(`  本地更新   → ${resolve(
    { id: 1, updated_at: '2026-06-01', pushed_at: '2026-01-01' },
    { id: 1, updated_at: '2026-01-01' },
  )}`)

  // 6. EventBus 演示
  console.log('\n── EventBus 演示 ──')
  const bus = new EventBus()
  bus.on('test:event', (msg: string) => console.log(`  📡 收到: ${msg}`))
  bus.emit('test:event', 'hello from EventBus')

  sqlDb.close()
  console.log('\n✅ 逻辑层 E2E 验证完成')
}

main().catch(e => {
  console.error('❌', e)
  process.exit(1)
})
