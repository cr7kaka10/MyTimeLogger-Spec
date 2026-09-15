import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

const columns = ['id', 'date', 'plan_version', 'exercise_type', 'week_num', 'day_name', 'completed_items', 'total_items', 'created_at', 'updated_at', 'pulled_at', 'pushed_at']
const serverRows = (id = '6fff3004-e94a-422e-9038-0c8f5b7ae78a') => [{ id, date: '2026-07-25', plan_version: 'v1', exercise_type: '六', updated_at: '2026-07-25 08:33:35' }]
const response = (rows: any[], from = 0, to = 1) => ({ ok: true, data: { status: 'ok', from_version: from, to_version: to, changes: [{ server_version: to }], server_time: '2026-07-31 09:00:00', tables: { exercise_daily_logs: rows } } })

describe('SyncWorker exercise daily natural-key convergence', () => {
  it('reuses a PC local automatic id, deterministically deduplicates, and replays idempotently', async () => {
    let version = 0; const writes: any[] = []; const local = { ...serverRows('local')[0], id: 'auto-1-2026-07-25-v1-sc-2026-07-25-0', pushed_at: null }
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], hasPendingOutbox: () => false, getLastServerVersion: () => version, setLastServerVersion: (v: number) => { version = v },
      getConfig: () => '', setConfig() {}, getRecordById: () => null, getRecordByUnique: () => null,
      allRaw: (sql: string) => sql.startsWith('PRAGMA') ? columns.map(name => ({ name })) : sql.includes('exercise_daily_logs') ? [local] : [],
      runRaw: (sql: string, params: any[]) => writes.push({ sql, params }), runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = { post: vi.fn(async () => ({ ok: true, data: { status: 'ok' } })), get: vi.fn(async () => response([
      ...serverRows('auto-1-2026-07-25-v1-sc-2026-07-25-0'), ...serverRows('6fff3004-e94a-422e-9038-0c8f5b7ae78a'),
    ])) }
    const worker = new SyncWorker(); worker.bind(api, db)
    expect(await worker.flushNow(false)).toMatchObject({ ok: true, merged: 1 }); expect(version).toBe(1)
    expect(writes).toHaveLength(1); expect(writes[0].params).toContain(local.id); expect(writes[0].params).not.toContain('6fff3004-e94a-422e-9038-0c8f5b7ae78a')
    expect(await worker.pullAndMergeResult(true)).toMatchObject({ ok: true, merged: 1 }); expect(writes).toHaveLength(2)
  })

  it('matches Android bulk rows by natural key without legacy lookups and advances the cursor', async () => {
    let version = 0; const transactions: any[][] = []; const queries: string[] = []; const local = { ...serverRows('server')[0], id: 'auto-local', pushed_at: null }
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version, setLastServerVersion: (v: number) => { version = v }, getConfig: () => '', setConfig() {},
      getRecordById: () => { throw new Error('legacy lookup') }, getRecordByUnique: () => { throw new Error('legacy lookup') },
      androidBulk: { query: (sql: string) => { queries.push(sql); if (sql.startsWith('PRAGMA')) return columns.map(name => ({ name })); if (sql.includes('sync_outbox')) return []; if (sql.includes('date = ?')) return [local]; return [] }, transaction: (ops: any[]) => transactions.push(ops), yieldToUi: async () => {} },
    }
    const worker = new SyncWorker(); worker.bind({ post: vi.fn(async () => ({ ok: true, data: { status: 'ok' } })), get: vi.fn(async () => response(serverRows())) } as any, db)
    expect(await worker.flushNow(false)).toMatchObject({ ok: true, merged: 1 }); expect(version).toBe(1); expect(transactions).toHaveLength(1)
    expect(transactions[0][0].params).toContain(local.id); expect(queries.filter((sql: string) => sql.includes('date = ?'))).toHaveLength(1)
  })

  it('keeps the cursor on a pending local natural-key row', async () => {
    let version = 7; const local = { ...serverRows('server')[0], id: 'auto-local', pushed_at: null }
    const db: any = { setEnqueue() {}, getPendingOutbox: () => [], hasPendingOutbox: (table: string, id: string) => table === 'exercise_daily_logs' && id === local.id, getLastServerVersion: () => version, setLastServerVersion: (v: number) => { version = v }, getConfig: () => '', setConfig() {}, getRecordById: () => null, getRecordByUnique: () => null, allRaw: (sql: string) => sql.startsWith('PRAGMA') ? columns.map(name => ({ name })) : sql.includes('exercise_daily_logs') ? [local] : [], runRaw: () => { throw new Error('must not overwrite pending row') }, runInTransaction: (fn: () => void) => fn() }
    const worker = new SyncWorker(); worker.bind({ post: vi.fn(async () => ({ ok: true, data: { status: 'ok' } })), get: vi.fn(async () => response(serverRows(), 7, 8)) } as any, db)
    expect(await worker.flushNow(false)).toMatchObject({ ok: false, error: 'local_outbox_conflict' }); expect(version).toBe(7)
  })
})
