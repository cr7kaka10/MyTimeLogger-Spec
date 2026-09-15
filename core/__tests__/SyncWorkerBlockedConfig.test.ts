import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

describe('SyncWorker account contamination guard', () => {
  it('does not send legacy account or provider config outbox entries', async () => {
    const post = vi.fn(async () => ({ ok: true, status: 200, data: {
      status: 'ok', server_time: '2026-07-28 01:00:00',
      operation_results: [{ change_id: 'habit-1', status: 'accepted', table: 'habits' }],
    } }))
    const synced = vi.fn()
    const db: any = {
      setEnqueue() {}, getConfig: () => '', setConfig() {}, markOutboxSynced: synced, markOutboxSending: vi.fn(),
      getPendingOutbox: () => [
        { id: 1, change_id: 'identity-1', table_name: 'system_config', payload_json: '{"key":"account_identity_key"}' },
        { id: 2, change_id: 'provider-1', table_name: 'system_config', payload_json: '{"key":"ticktick_config"}' },
        { id: 3, change_id: 'verified-1', table_name: 'system_config', payload_json: '{"key":"env_development_verified_user_id"}' },
        { id: 4, change_id: 'habit-1', table_name: 'habits', payload_json: '{"id":"habit-1"}' },
      ],
    }
    const worker = new SyncWorker(); worker.bind({ post } as any, db)
    await expect(worker.pushOnly()).resolves.toMatchObject({ ok: true })
    expect(post.mock.calls[0][1].operations).toEqual([expect.objectContaining({ table: 'habits' })])
    expect(synced).toHaveBeenCalledWith([1, 2, 3], expect.any(String))
  })
})
