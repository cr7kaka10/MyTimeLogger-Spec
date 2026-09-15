import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

const entry = (id: number, table: string, payload: object) => ({
  id, table_name: table, change_id: `c${id}`, device_id: 'pc', record_id: String(id),
  operation: 'upsert', base_version: 0, payload_json: JSON.stringify(payload),
})
const setup = () => {
  const entries = [
    entry(1, 'study_sessions', { id: 's1', session_summary: 'core' }),
    entry(2, 'habits', { id: 'h1', name: 'provider', source: 'ticktick' }),
  ]
  const post = vi.fn(async (_path: string, body: any) => ({ ok: true, data: {
    status: 'ok', server_time: '2026-09-11 12:00:00',
    operation_results: body.operations.map((op: any) => ({ change_id: op.change_id, table: op.table, status: 'accepted' })),
  } }))
  const db: any = { setEnqueue() {}, getPendingOutbox: () => entries, getConfig: () => '', setConfig() {},
    markOutboxSending: vi.fn(), markOutboxSynced: vi.fn(), markOutboxFailed: vi.fn() }
  const worker = new SyncWorker(); worker.bind({ post } as any, db)
  return { worker, post, db }
}

describe('SyncWorker scope isolation', () => {
  it('keeps provider outbox pending during core sync', async () => {
    const { worker, post, db } = setup()
    await (worker as any)._flushOutbox({ scope: 'core', syncRunId: 'core-run' })
    expect(post.mock.calls[0][1]).toMatchObject({ sync_scope: 'core' })
    expect(post.mock.calls[0][1].operations.map((op: any) => op.table)).toEqual(['study_sessions'])
    expect(db.markOutboxSending).toHaveBeenCalledWith([1])
    expect(db.markOutboxSynced).not.toHaveBeenCalledWith(expect.arrayContaining([2]), expect.anything())
  })

  it('sends provider outbox only in checklist scope', async () => {
    const { worker, post } = setup()
    await (worker as any)._flushOutbox({ scope: 'checklist', syncRunId: 'checklist-run' })
    expect(post.mock.calls[0][1]).toMatchObject({ sync_scope: 'checklist' })
    expect(post.mock.calls[0][1].operations.map((op: any) => op.table)).toEqual(['study_sessions', 'habits'])
  })
})
