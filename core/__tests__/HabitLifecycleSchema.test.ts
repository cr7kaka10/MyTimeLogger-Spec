import { it, expect } from 'vitest'
import { Database } from '../models/Database'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'

it('migrates lifecycle storage idempotently without inventing archive times', () => {
  const adapter = createBetterSqliteAdapter()
  const db = new Database(adapter)
  const id = db.addHabit('历史')
  db.runRaw('UPDATE habits SET is_active=1 WHERE id=?', [id])
  new Database(adapter)
  expect(db.allRaw('SELECT archived_at,archive_reason,lifecycle_version FROM habits WHERE id=?', [id])[0])
    .toMatchObject({ archived_at: null, archive_reason: 'legacy_archived', lifecycle_version: 0 })
  db.runRaw("INSERT INTO habit_tombstones VALUES(?,'binding','provider','2026-09-23','confirmed',10)", [id])
  db.runRaw('DELETE FROM habits WHERE id=?', [id])
  new Database(adapter)
  expect(db.allRaw('SELECT * FROM habit_tombstones')).toHaveLength(1)
  expect(db.allRaw('SELECT * FROM habit_lifecycle_outbox_audit')).toHaveLength(0)
})
