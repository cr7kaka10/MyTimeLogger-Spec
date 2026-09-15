import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

describe('SyncWorker task command isolation', () => {
  it('keeps local task creation and deletion out of the generic outbox request', async () => {
    const post = vi.fn()
    const failed = vi.fn()
    const db: any = {
      setEnqueue: () => {}, getConfig: () => '', setConfig: () => {},
      getPendingOutbox: () => [{ id: 1, table_name: 'tasks', record_id: 'local-task', operation: 'delete', payload_json: '{"id":"local-task"}' }],
      markOutboxFailed: failed, markOutboxSynced: vi.fn(),
    }
    const worker = new SyncWorker()
    worker.bind({ post, get: vi.fn() } as any, db)
    const result = await worker.pushOnly()
    expect(result).toMatchObject({ ok: true, merged: 0, pending: 1 })
    expect(post).not.toHaveBeenCalled()
    expect(failed).toHaveBeenCalledWith([1], 'task_structure_requires_command')
  })
})
