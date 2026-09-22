import { describe, it, expect } from 'vitest'
import { Database } from '../models/Database'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'

describe('local habit history queries', () => {
  it('keeps deleted local history out of active lists and excludes mirrors', () => {
    const db = new Database(createBetterSqliteAdapter())
    const id = db.addHabit('散步')
    const mirror = db.addHabit('镜像')
    db.runRaw("UPDATE habits SET source='ticktick',is_active=1 WHERE id=?", [mirror])
    db.toggleCheckin(id, '2026-09-22')
    db.deleteHabit(id)
    expect(db.getHabits()).toHaveLength(0)
    expect(db.getArchivedLocalHabits().map(row => row.id)).toEqual([id])
    const details = db.getLocalHabitDetails(id)
    expect(details?.habit).toMatchObject({ id, name: '散步', is_active: 1, source: 'local' })
    expect(details?.checkins).toHaveLength(1)
    expect(details?.checkins[0].date).toBe('2026-09-22')
    expect(db.getLocalHabitDetails(mirror)).toBeUndefined()
    expect(db.getLocalHabitDetails('missing')).toBeUndefined()
  })
})
