import { describe, it, expect } from 'vitest'
import { Database } from '../models/Database'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'

describe('local habit history queries', () => {
  it('keeps deleted local history out of active lists and excludes mirrors', () => {
    const db = new Database(createBetterSqliteAdapter())
    const id = db.addHabit('散步')
    const mirror = db.addHabit('镜像')
    db.runRaw("UPDATE habits SET source='ticktick',is_active=0 WHERE id=?", [mirror])
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

  it('treats an inactive referenced category as unclassified', () => {
    const db = new Database(createBetterSqliteAdapter())
    const id = db.addHabit('阅读', '📖', { category_id: 9999 })
    db.runRaw("INSERT INTO categories(id,name,icon,color,sort_order,is_active,created_at,updated_at) VALUES(9999,'旧分类','📖','#fff',0,0,'now','now')")
    expect(db.getLocalHabitDetails(id)?.category).toBeNull()
  })
})
