import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('bedtime coin pull projection', () => {
  it('keeps all settlement fields in the client schema and pull-only registry', () => {
    const schema = readFileSync(fileURLToPath(new URL('../models/Schema.ts', import.meta.url)), 'utf8')
    const registry = JSON.parse(readFileSync(fileURLToPath(new URL('../../shared/protocol/sync-entities.json', import.meta.url)), 'utf8'))
    const entity = registry.entities.find((item: any) => item.name === 'sleep_score_settlements')
    for (const field of ['bedtime_coin_status', 'bedtime_coin_amount', 'bedtime_coin_reason', 'bedtime_coin_rule_version']) {
      expect(schema).toContain(field)
      expect(entity.projectionFields).toContain(field)
    }
    expect(entity.direction).toBe('pull_only')
    expect(entity.outbox).toBe(false)
  })
})
