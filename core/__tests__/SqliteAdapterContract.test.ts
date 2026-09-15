import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'

type Step = { exec?: string; run?: string; query?: string; params?: any[]; expect?: any[] }
type Scenario = { name: string; steps: Step[] }
const contract = JSON.parse(readFileSync(new URL('../../shared/protocol/sqlite-adapter-contract.json', import.meta.url), 'utf8')) as Scenario[]

const query = (db: ReturnType<typeof createBetterSqliteAdapter>, sql: string, params: any[] = []) => {
  const statement = db.prepare(sql); statement.bind(params)
  const rows: any[] = []
  while (statement.step()) rows.push(statement.getAsObject())
  statement.free(); return rows
}

describe('Electron SQLite adapter shared contract', () => {
  for (const scenario of contract) it(scenario.name, () => {
    const db = createBetterSqliteAdapter(':memory:')
    try {
      for (const step of scenario.steps) {
        if (step.exec) db.exec(step.exec)
        else if (step.run) db.run(step.run, step.params)
        else if (step.query) expect(query(db, step.query, step.params)).toEqual(step.expect)
      }
    } finally { db.close() }
  })
})
