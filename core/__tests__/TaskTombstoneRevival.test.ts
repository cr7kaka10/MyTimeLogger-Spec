import { describe, expect, it } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

const columns = new Set(['id', 'title', 'status', 'due_date', 'deleted_at', 'updated_at', 'pulled_at', 'pushed_at'])
const revival = { id: 'task-1', title: 'fixture', status: 0, due_date: '2026-07-31', deleted_at: null, updated_at: '2026-07-31 20:00:00' }

describe('task tombstone revival merge', () => {
  it('PC upsert preserves explicit null and clears the local tombstone', () => {
    let row: Record<string, unknown> = { id: 'task-1', deleted_at: '2026-07-31 16:20:54' }
    const db: any = {
      allRaw: () => [...columns].map(name => ({ name })), setConfig() {},
      runRaw: (sql: string, params: unknown[]) => {
        const keys = sql.slice(sql.indexOf('(') + 1, sql.indexOf(')')).split(', ')
        row = { ...row, ...Object.fromEntries(keys.map((key, index) => [key, params[index]])) }
      },
    }
    const worker = new SyncWorker(); (worker as any)._db = db
    expect((worker as any)._upsertLocal('tasks', revival, '2026-07-31 20:00:01')).toBeNull()
    expect(row.deleted_at).toBeNull()
  })

  it('Android bulk operation preserves explicit null', () => {
    const worker = new SyncWorker()
    const operation = (worker as any)._bulkOperation('tasks', revival, '2026-07-31 20:00:01', null, columns)
    const keys = operation.sql.slice(operation.sql.indexOf('(') + 1, operation.sql.indexOf(')')).split(', ')
    expect(operation.params[keys.indexOf('deleted_at')]).toBeNull()
  })
})
