import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { Database } from '../models/Database'

describe('SyncWorker reward fragments', () => {
  it('pulls server-owned fragments and source bindings after their reward without creating an outbox entry', async () => {
    const db = new Database(createBetterSqliteAdapter())
    const worker = new SyncWorker()
    worker.bind({
      post: vi.fn(),
      get: vi.fn(async () => ({ ok: true, data: {
        status: 'ok', from_version: 0, to_version: 1, changes: [{ server_version: 1 }], server_time: '2026-08-23 12:00:00',
        tables: {
          rewards: [{ id: 'reward-1', title: '手机', price: 0, fulfillment_mode: 'fragment', fragment_target_count: 7, fragment_rule_version: 1, created_at: '2026-08-23 12:00:00', updated_at: '2026-08-23 12:00:00' }],
          reward_source_bindings: [{ id: 'binding-1', reward_id: 'reward-1', source_type: 'habit', source_id: 'habit-1', created_at: '2026-08-23 12:00:00', updated_at: '2026-08-23 12:00:00' }],
          reward_fragments: [{ id: 'fragment-1', reward_id: 'reward-1', source_type: 'habit', source_id: 'habit-1', completion_event_key: 'habit:habit-1:2026-08-23', rule_version: 1, issued_at: '2026-08-23 12:00:00', expires_at: '2026-08-30 00:00:00', status: 'active', created_at: '2026-08-23 12:00:00', updated_at: '2026-08-23 12:00:00' }],
        },
      } })),
    } as any, db)

    expect(await worker.flushNow(false)).toMatchObject({ ok: true, merged: 3 })
    expect(db.getRecordById('reward_fragments', 'fragment-1')).toMatchObject({ reward_id: 'reward-1', status: 'active' })
    expect(db.getRecordById('reward_source_bindings', 'binding-1')).toMatchObject({ reward_id: 'reward-1', source_type: 'habit' })
    expect(db.getPendingOutbox(20).some(item => item.table_name === 'reward_fragments')).toBe(false)
    expect(db.getPendingOutbox(20).some(item => item.table_name === 'reward_source_bindings')).toBe(false)
  })
})
