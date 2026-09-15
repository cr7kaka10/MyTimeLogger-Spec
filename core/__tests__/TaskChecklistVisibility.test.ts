import { describe, expect, it } from 'vitest'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { Database } from '../models/Database'

describe('revived task checklist visibility', () => {
  it('shows the selected dated task and hides undated or tombstoned rows', () => {
    const db = new Database(createBetterSqliteAdapter())
    const insert = (id: string, dueDate: string | null, deletedAt: string | null) => db.runRaw(
      'INSERT INTO tasks (id,title,status,due_date,deleted_at,updated_at) VALUES (?,?,0,?,?,?)',
      [id, id, dueDate, deletedAt, '2026-07-31 20:00:00'],
    )
    insert('visible', '2026-07-31', null)
    insert('undated', null, null)
    insert('tombstoned', '2026-07-31', '2026-07-31 16:20:54')

    expect(db.getChecklistTasks('2026-07-31').map(row => row.id)).toEqual(['visible'])
  })
})
