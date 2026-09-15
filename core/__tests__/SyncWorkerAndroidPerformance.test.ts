import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

describe('SyncWorker Android bulk performance', () => {
  it('uses the shared server ledger snapshot path before Android bulk merging', async () => {
    let version = 4
    const replaceServerLedgerSnapshot = vi.fn(() => ({ removed: 1, balance: 9.7 }))
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version, getLedgerSnapshotVersion: () => 0,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig() {},
      getLedgerSummary: () => ({ balance: 8.7 }), replaceServerLedgerSnapshot,
      androidBulk: { query: () => [], transaction: () => {}, yieldToUi: async () => {} },
    }
    const api: any = { post: vi.fn(), get: vi.fn(async () => ({ ok: true, data: {
      status: 'ok', from_version: 4, to_version: 5, changes: [{ server_version: 5 }], tables: {}, server_time: '2026-08-05 12:00:00',
      ledger_snapshot: { rows: [{ id: 'server', amount: 9.7 }], summary: { balance: 9.7, income: 13.7, expense: 4 }, integrity: { count: 1, sha256: 'a'.repeat(64) } },
    } })) }
    const worker = new SyncWorker(); worker.bind(api, db)

    expect(await worker.flushNow(false)).toMatchObject({ ok: true })
    expect(api.get.mock.calls[0][1]).toMatchObject({ ledger_snapshot: 'true' })
    expect(replaceServerLedgerSnapshot).toHaveBeenCalledWith(expect.any(Object), 5)
    expect(version).toBe(5)
  })

  it('scales bridge calls by bounded batches and yields before completion', async () => {
    const rows = Array.from({ length: 205 }, (_, id) => ({ id: `t${id}`, title: `task${id}`, updated_at: '2026-07-21 12:00:00' }))
    const queries: string[] = []; const transactions: any[][] = []; const events: string[] = []
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => 0,
      setLastServerVersion() {}, getConfig: () => '', setConfig() {},
      androidBulk: {
        query: (sql: string) => { queries.push(sql); return sql.startsWith('PRAGMA')
          ? ['id', 'title', 'updated_at', 'pulled_at', 'pushed_at'].map(name => ({ name })) : [] },
        transaction: (operations: any[]) => { transactions.push(operations) },
        yieldToUi: async () => { events.push('tab'); await Promise.resolve() },
      },
    }
    const api: any = { post: vi.fn(async () => ({ ok: true, data: { status: 'ok' } })), get: vi.fn(async () => ({ ok: true, data: {
      status: 'ok', from_version: 0, to_version: 205, changes: rows.map((_, server_version) => ({ server_version: server_version + 1 })),
      server_time: '2026-07-21 12:01:00', tables: { tasks: rows },
    } })) }
    const worker = new SyncWorker(); worker.bind(api, db)
    const result = await worker.flushNow(false)
    expect(result.merged).toBe(205); expect(transactions.map(batch => batch.length)).toEqual([100, 100, 5])
    expect(queries.filter(sql => sql.startsWith('PRAGMA'))).toHaveLength(1)
    expect(queries.filter(sql => sql.startsWith('SELECT * FROM tasks'))).toHaveLength(3)
    expect(events).toEqual(['tab', 'tab', 'tab'])
  })

  it('isolates one bad record, advances only continuously, and gates passive replay', async () => {
    let version = 0; let transactions = 0
    const rows = [{ id: 'good', title: 'ok' }, { id: 'bad', title: 'private payload' }]
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig() {},
      androidBulk: {
        query: (sql: string) => sql.startsWith('PRAGMA') ? ['id', 'title', 'pulled_at', 'pushed_at'].map(name => ({ name })) : [],
        transaction: (operations: any[]) => { transactions++; if (operations.some(op => op.recordId === 'bad')) throw new Error('constraint private-token') },
        yieldToUi: async () => {},
      },
    }
    const response = { ok: true, data: { status: 'ok', from_version: 0, to_version: 2,
      changes: [{ server_version: 1, table_name: 'tasks', record_id: 'good' }, { server_version: 2, table_name: 'tasks', record_id: 'bad' }],
      server_time: '2026-07-21 12:01:00', tables: { tasks: rows } } }
    const worker = new SyncWorker(); worker.bind({ get: vi.fn(async () => response), post: vi.fn(async () => ({ ok: true, data: { status: 'ok' } })) } as any, db)
    const failed = await worker.flushNow(false)
    expect(failed).toMatchObject({ ok: false, merged: 1, error: 'local_merge_failed' }); expect(version).toBe(0)
    expect(JSON.stringify(failed.diagnostics)).not.toContain('private payload'); expect(JSON.stringify(failed.diagnostics)).not.toContain('private-token')
    const before = transactions
    expect(await worker.pullAndMergeResult(false, { reason: 'android-foreground-fallback' })).toMatchObject({ error: 'local_merge_backoff' })
    expect(transactions).toBe(before)
  })

  it('reports one table schema failure before splitting ATM records', async () => {
    let version = 0; const transaction = vi.fn()
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version, setLastServerVersion: (next: number) => { version = next },
      getConfig: () => '', setConfig() {}, androidBulk: { query: (sql: string) => sql.startsWith('PRAGMA')
        ? [{ name: 'id' }, { name: 'date' }] : [], transaction, yieldToUi: async () => {} },
    }
    const tables = { atm_summary: [{ id: 1, date: '2026-07-20' }], atm_activities: Array.from({ length: 7 }, (_, id) => ({ id, date: '2026-07-20' })) }
    const response = { ok: true, data: { status: 'ok', snapshot: true, from_version: 0, to_version: 737, changes: [], tables } }
    const worker = new SyncWorker(); worker.bind({ get: vi.fn(async () => response), post: vi.fn() } as any, db)

    const result = await worker.pullAndMergeResult(true)

    expect(result).toMatchObject({ ok: false, merged: 0, error: 'local_merge_failed' }); expect(version).toBe(0)
    expect(transaction).not.toHaveBeenCalled(); expect(result.diagnostics?.merge.failure_details).toHaveLength(1)
  })

  it('applies a 729+1+7 snapshot and uses an incremental cursor next round', async () => {
    let version = 0; const tasks = Array.from({ length: 729 }, (_, id) => ({ id: `t${id}`, title: `task${id}` }))
    const tables = { tasks, atm_summary: [{ id: 1, date: '2026-07-20' }], atm_activities: Array.from({ length: 7 }, (_, id) => ({ id: id + 1, date: '2026-07-20', activity_type: 'work', start_time: '09:00', end_time: '10:00', duration_minutes: 60 })) }
    const get = vi.fn(async (_path: string, params: any) => ({ ok: true, data: { status: 'ok', snapshot: version === 0, from_version: version,
      to_version: 737, changes: [], tables: version === 0 ? tables : {}, server_time: '2026-07-21 18:02:00' } }))
    const columns: Record<string, string[]> = { tasks: ['id', 'title', 'pulled_at', 'pushed_at'], atm_summary: ['id', 'date', 'pulled_at', 'pushed_at'],
      atm_activities: ['id', 'date', 'activity_type', 'start_time', 'end_time', 'duration_minutes', 'pulled_at', 'pushed_at'] }
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version, setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig() {},
      androidBulk: { query: (sql: string) => { const table = Object.keys(columns).find(name => sql.includes(`(${name})`)); return table ? columns[table].map(name => ({ name })) : [] },
        transaction: () => {}, yieldToUi: async () => {} },
    }
    const worker = new SyncWorker(); worker.bind({ get, post: vi.fn() } as any, db)
    expect(await worker.pullAndMergeResult(true)).toMatchObject({ ok: true, merged: 737 }); expect(version).toBe(737)
    expect(await worker.pullAndMergeResult(true)).toMatchObject({ ok: true, merged: 0 })
    expect(get.mock.calls[1][1]).toMatchObject({ since_version: '737' })
  })
})
