import BetterSqlite3 from 'better-sqlite3'
import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

const createDb = () => {
  const sqlite = new BetterSqlite3(':memory:'); sqlite.pragma('foreign_keys = ON')
  sqlite.exec(`CREATE TABLE habits (id TEXT PRIMARY KEY, name TEXT, updated_at TEXT, pulled_at TEXT, pushed_at TEXT);
    CREATE TABLE habit_checkins (id TEXT PRIMARY KEY, habit_id TEXT NOT NULL REFERENCES habits(id), checkin_date TEXT, status INTEGER, updated_at TEXT, pulled_at TEXT, pushed_at TEXT);`)
  let version = 100
  return { sqlite, db: {
    setEnqueue() {}, getPendingOutbox: () => [], hasPendingOutbox: () => false,
    getLastServerVersion: () => version, setLastServerVersion: (next: number) => { version = next },
    getConfig: () => '', setConfig() {}, runInTransaction: (fn: () => void) => fn(),
    getRecordById: (table: string, id: string) => sqlite.prepare(`SELECT * FROM ${table} WHERE id = ?`).get(id) ?? null,
    getRecordByUnique: () => null, allRaw: (sql: string, params: any[] = []) => sqlite.prepare(sql).all(...params),
    runRaw: (sql: string, params: any[]) => sqlite.prepare(sql).run(params),
  }, version: () => version }
}

const pull = (tables: Record<string, any[]>, toVersion = 101) => ({
  post: vi.fn(async () => ({ ok: true, data: { status: 'ok' } })),
  get: vi.fn(async () => ({ ok: true, data: { status: 'ok', from_version: 100, to_version: toVersion, server_time: '2026-07-29 13:00:00', tables } })),
})

describe('SyncWorker foreign-key-safe checklist merge', () => {
  it('replays reset pages to the server tail and retains the last successful page on a later merge failure', async () => {
    const pages = (secondTables: Record<string, any[]>) => {
      const get = vi.fn()
        .mockResolvedValueOnce({ ok: true, data: { status: 'ok', from_version: 100, to_version: 101, has_more: true, server_time: '2026-08-04 10:00:00', tables: { habits: [{ id: 'page-one', name: 'one', updated_at: '2026-08-04 10:00:00' }] } } })
        .mockResolvedValueOnce({ ok: true, data: { status: 'ok', from_version: 101, to_version: 102, server_time: '2026-08-04 10:00:01', tables: secondTables } })
      return { post: vi.fn(async () => ({ ok: true, data: { status: 'ok' } })), get }
    }
    const complete = createDb(); const completeApi = pages({ habit_checkins: [{ id: 'page-two', habit_id: 'page-one', checkin_date: '2026-08-04', status: 2, updated_at: '2026-08-04 10:00:01' }] })
    const completeWorker = new SyncWorker(); completeWorker.bind(completeApi as any, complete.db as any)
    expect(await completeWorker.flushNow(false)).toMatchObject({ ok: true, merged: 2, diagnostics: { pages: 2 } })
    expect(complete.version()).toBe(102)
    expect(completeApi.get.mock.calls.map(call => call[1].since_version)).toEqual(['100', '101'])
    complete.sqlite.close()

    const partial = createDb(); const partialApi = pages({ habit_checkins: [{ id: 'orphan', habit_id: 'missing-parent', checkin_date: '2026-08-04', status: 2, updated_at: '2026-08-04 10:00:01' }] })
    const partialWorker = new SyncWorker(); partialWorker.bind(partialApi as any, partial.db as any)
    const failed = await partialWorker.flushNow(false)
    expect(failed).toMatchObject({ ok: false, error: 'local_merge_failed', diagnostics: { cursor: { previous: 101, next: 101, advanced: false } } })
    expect(partial.version()).toBe(101)
    expect(partial.sqlite.prepare('SELECT COUNT(*) count FROM habits').get()).toMatchObject({ count: 1 })
    partial.sqlite.close()
  })

  it('deletes child checkins before parents, then rebuilds the pair', async () => {
    const { sqlite, db, version } = createDb()
    sqlite.prepare('INSERT INTO habits (id, name) VALUES (?, ?)').run('old-habit', 'old')
    sqlite.prepare('INSERT INTO habit_checkins (id, habit_id) VALUES (?, ?)').run('old-check', 'old-habit')
    const worker = new SyncWorker(); worker.bind(pull({
      habits: [{ id: 'old-habit', _sync_operation: 'delete' }, { id: 'new-habit', name: 'new', updated_at: '2026-07-29 12:00:00' }],
      habit_checkins: [{ id: 'old-check', _sync_operation: 'delete' }, { id: 'new-check', habit_id: 'new-habit', checkin_date: '2026-07-29', status: 2, updated_at: '2026-07-29 12:00:00' }],
    }) as any, db as any)
    expect(await worker.flushNow(false)).toMatchObject({ ok: true, merged: 4 })
    expect(version()).toBe(101); expect(sqlite.prepare('SELECT COUNT(*) count FROM habit_checkins WHERE habit_id = ?').get('new-habit')).toMatchObject({ count: 1 })
    sqlite.close()
  })

  it('updates a habit with an existing checkin without replacing its parent row', async () => {
    const { sqlite, db } = createDb()
    sqlite.prepare('INSERT INTO habits (id, name) VALUES (?, ?)').run('habit-1', 'old')
    sqlite.prepare('INSERT INTO habit_checkins (id, habit_id) VALUES (?, ?)').run('check-1', 'habit-1')
    const worker = new SyncWorker(); worker.bind(pull({ habits: [{ id: 'habit-1', name: 'new', updated_at: '2026-07-29 12:00:00' }] }) as any, db as any)
    expect(await worker.flushNow(false)).toMatchObject({ ok: true, merged: 1 })
    expect(sqlite.prepare('SELECT name FROM habits WHERE id = ?').get('habit-1')).toMatchObject({ name: 'new' })
    expect(sqlite.prepare('SELECT COUNT(*) count FROM habit_checkins WHERE habit_id = ?').get('habit-1')).toMatchObject({ count: 1 })
    sqlite.close()
  })

  it('replays a prior habit delete after a partial merge without deleting pending local checkins', async () => {
    const { sqlite, db, version } = createDb()
    sqlite.prepare('INSERT INTO habits (id, name) VALUES (?, ?)').run('habit-1', 'old')
    sqlite.prepare('INSERT INTO habit_checkins (id, habit_id) VALUES (?, ?)').run('partial-check', 'habit-1')
    const replay = { habits: [{ id: 'habit-1', _sync_operation: 'delete' }, { id: 'habit-1', name: 'new', updated_at: '2026-07-29 12:00:00' }], habit_checkins: [{ id: 'partial-check', habit_id: 'habit-1', updated_at: '2026-07-29 12:00:00' }] }
    const worker = new SyncWorker(); worker.bind(pull(replay) as any, db as any)
    expect(await worker.flushNow(false)).toMatchObject({ ok: true, merged: 3 })
    expect(version()).toBe(101); expect(sqlite.prepare('SELECT COUNT(*) count FROM habit_checkins').get()).toMatchObject({ count: 1 })
    ;(db as any).setLastServerVersion(100); (db as any).hasPendingOutbox = (_table: string, id: string) => id === 'partial-check'
    const failed = await worker.pullAndMergeResult(true)
    expect(failed).toMatchObject({ ok: false, error: 'local_merge_failed' }); expect(version()).toBe(100)
    expect(failed.diagnostics?.merge.failure_details).toEqual([{ table: 'habits', recordId: 'habit-1', category: 'pending_child_conflict' }])
    expect(sqlite.prepare('SELECT COUNT(*) count FROM habits').get()).toMatchObject({ count: 1 })
    sqlite.close()
  })

  it('keeps its cursor and reports only safe details when one write still fails', async () => {
    let version = 100; let fail = true
    const db: any = { setEnqueue() {}, getPendingOutbox: () => [], hasPendingOutbox: () => false, getLastServerVersion: () => version,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig() {}, getRecordById: () => null, getRecordByUnique: () => null,
      runRaw: () => { if (fail) throw new Error('FOREIGN KEY constraint failed') }, runInTransaction: (fn: () => void) => fn() }
    const api = pull({ tasks: [{ id: 'safe-id', title: 'private title', updated_at: '2026-07-29 12:00:00' }] }, 101)
    const worker = new SyncWorker(); worker.bind(api as any, db)
    const failed = await worker.flushNow(false)
    expect(failed).toMatchObject({ ok: false, error: 'local_merge_failed' }); expect(version).toBe(100)
    expect(failed.diagnostics?.merge.failure_details).toEqual([{ table: 'tasks', recordId: 'safe-id', category: 'constraint' }])
    expect(JSON.stringify(failed.diagnostics)).not.toContain('private title')
    fail = false; expect(await worker.flushNow(false)).toMatchObject({ ok: true, merged: 1 }); expect(version).toBe(101)
  })
})
