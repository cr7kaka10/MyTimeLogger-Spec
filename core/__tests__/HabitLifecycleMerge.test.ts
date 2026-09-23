import { describe, it, expect } from 'vitest'
import { Database } from '../models/Database'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { planHabitLifecycle } from '../core/HabitLifecycleMerge'

describe('provider lifecycle transaction plan', () => {
  it('atomically deletes children, terminates only related outbox, and fences replay', () => {
    const db = new Database(createBetterSqliteAdapter())
    const id = db.addHabit('镜像'); const other = db.addHabit('保留')
    db.toggleCheckin(id, '2026-09-23')
    db.runRaw("UPDATE habits SET source='ticktick',lifecycle_version=2 WHERE id=?", [id])
    const query = (sql: string, args: any[] = []) => db.allRaw(sql, args)
    const row = { id, source: 'ticktick', lifecycle_version: 4, provider_binding_id: 'b', provider_id: 'p', evidence: 'verified', _sync_operation: 'delete' }
    const plan = planHabitLifecycle(query, row, null, '2026-09-23 20:00:00')!
    expect(() => db.runInTransaction(() => { plan.forEach(op => db.runRaw(op.sql, op.params)); throw new Error('rollback') })).toThrow('rollback')
    expect(db.getRecordById('habits', id)).toBeTruthy()
    expect(query('SELECT * FROM habit_tombstones')).toHaveLength(0)
    db.runInTransaction(() => plan.forEach(op => db.runRaw(op.sql, op.params)))
    expect(db.getRecordById('habits', id)).toBeFalsy()
    expect(query('SELECT * FROM habit_checkins WHERE habit_id=?', [id])).toHaveLength(0)
    expect(query('SELECT * FROM habit_lifecycle_outbox_audit').length).toBeGreaterThan(0)
    expect(db.getPendingOutbox(100).some(r => r.record_id === other)).toBe(true)
    expect(planHabitLifecycle(query, row, null, 'now')).toBeNull()
    expect(planHabitLifecycle(query, { ...row, _sync_operation: 'upsert', lifecycle_version: 3 }, null, 'now')).toBeNull()
  })
  it('active facts do not terminate pending checkins', () => {
    const db = new Database(createBetterSqliteAdapter()); const id = db.addHabit('活动')
    db.runRaw("UPDATE habits SET source='ticktick' WHERE id=?", [id])
    const upsert = { sql: 'SELECT 1', params: [] }
    const result = planHabitLifecycle((sql, args) => db.allRaw(sql, args), { id, source: 'ticktick', lifecycle_version: 1, is_active: 0 }, upsert, 'now')
    expect(result).toEqual([upsert])
  })
})
