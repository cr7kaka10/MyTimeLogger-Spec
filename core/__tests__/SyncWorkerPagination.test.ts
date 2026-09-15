import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

describe('SyncWorker version pagination', () => {
  it('drains all pages before reporting a successful pull', async () => {
    let version = 0
    const writes: string[] = []
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], hasPendingOutbox: () => false,
      getLastServerVersion: () => version, setLastServerVersion: (next: number) => { version = next },
      getConfig: () => '', setConfig() {}, getRecordById: () => null, getRecordByUnique: () => null,
      runRaw: (_sql: string, params: any[]) => writes.push(String(params[0])),
      runInTransaction: (fn: () => void) => fn(),
    }
    const get = vi.fn(async (_path: string, params: Record<string, string>) => {
      const first = params.since_version === '0'
      const next = first ? 1 : 2
      return { ok: true, data: {
        status: 'ok', from_version: next - 1, to_version: next, has_more: first,
        server_time: `2026-07-29 12:00:0${next}`,
        tables: { tasks: [{ id: `task-${next}`, title: `row-${next}`, updated_at: `2026-07-29 12:00:0${next}` }] },
      } }
    })
    const worker = new SyncWorker()
    worker.bind({ get, post: vi.fn(async () => ({ ok: true, data: { status: 'ok' } })) } as any, db)

    const result = await worker.flushNow(false, { syncRunId: 'pagination-run' })

    expect(result).toMatchObject({ ok: true, merged: 2 })
    expect(result.diagnostics?.pages).toBe(2)
    expect(version).toBe(2)
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls.map(call => call[1].since_version)).toEqual(['0', '1'])
    expect(writes).toEqual(['task-1', 'task-2'])
  })
})
