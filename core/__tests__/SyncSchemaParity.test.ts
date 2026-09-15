import { describe, expect, it } from 'vitest'
import { SYNC_ENTITY_NAMES } from '../core/SyncEntities'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { initDatabase } from '../models/Schema'

describe('shared sync schema parity', () => {
  it('gives every registry client table pulled_at', () => {
    const db = createBetterSqliteAdapter()
    initDatabase(db)

    expect(SYNC_ENTITY_NAMES).toContain('flash_cards')
    expect(SYNC_ENTITY_NAMES).toContain('management_plan_revisions')
    const missing = SYNC_ENTITY_NAMES.filter(table => {
      const stmt = db.prepare(`PRAGMA table_info(${table})`)
      const columns: string[] = []
      while (stmt.step()) columns.push(String(stmt.getAsObject().name))
      stmt.free()
      return !columns.includes('pulled_at')
    })

    expect(missing).toEqual([])
  })
})
