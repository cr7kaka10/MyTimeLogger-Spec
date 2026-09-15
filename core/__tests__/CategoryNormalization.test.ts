import { describe, expect, it } from 'vitest'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { Database } from '../models/Database'
import { SyncWorker } from '../core/SyncWorker'

const createDb = () => new Database(createBetterSqliteAdapter())

describe('category normalization', () => {
  it('migrates duplicate references without changing another account database', () => {
    const accountA = createDb(); const accountB = createDb()
    accountA.runRaw(`INSERT INTO categories (name, icon, color, group_name, sort_order, is_active, created_at) VALUES ('输入', '📖', '#000', '增益', 99, 1, '2026-07-28 00:00:00')`)
    const duplicateId = Number(accountA.allRaw("SELECT id FROM categories WHERE name = '输入' ORDER BY id DESC LIMIT 1")[0].id)
    accountA.logSession({ startTime: '2026-07-28 09:00:00', endTime: '2026-07-28 09:30:00', netDurationMinutes: 30, date: '2026-07-28', categoryId: duplicateId })

    expect(accountA.previewCategoryNormalization()).toEqual([expect.objectContaining({ canonicalId: 1, duplicateIds: [duplicateId], referenceCounts: { 1: 0, [duplicateId]: 1 } })])
    accountA.normalizeDuplicateCategories()

    expect(accountA.getCategories().filter(category => category.name === '输入')).toHaveLength(1)
    expect(accountA.allRaw('SELECT category_id FROM study_sessions')[0].category_id).toBe(1)
    expect(() => accountA.addCategory('输入', '📖', '#000', '增益')).toThrow('分类名称已存在')
    expect(() => accountA.updateCategory(2, { name: '输入' })).toThrow('分类名称已存在')
    expect(accountB.getCategories()).toHaveLength(19)
    expect(accountB.allRaw('SELECT * FROM study_sessions')).toHaveLength(0)
  })

  it('aligns a client-only category to its server id without losing references', () => {
    const db = createDb()
    db.runRaw("INSERT INTO categories (id,name,icon,color,group_name,sort_order,is_active,created_at) VALUES (26,'额外休息','x','#000','生活',30,1,'2026-08-29 00:00:00')")
    db.logSession({ startTime: '2026-08-29 09:00:00', endTime: '2026-08-29 09:30:00', netDurationMinutes: 30, date: '2026-08-29', categoryId: 26 })

    db.rekeyCategoryId(26, 46)

    expect(db.allRaw("SELECT id FROM categories WHERE name='额外休息'")[0].id).toBe(46)
    expect(db.allRaw('SELECT category_id FROM study_sessions')[0].category_id).toBe(46)
  })

  it('pulls authoritative 46–49 category ids before sessions without internal outbox writes', async () => {
    const db = createDb(); const names = ['休息', '活动', '工作', '家务']; db.runRaw('DELETE FROM categories')
    names.forEach((name, index) => db.runRaw("INSERT INTO categories(id,name,icon,color,group_name,sort_order,is_active,created_at,updated_at) VALUES (?,?,'x','#000','生活',?,1,'old','old')", [16 + index, name, index]))
    names.forEach((name, index) => db.runRaw("INSERT INTO categories(id,name,icon,color,group_name,sort_order,is_active,created_at,updated_at) VALUES (?,?,'old','#999','生活',?,0,'old','old')", [46 + index, name, index]))
    const localIds = names.map((_, index) => db.logSession({ startTime: '2026-08-31 09:00', endTime: '2026-08-31 10:00', netDurationMinutes: 60, date: '2026-08-31', categoryId: 16 + index }))
    db.runRaw("DELETE FROM sync_outbox WHERE table_name='study_sessions'")
    const categories = names.map((name, index) => ({ id: 46 + index, name, icon: 'server', color: '#111', group_name: '生活', sort_order: index, is_active: 1, created_at: 'server', updated_at: 'server' }))
    const sessions = names.map((_, index) => ({ id: `server-${index}`, start_time: '2026-08-31 10:00', end_time: '2026-08-31 10:01', net_duration_minutes: 1, net_duration_seconds: 60, date: '2026-08-31', day_of_week: '星期一', pause_count: 0, pause_reasons: '[]', session_summary: '', category_id: 46 + index, updated_at: 'server' }))
    const worker = new SyncWorker(); worker.bind({ post: async () => ({ ok: true, data: {} }), get: async () => ({ ok: true, data: { status: 'ok', from_version: 0, to_version: 1, server_time: 'server', tables: { categories, study_sessions: sessions } } }) } as any, db)
    expect(await worker.pullAndMergeResult(true)).toMatchObject({ ok: true, merged: 8 })
    expect(localIds.map(id => db.getRecordById('study_sessions', id)?.category_id)).toEqual([46, 47, 48, 49])
    expect(db.allRaw('SELECT COUNT(*) AS count FROM study_sessions s LEFT JOIN categories c ON c.id=s.category_id WHERE c.id IS NULL')[0].count).toBe(0)
    expect(db.getPendingOutbox(20).filter(row => row.table_name === 'study_sessions')).toHaveLength(0)
    db.updateSession(localIds[0], { session_summary: '用户编辑' })
    expect(db.getPendingOutbox(20).filter(row => row.table_name === 'study_sessions')).toHaveLength(1)
  })
})
