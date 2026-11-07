import { describe, expect, it } from 'vitest'
import { Database } from '../models/Database'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'

describe('goal summary period projection', () => {
  it('shows added and edited weekly goals, then hides deletion only from its effective day', () => {
    const db = new Database(createBetterSqliteAdapter())
    expect(db.getSummaryGoalsForDate('2026-10-31')).toHaveLength(0)
    db.runRaw("INSERT INTO goals(id,title,category_id,metric,target_value,period,created_at,updated_at) VALUES('g','周目标',1,'duration',60,'weekly','2026-10-29 09:00:00','2026-10-29 09:00:00')")
    db.runRaw("INSERT INTO study_sessions(id,start_time,end_time,net_duration_minutes,date,category_id) VALUES('s1','2026-10-30 09:00:00','2026-10-30 09:30:00',30,'2026-10-30',1)")
    db.runRaw("INSERT INTO study_sessions(id,start_time,end_time,net_duration_minutes,date,category_id) VALUES('s2','2026-10-31 09:00:00','2026-10-31 09:45:00',45,'2026-10-31',1)")
    expect(db.getSummaryGoalsForDate('2026-10-31')[0]).toMatchObject({ current: 75, target: 60, periodKey: '2026W44' })
    db.runRaw("UPDATE goals SET title='更新周目标',target_value=90,updated_at='2026-10-31 10:00:00' WHERE id='g'")
    expect(db.getSummaryGoalsForDate('2026-10-31')[0]).toMatchObject({ title: '更新周目标', target: 90 })
    db.runRaw("UPDATE goals SET is_active=0,updated_at='2026-10-31 11:00:00' WHERE id='g'")
    expect(db.getSummaryGoalsForDate('2026-10-31')).toHaveLength(0)
    expect(db.getSummaryGoalsForDate('2026-10-30')[0]).toMatchObject({ current: 30 })
  })

  it('keeps custom weekday rest days empty and projects each session separately', () => {
    const db = new Database(createBetterSqliteAdapter())
    db.runRaw("INSERT INTO goals(id,title,category_id,metric,target_value,period,weekdays,created_at) VALUES('rest','周一执行',1,'duration',10,'custom_weekdays','[1]','2026-10-01')")
    db.runRaw("INSERT INTO goals(id,title,category_id,metric,target_value,period,created_at) VALUES('single','每次目标',1,'duration',10,'per_session','2026-10-01')")
    for (const id of ['a', 'b']) db.runRaw('INSERT INTO study_sessions(id,start_time,end_time,net_duration_minutes,date,category_id) VALUES(?,?,?,?,?,1)', [id, '2026-10-31 09:00:00', '2026-10-31 09:20:00', 20, '2026-10-31'])
    const rows = db.getSummaryGoalsForDate('2026-10-31')
    expect(rows.some(row => row.id === 'rest')).toBe(false)
    expect(rows.filter(row => row.id === 'single').map(row => row.periodKey)).toEqual(['session_a', 'session_b'])
  })
})
