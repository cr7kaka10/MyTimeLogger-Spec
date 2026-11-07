import { describe, expect, it, vi } from 'vitest'
import { Database } from '../models/Database'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { SyncWorker } from '../core/SyncWorker'

describe('meal wheel account sync', () => {
  it('queues one account config and pulls it only into the intended account database', async () => {
    const source = new Database(createBetterSqliteAdapter())
    const target = new Database(createBetterSqliteAdapter())
    const otherAccount = new Database(createBetterSqliteAdapter())
    const value = JSON.stringify({ schemaVersion: 1, revision: 'rev-1', updatedAt: '2026-11-06 12:00:00', items: [{ id: 'a', name: '面条', weight: 1 }, { id: 'b', name: '米饭', weight: 3 }] })
    source.setConfig('meal_wheel_v1', value)
    const outbox = source.getPendingOutbox(20).find(row => row.table_name === 'system_config' && row.record_id === 'meal_wheel_v1')
    expect(outbox).toBeDefined()
    expect(JSON.parse(String(outbox?.payload_json)).value).toBe(value)
    const serverRow = source.getRecordByUnique('system_config', 'key', 'meal_wheel_v1')
    const payload = { ok: true, data: { status: 'ok', from_version: 0, to_version: 1, server_time: '2026-11-06 12:00:01', tables: { system_config: [{ ...serverRow, user_id: 1, server_version: 1 }] } } }
    const worker = new SyncWorker()
    worker.bind({ post: vi.fn(), get: vi.fn(async () => payload) } as any, target)
    await worker.pullAndMergeResult(true)
    expect(target.getConfig('meal_wheel_v1')).toBe(value)
    expect(otherAccount.getConfig('meal_wheel_v1')).toBeNull()
  })
})
