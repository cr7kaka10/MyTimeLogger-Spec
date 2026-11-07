import { describe, it, expect } from 'vitest'
import { Database } from '../models/Database'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { normalizeHabitEdits } from '../models/HabitEdits'

describe('local habit edits', () => {
  it('normalizes names and rejects untrusted keys and invalid values', () => {
    expect(normalizeHabitEdits({ title: '  读书  ' })).toEqual({ name: '读书' })
    for (const fields of [{ source: 'local' }, { is_active: 0 }, { difficulty: 'hard' }, { name: '  ' }, { sort_order: NaN }, { name: 'a', title: 'b' }]) {
      expect(() => normalizeHabitEdits(fields as any)).toThrow()
    }
  })
  it('edits and soft deletes with stable identity, preserving history and queue', () => {
    const db = new Database(createBetterSqliteAdapter())
    const id = db.addHabit('读书')
    expect(db.getRecordById('habits', id)).toMatchObject({ difficulty: 'easy', repeat_rule: 'FREQ=DAILY', category_id: null })
    db.toggleCheckin(id, '2026-09-22')
    db.updateHabit(id, { name: '阅读', repeat_rule: 'FREQ=DAILY' })
    expect(db.getRecordById('habits', id)).toMatchObject({ name: '阅读', source: 'local' })
    db.deleteHabit(id)
    expect(db.getHabits().some(h => h.id === id)).toBe(false)
    expect(db.getRecordById('habits', id)?.is_active).toBe(1)
    expect(db.getTodayCheckins('2026-09-22').some(c => c.habit_id === id)).toBe(true)
    expect(db.getPendingOutbox(100)).toEqual(expect.arrayContaining([expect.objectContaining({ record_id: id })]))
    expect(() => db.updateHabit(id, { name: '恢复' })).toThrow('已删除')
  })
  it('rejects stale snapshots and provider mirrors without modifying either', () => {
    const db = new Database(createBetterSqliteAdapter())
    const id = db.addHabit('原名')
    expect(() => db.updateHabit(id, { name: '旧修改' }, 'outdated')).toThrow('已更新')
    expect(() => db.deleteHabit(id, 'outdated')).toThrow('已更新')
    db.runRaw("UPDATE habits SET source='ticktick' WHERE id=?", [id])
    expect(() => db.updateHabit(id, { name: '镜像修改' })).toThrow('滴答镜像')
    expect(() => db.deleteHabit(id)).toThrow('滴答镜像')
    expect(db.getRecordById('habits', id)?.name).toBe('原名')
  })
})
