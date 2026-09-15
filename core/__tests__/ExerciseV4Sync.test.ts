import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), 'utf8')

describe('exercise V4 cross-device sync contract', () => {
  it('queues diet facts but keeps deadline and score facts server-owned', () => {
    const registry = JSON.parse(read('../../shared/protocol/sync-entities.json'))
    const entity = (name: string) => registry.entities.find((item: any) => item.name === name)
    expect(entity('exercise_diet_checkins')).toMatchObject({
      naturalKeys: ['date', 'plan_version', 'rule_key'], ownership: 'client_writable',
      direction: 'bidirectional', outbox: true,
    })
    expect(entity('exercise_deadline_facts')).toMatchObject({ ownership: 'server_owned', direction: 'pull_only', outbox: false })
    expect(entity('exercise_item_scores')).toMatchObject({ ownership: 'server_owned', direction: 'pull_only', outbox: false })
    expect(entity('exercise_settlements')).toMatchObject({ ownership: 'server_owned', direction: 'pull_only', outbox: false })
  })

  it('has mirrored tables, stable natural keys, and a diet outbox write', () => {
    const schema = read('../models/Schema.ts')
    const database = read('../models/Database.ts')
    expect(schema).toContain('CREATE TABLE IF NOT EXISTS exercise_diet_checkins')
    expect(schema).toContain('UNIQUE(date, plan_version, rule_key)')
    expect(schema).toContain('CREATE TABLE IF NOT EXISTS exercise_deadline_facts')
    expect(schema).toContain('UNIQUE(date, plan_version, fact_type)')
    expect(database).toContain("this._afterWrite('exercise_diet_checkins', saved.id)")
    expect(database).toContain("planVersion !== 'v4'")
  })
})
