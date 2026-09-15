import { describe, expect, it, vi } from 'vitest'
import { ApiClient, type ApiRequester } from '../core/ApiClient'
import { SYNC_CONFIG } from '../core/SyncConfig'
import { SyncWorker } from '../core/SyncWorker'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { Database } from '../models/Database'

describe('SyncWorker version cursor', () => {
  it('runs an authoritative push/pull follow-up when a user acts during sync', async () => {
    const worker = new SyncWorker()
    let releaseFirst: (() => void) | undefined
    const first = new Promise<{ ok: true; merged: number }>(resolve => { releaseFirst = () => resolve({ ok: true, merged: 0 }) })
    const flush = vi.spyOn(worker as any, '_flushNow')
      .mockImplementationOnce(() => first)
      .mockResolvedValue({ ok: true, merged: 2 })
    const pull = vi.spyOn(worker, 'pullAndMergeResult')
    const initial = worker.requestSync('app-foreground')
    const action = worker.requestSync('user-action')
    releaseFirst?.()
    await Promise.all([initial, action])
    expect(flush).toHaveBeenCalledTimes(2)
    expect(flush.mock.calls[1]?.[1]).toMatchObject({ reason: 'user-action-followup' })
    expect(pull).not.toHaveBeenCalled()
  })

  it('uses the dedicated pull timeout for an ordinary core pull', async () => {
    const get = vi.fn(async () => ({ ok: true, data: { status: 'ok', tables: {}, server_time: '2026-09-12 12:00:00' } }))
    const db: any = { setEnqueue() {}, getConfig: () => '', setConfig() {} }
    const worker = new SyncWorker(); worker.bind({ get, post: vi.fn() } as any, db)

    await worker.pullAndMergeResult(false)

    expect((get as any).mock.calls[0]?.[0]).toBe(SYNC_CONFIG.api.pull)
    expect((get as any).mock.calls[0]?.[2]).toBe(SYNC_CONFIG.timeout.pull)
  })

  it('pulls completion settlement snapshots idempotently without creating outbox entries', async () => {
    const db = new Database(createBetterSqliteAdapter())
    const worker = new SyncWorker()
    const payload = { ok: true, data: { status: 'ok', from_version: 0, to_version: 1, changes: [{ server_version: 1 }], server_time: '2026-09-01 09:01:00', tables: {
      sleep_score_settlements: [{ id: 'sleep-v2', sleep_date: '2026-09-01', metrics_snapshot: '{}', score_breakdown: '{}', score_total: 100, reward_amount: 80, cycle_penalty: 0, net_amount: 200, settlement_status: 'scored', missing_fields: '[]', rule_version: 'sleep-score-v2', occurred_at: '2026-09-01 09:00:00', created_at: '2026-09-01 09:00:00', updated_at: '2026-09-01 09:00:00', report_completed_at: '2026-09-01 08:59:00', is_all_complete: 1, completion_reward_amount: 100, completion_reason: '十项睡眠指标均满分', morning_diary_reward_status: 'completed', morning_diary_reward_amount: 10, morning_diary_reward_reason: '晨间日记已完成', morning_diary_reward_rule_version: 'v1', evening_diary_reward_status: 'completed', evening_diary_reward_amount: 10, evening_diary_reward_reason: '晚间日记已完成', evening_diary_reward_rule_version: 'v1' }],
      exercise_settlements: [{ id: 'exercise-v2', business_date: '2026-09-01', plan_version: 'v2', score_snapshot: '{}', score_total: 100, category_scores: '{}', completed_items: 1, total_items: 1, settlement_status: 'settled_reward', reason_code: 'score_band', rule_version: 'v1', coin_amount: 80, occurred_at: '2026-09-02 00:00:00', created_at: '2026-09-02 00:00:00', updated_at: '2026-09-02 00:00:00', is_all_complete: 1, completion_reward_amount: 100, completion_reason: '全部应评分条目满分' }],
    } } }
    worker.bind({ post: vi.fn(), get: vi.fn(async () => payload) } as any, db)
    await worker.pullAndMergeResult(true)
    await worker.pullAndMergeResult(true)
    expect(db.getExerciseSettlement('2026-09-01', 'v2')).toMatchObject({ is_all_complete: 1, completion_reward_amount: 100 })
    expect(db.getRecordById('sleep_score_settlements', 'sleep-v2')).toMatchObject({ report_completed_at: '2026-09-01 08:59:00', completion_reward_amount: 100, morning_diary_reward_amount: 10, evening_diary_reward_amount: 10 })
    expect(db.getPendingOutbox(20).some(item => ['exercise_settlements', 'sleep_score_settlements'].includes(item.table_name))).toBe(false)
  })

  it('keeps same-name category pulls isolated between account-local databases', async () => {
    const accountA = new Database(createBetterSqliteAdapter())
    const accountB = new Database(createBetterSqliteAdapter())
    accountA.runRaw("INSERT INTO categories(id,name,icon,color,group_name,sort_order,is_active,created_at) VALUES(26,'双账号分类','a','#111','默认',1,1,'x')")
    accountB.runRaw("INSERT INTO categories(id,name,icon,color,group_name,sort_order,is_active,created_at) VALUES(36,'双账号分类','b','#222','默认',1,1,'x')")
    const payload = (id: number, color: string) => ({ ok: true, data: { status: 'ok', from_version: 0, to_version: 1, server_time: 'server', tables: { categories: [{ id, name: '双账号分类', icon: 'server', color, group_name: '默认', sort_order: 1, is_active: 1, created_at: 'server', updated_at: 'server' }] } } })
    const first = new SyncWorker(); first.bind({ post: vi.fn(), get: vi.fn(async () => payload(46, '#f00')) } as any, accountA)
    const second = new SyncWorker(); second.bind({ post: vi.fn(), get: vi.fn(async () => payload(72, '#0f0')) } as any, accountB)

    await first.pullAndMergeResult(true)
    await second.pullAndMergeResult(true)

    expect(accountA.getRecordById('categories', 46)).toMatchObject({ color: '#f00' })
    expect(accountA.getRecordById('categories', 72)).toBeUndefined()
    expect(accountB.getRecordById('categories', 72)).toMatchObject({ color: '#0f0' })
    expect(accountB.getRecordById('categories', 46)).toBeUndefined()
  })

  it('converges server-owned flash recommendation statuses without outbox writes', async () => {
    const clients = [new Database(createBetterSqliteAdapter()), new Database(createBetterSqliteAdapter())]
    for (const db of clients) {
      const worker = new SyncWorker()
      worker.bind({ post: vi.fn(), get: vi.fn(async () => ({ ok: true, data: {
        status: 'ok', from_version: 0, to_version: 1, changes: [{ server_version: 1 }], server_time: '2026-08-13 10:30:00',
        tables: { flash_task_recommendations: [{ id: 'recommendation-1', flash_card_id: 'flash-1', ordinal: 0, title: '处理部署问题', reason: '明确待办', status: 'ignored', provider_task_id: null, ignored_at: '2026-08-13 10:29:00', created_at: '2026-08-13 10:00:00', updated_at: '2026-08-13 10:29:00' }] },
      } })) } as any, db)

      await worker.flushNow(false)
      expect(db.getRecordById('flash_task_recommendations', 'recommendation-1')).toMatchObject({ status: 'ignored', ignored_at: '2026-08-13 10:29:00' })
      expect(db.getPendingOutbox(20).some(item => item.table_name === 'flash_task_recommendations')).toBe(false)
    }
  })

  it('converges server-owned flash cards on two clients without creating outbox writes', async () => {
    const payloads = [
      { from_version: 0, to_version: 1, changes: [{ server_version: 1 }], tables: { flash_cards: [{ id: 'flash-1', occurred_at: '2026-08-10 09:00:00', original_text: '整理阅读计划', polished_text: null, analysis_status: 'processing', analysis_error_code: null, analysis_draft_id: null, deleted_at: null, created_at: '2026-08-10 09:00:00', updated_at: '2026-08-10 09:00:00' }] } },
      { from_version: 1, to_version: 2, changes: [{ server_version: 2 }], tables: { flash_cards: [{ id: 'flash-1', occurred_at: '2026-08-10 09:00:00', original_text: '整理阅读计划', polished_text: null, analysis_status: 'failed', analysis_error_code: 'flash_insight_analysis_failed', analysis_draft_id: null, deleted_at: null, created_at: '2026-08-10 09:00:00', updated_at: '2026-08-10 09:10:00' }] } },
      { from_version: 2, to_version: 3, changes: [{ server_version: 3 }], tables: { flash_cards: [{ id: 'flash-1', _sync_operation: 'delete' }] } },
    ]
    const clients = [new Database(createBetterSqliteAdapter()), new Database(createBetterSqliteAdapter())]
    for (const db of clients) {
      const worker = new SyncWorker()
      let pull = 0
      worker.bind({ post: vi.fn(), get: vi.fn(async () => ({ ok: true, data: { status: 'ok', server_time: '2026-08-10 09:10:00', ...payloads[pull++] } })) } as any, db)
      await worker.flushNow(true)
      expect(db.getRecordById('flash_cards', 'flash-1')).toMatchObject({ original_text: '整理阅读计划', polished_text: null })
      await worker.flushNow(true)
      expect(db.getRecordById('flash_cards', 'flash-1')).toMatchObject({ analysis_status: 'failed', analysis_error_code: 'flash_insight_analysis_failed' })
      await worker.flushNow(true)
      expect(db.getRecordById('flash_cards', 'flash-1')).toBeUndefined()
      expect(db.getPendingOutbox(20).some(item => item.table_name === 'flash_cards')).toBe(false)
    }
  })

  it('clears legacy server-owned outbox entries without pushing them', async () => {
    const worker = new SyncWorker()
    const post = vi.fn()
    const markOutboxSynced = vi.fn()
    const db: any = {
      setEnqueue() {}, getConfig: () => '', setConfig() {},
      getPendingOutbox: () => [{ id: 1, table_name: 'goals', change_id: 'goal-1', payload_json: '{}' }],
      markOutboxSynced,
    }
    worker.bind({ post } as any, db)

    expect(await (worker as any)._flushOutbox()).toMatchObject({ ok: true })
    expect(post).not.toHaveBeenCalled()
    expect(markOutboxSynced).toHaveBeenCalledWith([1], expect.any(String))
  })

  it('recovers interrupted sending once before startup sync', () => {
    const worker = new SyncWorker()
    const recover = vi.fn()
    const db: any = { setEnqueue: () => {}, recoverInterruptedOutboxSending: recover, getPendingOutbox: () => [], getConfig: () => '', setConfig: () => {} }
    worker.bind({ post: vi.fn(), get: vi.fn(async () => ({ ok: true, data: { status: 'ok', tables: {}, server_time: '2026-07-16 14:20:00' } })) } as any, db)
    worker.start(); worker.stop(); worker.start()
    expect(recover).toHaveBeenCalledTimes(1)
  })

  it('coalesces ordinary requests but reruns when SSE arrives in flight', async () => {
    const worker = new SyncWorker()
    let releasePush: (() => void) | undefined
    const post = vi.fn(() => new Promise(resolve => { releasePush = () => resolve({ ok: true, data: { status: 'ok' } }) }))
    const get = vi.fn(async () => ({ ok: true, data: { status: 'ok', tables: {}, server_time: '2026-07-14 15:10:00' } }))
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [{ id: 1, table_name: 'tasks', change_id: 'c1', payload_json: '{"source":"local"}' }],
      markOutboxSending: () => {}, markOutboxSynced: () => {}, getConfig: () => '', setConfig: () => {},
      getRecordById: () => null, getRecordByUnique: () => null,
    }
    worker.bind({ post, get } as any, db)

    const runs = [
      worker.requestSync('app-foreground'), worker.requestSync('network-online'),
      worker.requestSync('sse-changed'), worker.flushNow(false, { syncRunId: 'manual-run', reason: 'manual' }),
    ]
    await Promise.resolve()
    expect(post).toHaveBeenCalledTimes(1)
    releasePush?.()
    await Promise.all(runs)
    expect(post).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledTimes(2)
  })

  it.each(['sse-changed', 'server-change-followup'])('does not dedupe authoritative pull reason %s', async reason => {
    const get = vi.fn(async () => ({ ok: true, data: { status: 'ok', tables: {}, server_time: '2026-08-12 22:09:35' } }))
    const db: any = { setEnqueue() {}, getPendingOutbox: () => [], getConfig: () => '', setConfig() {} }
    const worker = new SyncWorker(); worker.bind({ get, post: vi.fn() } as any, db)

    await worker.requestSync('app-foreground')
    await worker.requestSync(reason)

    expect(get).toHaveBeenCalledTimes(2)
  })

  it('uses one push-free authoritative pull for completed-session SSE notifications', async () => {
    const get = vi.fn(async () => ({ ok: true, data: { status: 'ok', tables: {}, server_time: '2026-08-30 12:00:00' } }))
    const post = vi.fn()
    const worker = new SyncWorker()
    const db: any = { setEnqueue() {}, getPendingOutbox: () => [], getConfig: () => '', setConfig() {} }
    worker.bind({ get, post } as any, db)
    ;(worker as any)._lastPassivePullAt = Date.now()

    const first = (worker as any)._handleChangedEvent({ data: JSON.stringify({ tables: ['study_sessions'] }) })
    const second = (worker as any)._handleChangedEvent({ data: JSON.stringify({ tables: ['study_sessions'] }) })
    await Promise.all([first, second])

    expect(get).toHaveBeenCalledTimes(1)
    expect(post).not.toHaveBeenCalled()
  })

  it('keeps the existing sync path for changed notifications other than study sessions', async () => {
    const worker = new SyncWorker()
    const pullSessionVisibility = vi.spyOn(worker, 'pullSessionVisibility').mockResolvedValue({ ok: true, merged: 0 })
    const requestSync = vi.spyOn(worker, 'requestSync').mockResolvedValue({ ok: true, merged: 0 })

    await (worker as any)._handleChangedEvent({ data: JSON.stringify({ tables: ['tasks'] }) })

    expect(pullSessionVisibility).not.toHaveBeenCalled()
    expect(requestSync).toHaveBeenCalledWith('sse-changed')
  })

  it('ignores a versioned SSE event that the local cursor already covers', async () => {
    const worker = new SyncWorker()
    const requestSync = vi.spyOn(worker, 'requestSync').mockResolvedValue({ ok: true, merged: 0 })
    worker.bind({ get: vi.fn(), post: vi.fn() } as any, { setEnqueue() {}, getLastServerVersion: () => 12, getConfig: () => '', setConfig() {} } as any)

    await (worker as any)._handleChangedEvent({ data: JSON.stringify({ tables: ['goals'], server_version: 12 }) })

    expect(requestSync).not.toHaveBeenCalled()
  })

  it('performs one version follow-up only when an SSE version exceeds the in-flight pull result', async () => {
    const worker = new SyncWorker()
    let savedVersion = 4
    let releaseFirst: ((value: any) => void) | undefined
    const get = vi.fn(() => get.mock.calls.length === 1
      ? new Promise(resolve => { releaseFirst = resolve })
      : Promise.resolve({ ok: true, status: 200, data: { status: 'ok', from_version: 5, to_version: 6, tables: {}, server_time: '2026-09-12 12:00:00' } }))
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value }, getConfig: () => '', setConfig() {},
    }
    worker.bind({ get, post: vi.fn() } as any, db)

    const initial = worker.requestSync('manual')
    await Promise.resolve()
    const changed = (worker as any)._handleChangedEvent({ data: JSON.stringify({ tables: ['goals'], server_version: 6 }) })
    releaseFirst?.({ ok: true, status: 200, data: { status: 'ok', from_version: 4, to_version: 5, tables: {}, server_time: '2026-09-12 12:00:00' } })
    await Promise.all([initial, changed])

    expect(get).toHaveBeenCalledTimes(2)
    expect(savedVersion).toBe(6)
  })

  it('retries exactly once after a transient core Pull failure', async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 0, error: 'request_timeout' })
      .mockResolvedValueOnce({ ok: true, status: 200, data: { status: 'ok', tables: {}, server_time: '2026-09-12 12:00:00' } })
    const worker = new SyncWorker(); worker.bind({ get, post: vi.fn() } as any, { setEnqueue() {}, getConfig: () => '', setConfig() {} } as any)

    const result = await worker.pullAndMergeResult(false)

    expect(get).toHaveBeenCalledTimes(2)
    expect(result.diagnostics?.retry).toBe(1)
  })

  it('does not retry an authentication or server Pull failure', async () => {
    const get = vi.fn(async () => ({ ok: false, status: 401, error: 'auth_expired' }))
    const worker = new SyncWorker(); worker.bind({ get, post: vi.fn() } as any, { setEnqueue() {}, getConfig: () => '', setConfig() {} } as any)

    await worker.pullAndMergeResult(false)

    expect(get).toHaveBeenCalledTimes(1)
  })

  it('waits for an active sync before the completed-session follow-up pull', async () => {
    const worker = new SyncWorker()
    let releasePush: (() => void) | undefined
    let activePulls = 0
    let maxActivePulls = 0
    let pending = true
    const post = vi.fn(() => new Promise(resolve => { releasePush = () => resolve({ ok: true, data: { status: 'ok' } }) }))
    const get = vi.fn(async () => {
      activePulls += 1
      maxActivePulls = Math.max(maxActivePulls, activePulls)
      await Promise.resolve()
      activePulls -= 1
      return { ok: true, data: { status: 'ok', tables: {}, server_time: '2026-08-30 12:00:00' } }
    })
    const db: any = {
      setEnqueue() {}, getConfig: () => '', setConfig() {},
      getPendingOutbox: () => pending ? [{ id: 1, table_name: 'tasks', change_id: 'task-1', payload_json: '{"source":"local"}' }] : [],
      markOutboxSending() {}, markOutboxSynced() { pending = false },
    }
    worker.bind({ get, post } as any, db)

    const backgroundSync = worker.requestSync('manual')
    await Promise.resolve()
    const visibilityPull = worker.pullSessionVisibility()
    releasePush?.()
    await Promise.all([backgroundSync, visibilityPull])

    expect(post).toHaveBeenCalledTimes(1)
    expect(maxActivePulls).toBe(1)
    expect(get).toHaveBeenCalledTimes(1)
  })

  for (const localStatus of [1, 2]) {
    it(`applies habit status ${localStatus} -> 0 even when pushed_at is null`, async () => {
      const worker = new SyncWorker()
      let savedVersion = 10
      const writes: { sql: string; params: any[] }[] = []
      const db: any = {
        setEnqueue: () => {}, getPendingOutbox: () => [], hasPendingOutbox: () => false,
        getLastServerVersion: () => savedVersion, setLastServerVersion: (v: number) => { savedVersion = v },
        getConfig: () => '', setConfig: () => {}, getRecordByUnique: () => null,
        getRecordById: () => ({ id: 'check-1', status: localStatus, pushed_at: null }),
        runRaw: (sql: string, params: any[]) => writes.push({ sql, params }),
        runInTransaction: (fn: () => void) => fn(),
      }
      const api: any = { post: async () => ({ ok: true, data: { status: 'ok' } }), get: async () => ({
        ok: true, data: { status: 'ok', from_version: 10, to_version: 11,
          changes: [{ server_version: 11 }], server_time: '2026-06-19 12:00:00',
          tables: { habit_checkins: [{ id: 'check-1', habit_id: 'habit-1', checkin_date: '2026-06-19', status: 0, updated_at: '2026-06-19 11:59:00' }] } },
      }) }

      worker.bind(api, db)
      const result = await worker.flushNow(false)

      expect(result.ok).toBe(true)
      expect(savedVersion).toBe(11)
      expect(writes[0].sql).toContain('pulled_at')
      expect(writes[0].params).toContain(0)
      expect(writes[0].params).toContain(null)
    })
  }

  it('keeps cursor when the same record has pending outbox', async () => {
    const worker = new SyncWorker()
    let savedVersion = 20
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], hasPendingOutbox: () => true,
      getLastServerVersion: () => savedVersion, setLastServerVersion: (v: number) => { savedVersion = v },
      getConfig: () => '', setConfig: () => {}, getRecordByUnique: () => null,
      getRecordById: () => ({ id: 'task-1', title: 'local' }), runRaw: () => {},
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = { post: async () => ({ ok: true, data: { status: 'ok' } }), get: async () => ({
      ok: true, data: { status: 'ok', from_version: 20, to_version: 21,
        changes: [{ server_version: 21 }], server_time: '2026-06-19 12:00:00',
        tables: { tasks: [{ id: 'task-1', title: 'server', updated_at: '2026-06-19 11:00:00' }] } },
    }) }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(false)
    expect(result.error).toBe('local_outbox_conflict')
    expect(savedVersion).toBe(20)
    expect(result.diagnostics?.merge.conflicts).toEqual(['tasks:task-1'])
  })

  it('does not advance last_server_version when local merge fails', async () => {
    const worker = new SyncWorker()
    let savedVersion = 7
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: () => null,
      runRaw: () => { throw new Error('merge boom') },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 7,
          to_version: 8,
          changes: [{ server_version: 8 }],
          tables: {
            tasks: [{
              id: 'task-1',
              title: 'server task',
              status: 0,
              updated_at: '2026-06-13 10:00:00',
            }],
          },
          server_time: '2026-06-13 10:01:00',
          diagnostics: { protocol: 'server_version' },
        },
      }),
      post: async () => ({ ok: true, data: { status: 'ok' } }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(false)
    expect(result.error).toBe('local_merge_failed')
    expect(savedVersion).toBe(7)
    expect(result.diagnostics?.merge.failed).toBe(1)
  })

  it('replaces the local ledger from a server snapshot before advancing the cursor', async () => {
    const worker = new SyncWorker(); let version = 7
    const replaceServerLedgerSnapshot = vi.fn(() => ({ removed: 3, balance: 9.7 }))
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      getLedgerSnapshotVersion: () => 7, hasConsistentLedgerSnapshot: () => false, setLastServerVersion: (next: number) => { version = next },
      getConfig: () => '', setConfig: () => {}, getRecordById: () => null, getRecordByUnique: () => null,
      getLedgerSummary: () => ({ balance: 6.7, income: 13.7, expense: 7 }), replaceServerLedgerSnapshot, runInTransaction: (fn: () => void) => fn(),
    }
    const get = vi.fn(async (_path: string, params: any) => ({ ok: true, data: {
      status: 'ok', from_version: 7, to_version: 8, changes: [{ server_version: 8 }], tables: { reward_ledger: [{ id: 'incremental' }] },
      ledger_snapshot: { rows: [{ id: 'server', amount: 9.7 }], summary: { balance: 9.7, income: 13.7, expense: 4 }, integrity: { count: 1, sha256: 'a'.repeat(64) } },
      server_time: '2026-08-05 12:00:00',
    } }))
    worker.bind({ get, post: vi.fn() } as any, db)

    expect(await worker.flushNow(false)).toMatchObject({ ok: true })
    expect(get.mock.calls[0][1]).toMatchObject({ since_version: '7', ledger_snapshot: 'true' })
    expect(replaceServerLedgerSnapshot).toHaveBeenCalledWith(expect.any(Object), 8)
    expect(version).toBe(8)
  })

  it('repairs an Android core pull when the new ledger row is visible but its total differs from the server wallet', async () => {
    const db = new Database(createBetterSqliteAdapter()) as any
    const stamp = '2026-09-14 14:00:00'
    const row = (id: string, amount: number) => ({ id, amount, source_type: 'test_reward', target_date: '2026-09-14', created_at: stamp, updated_at: stamp })
    const snapshot = (rows: any[], balance: number) => ({ rows, summary: { balance, income: rows.reduce((sum, item) => sum + Math.max(item.amount, 0), 0), expense: rows.reduce((sum, item) => sum + Math.max(-item.amount, 0), 0) }, integrity: { count: rows.length, sha256: 'a'.repeat(64) } })
    db.replaceServerLedgerSnapshot(snapshot([row('old-penalty', -5)], -5), 8)
    db.setLastServerVersion(8)
    db.androidBulk = {
      query: (sql: string, params: any[] = []) => db.allRaw(sql, params),
      transaction: (operations: Array<{ sql: string; params?: any[] }>) => db.runInTransaction(() => operations.forEach(operation => db.runRaw(operation.sql, operation.params || []))),
      yieldToUi: async () => {},
    }
    const get = vi.fn(async (_path: string, params: Record<string, string>) => ({ ok: true, data: params.ledger_snapshot
      ? { status: 'ok', from_version: 8, to_version: 9, server_time: stamp, wallet: { balance: 15 }, tables: {}, ledger_snapshot: snapshot([row('old-penalty', -5), row('missing-reward', 10), row('new-reward', 10)], 15) }
      : { status: 'ok', from_version: 8, to_version: 9, server_time: stamp, wallet: { balance: 15 }, tables: { reward_ledger: [row('new-reward', 10)] } } }))
    const worker = new SyncWorker(); worker.bind({ get, post: vi.fn() } as any, db)
    const observedBalances: number[] = []
    const previousWindow = (globalThis as any).window
    ;(globalThis as any).window = { CustomEvent: class { constructor(public type: string) {} },
      dispatchEvent: (event: { type: string }) => { if (event.type === 'sync-pull-complete') observedBalances.push(db.getBalance()) } }

    let result: any
    try { result = await worker.flushNow(false, { reason: 'sse-changed' }) }
    finally { (globalThis as any).window = previousWindow }

    expect(result.ok).toBe(true)
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[1][1]).toMatchObject({ sync_scope: 'core', ledger_snapshot: 'true' })
    expect(db.getLedgerFull(10, 0).some((entry: any) => entry.id === 'new-reward')).toBe(true)
    expect(db.getBalance()).toBe(15)
    expect(observedBalances).toEqual([15])
    expect(db.getLastServerVersion()).toBe(9)
  })

  it('does not advance the core cursor or claim success when a wallet mismatch cannot be repaired', async () => {
    let version = 8
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      getLedgerSnapshotVersion: () => 8, hasConsistentLedgerSnapshot: () => true,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig() {},
      getLedgerSummary: () => ({ balance: 5 }), runInTransaction: (fn: () => void) => fn(),
    }
    const get = vi.fn(async (_path: string, _params: Record<string, string>) => ({ ok: true, data: { status: 'ok', from_version: 8, to_version: 9,
      server_time: '2026-09-14 14:00:00', wallet: { balance: 15 }, tables: {} } }))
    const worker = new SyncWorker(); worker.bind({ get, post: vi.fn() } as any, db)

    const result = await worker.flushNow(false, { reason: 'sse-changed' })

    expect(result).toMatchObject({ ok: false, error: 'wallet_balance_mismatch' })
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[1][1]).toMatchObject({ ledger_snapshot: 'true', sync_scope: 'core' })
    expect(version).toBe(8)
  })

  it('confirms a diary reward only after the forced core ledger snapshot is merged', async () => {
    const worker = new SyncWorker(); let version = 8
    const replaceServerLedgerSnapshot = vi.fn(() => ({ removed: 0, balance: 10 }))
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      getLedgerSnapshotVersion: () => 8, hasConsistentLedgerSnapshot: () => true,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig: () => {},
      getLedgerSummary: () => ({ balance: 0 }), replaceServerLedgerSnapshot, runInTransaction: (fn: () => void) => fn(),
    }
    const get = vi.fn(async (_path: string, params: any) => ({ ok: true, data: {
      status: 'ok', from_version: 8, to_version: 9, changes: [{ server_version: 9 }], tables: {},
      ledger_snapshot: { rows: [{ id: 'morning', source_type: 'sleep_morning_diary_reward', target_date: '2026-09-14', amount: 10 }], summary: { balance: 10 }, integrity: { count: 1, sha256: 'a'.repeat(64) } },
      server_time: '2026-09-14 09:00:00',
    } }))
    worker.bind({ get, post: vi.fn() } as any, db)

    const result = await worker.flushNow(false, { reason: 'sleep-morning-diary-save', ledgerExpectation: {
      sourceType: 'sleep_morning_diary_reward', targetDate: '2026-09-14', exists: true,
    } })

    expect(result.ok).toBe(true)
    expect(result.diagnostics?.ledger_expectation).toMatchObject({ confirmed: true, attempt: 0 })
    expect(get.mock.calls[0][1]).toMatchObject({ since_version: '8', ledger_snapshot: 'true', sync_scope: 'core' })
    expect(replaceServerLedgerSnapshot).toHaveBeenCalledOnce()
    expect(version).toBe(9)
  })

  it('runs a fresh diary push and ledger pull when another core sync is already in flight', async () => {
    const worker = new SyncWorker(); let version = 8
    let releaseFirst: ((value: any) => void) | undefined
    const get = vi.fn((_path: string, params: any) => get.mock.calls.length === 1
      ? new Promise(resolve => { releaseFirst = resolve })
      : Promise.resolve({ ok: true, data: {
          status: 'ok', from_version: 8, to_version: 9, tables: {},
          ledger_snapshot: { rows: [{ id: 'morning', source_type: 'sleep_morning_diary_reward', target_date: '2026-09-14', amount: 10 }], summary: { balance: 10 }, integrity: { count: 1, sha256: 'a'.repeat(64) } },
          server_time: '2026-09-14 13:43:00',
        } }))
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      getLedgerSnapshotVersion: () => 8, hasConsistentLedgerSnapshot: () => true,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig() {},
      getLedgerSummary: () => ({ balance: 0 }), replaceServerLedgerSnapshot: vi.fn(() => ({ removed: 0, balance: 10 })),
      runInTransaction: (fn: () => void) => fn(),
    }
    worker.bind({ get, post: vi.fn() } as any, db)

    const first = worker.requestSync('user-action')
    await Promise.resolve()
    const diary = worker.flushNow(false, { reason: 'sleep-morning-diary-save', ledgerExpectation: {
      sourceType: 'sleep_morning_diary_reward', targetDate: '2026-09-14', exists: true,
    } })
    releaseFirst?.({ ok: true, data: { status: 'ok', from_version: 8, to_version: 8, tables: {}, server_time: '2026-09-14 13:42:59' } })
    await first
    const result = await diary

    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[1][1]).toMatchObject({ ledger_snapshot: 'true', sync_scope: 'core' })
    expect(result.diagnostics?.ledger_expectation?.confirmed).toBe(true)
    expect(version).toBe(9)
  })

  it('keeps a diary reward unconfirmed and the cursor unchanged after bounded core retries', async () => {
    const worker = new SyncWorker(); let version = 8
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      getLedgerSnapshotVersion: () => 8, hasConsistentLedgerSnapshot: () => true,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig: () => {},
      getLedgerSummary: () => ({ balance: 0 }), replaceServerLedgerSnapshot: () => ({ removed: 0, balance: 0 }), runInTransaction: (fn: () => void) => fn(),
    }
    const get = vi.fn(async () => ({ ok: true, data: {
      status: 'ok', from_version: 8, to_version: 9, changes: [{ server_version: 9 }], tables: {},
      ledger_snapshot: { rows: [], summary: { balance: 0 }, integrity: { count: 0, sha256: 'a'.repeat(64) } }, server_time: '2026-09-14 09:00:00',
    } }))
    worker.bind({ get, post: vi.fn() } as any, db)

    const result = await worker.flushNow(false, { reason: 'sleep-morning-diary-save', ledgerExpectation: {
      sourceType: 'sleep_morning_diary_reward', targetDate: '2026-09-14', exists: true,
    } })

    expect(result).toMatchObject({ ok: false, error: 'ledger_confirmation_pending' })
    expect(result.diagnostics?.ledger_expectation).toMatchObject({ confirmed: false, attempt: 1 })
    expect(get).toHaveBeenCalledTimes(2)
    expect(version).toBe(8)
  })

  it('confirms the same expected reward through the Android bulk merge path', async () => {
    const worker = new SyncWorker(); let version = 3
    const bulk = { query: () => [], transaction: vi.fn(), yieldToUi: async () => {} }
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      getLedgerSnapshotVersion: () => 3, hasConsistentLedgerSnapshot: () => true,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig: () => {},
      getLedgerSummary: () => ({ balance: 0 }), replaceServerLedgerSnapshot: () => ({ removed: 0, balance: 10 }), androidBulk: bulk,
      runInTransaction: (fn: () => void) => fn(),
    }
    worker.bind({ post: vi.fn(), get: async () => ({ ok: true, data: {
      status: 'ok', from_version: 3, to_version: 4, changes: [{ server_version: 4 }], tables: {},
      ledger_snapshot: { rows: [{ id: 'morning', source_type: 'sleep_morning_diary_reward', target_date: '2026-09-14', amount: 10 }], summary: { balance: 10 }, integrity: { count: 1, sha256: 'a'.repeat(64) } }, server_time: '2026-09-14 09:00:00',
    } }) } as any, db)

    const result = await worker.flushNow(false, { ledgerExpectation: { sourceType: 'sleep_morning_diary_reward', targetDate: '2026-09-14', exists: true } })
    expect(result.diagnostics?.ledger_expectation?.confirmed).toBe(true)
    expect(version).toBe(4)
  })

  it('keeps the cursor when server ledger snapshot replacement fails', async () => {
    const worker = new SyncWorker(); let version = 7
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], getLastServerVersion: () => version, getLedgerSnapshotVersion: () => 0,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig: () => {}, replaceServerLedgerSnapshot: () => { throw new Error('invalid_server_ledger_snapshot') },
    }
    worker.bind({ get: async () => ({ ok: true, data: { status: 'ok', from_version: 7, to_version: 8, tables: {}, ledger_snapshot: { summary: {}, integrity: {} } } }), post: vi.fn() } as any, db)

    await expect(worker.flushNow(false)).resolves.toMatchObject({ ok: false, error: 'ledger_snapshot_failed' })
    expect(version).toBe(7)
  })

  it('defers habit checkins when parent habit is missing locally', async () => {
    const worker = new SyncWorker()
    let savedVersion = 22
    const writes: { sql: string; params: any[] }[] = []
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      hasPendingOutbox: () => false,
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: () => null,
      runRaw: (sql: string, params: any[]) => { writes.push({ sql, params }) },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      post: async () => ({ ok: true, data: { status: 'ok' } }),
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 22,
          to_version: 23,
          changes: [{ server_version: 23 }],
          tables: {
            habit_checkins: [{
              id: 'check-missing-parent',
              habit_id: 'habit-missing',
              checkin_date: '2026-07-08',
              status: 2,
              updated_at: '2026-07-08 22:00:00',
            }],
          },
          server_time: '2026-07-08 22:01:00',
        },
      }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false, { syncRunId: 'run-missing-parent' })

    expect(result.ok).toBe(false)
    expect(result.error).toBe('local_merge_failed')
    expect(savedVersion).toBe(22)
    expect(writes).toEqual([])
    expect(result.diagnostics?.merge.skipped).toEqual(['habit_checkins:check-missing-parent:missing_parent'])
  })

  it('applies reset marker and checkin tombstone without requiring a parent', async () => {
    const worker = new SyncWorker(); let savedVersion = 30
    const reset = vi.fn(() => ({ applied: true, tasks: 1, habits: 1, checkins: 1, rewards: 1 }))
    const writes: string[] = []
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], hasPendingOutbox: () => false,
      getLastServerVersion: () => savedVersion, setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '', setConfig: () => {}, getRecordById: () => null, getRecordByUnique: () => null,
      applyChecklistResetMarker: reset, runRaw: (sql: string) => writes.push(sql),
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = { post: async () => ({ ok: true, data: { status: 'ok' } }), get: async () => ({
      ok: true, data: { status: 'ok', from_version: 30, to_version: 32, server_time: '2026-07-29 12:00:00',
        tables: {
          system_config: [{ key: 'checklist_ticktick_reset_marker', value: 'marker-1', updated_at: '2026-07-29 12:00:00' }],
          habit_checkins: [{ id: 'old-checkin', _sync_operation: 'delete', updated_at: '2026-07-29 12:00:00' }],
        } },
    }) }
    worker.bind(api, db)
    const result = await worker.flushNow(false)
    expect(result.ok).toBe(true)
    expect(savedVersion).toBe(32)
    expect(reset).toHaveBeenCalledWith('marker-1')
    expect(writes.some(sql => sql.startsWith('DELETE FROM habit_checkins'))).toBe(true)
  })

  it('applies habit parent before checkins from the same pull', async () => {
    const worker = new SyncWorker()
    let savedVersion = 24
    let parentSaved = false
    const writes: { sql: string; params: any[] }[] = []
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      hasPendingOutbox: () => false,
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: (table: string, id: string) => (
        table === 'habits' && id === 'habit-parent' && parentSaved ? { id: 'habit-parent' } : null
      ),
      getRecordByUnique: () => null,
      runRaw: (sql: string, params: any[]) => {
        writes.push({ sql, params })
        if (sql.includes('INSERT INTO habits')) parentSaved = true
      },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      post: async () => ({ ok: true, data: { status: 'ok' } }),
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 24,
          to_version: 25,
          changes: [{ server_version: 25 }],
          tables: {
            habits: [{
              id: 'habit-parent',
              name: '洗碗',
              icon: '',
              color: '#A3BE8C',
              sort_order: 1,
              is_active: 0,
              difficulty: 'easy',
              created_at: '2026-07-08 08:00:00',
              updated_at: '2026-07-08 08:00:00',
            }],
            habit_checkins: [{
              id: 'check-with-parent',
              habit_id: 'habit-parent',
              checkin_date: '2026-07-08',
              status: 2,
              updated_at: '2026-07-08 22:00:00',
            }],
          },
          server_time: '2026-07-08 22:01:00',
        },
      }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(true)
    expect(savedVersion).toBe(25)
    expect(writes.map(write => write.sql)).toEqual([
      expect.stringContaining('INSERT INTO habits'),
      expect.stringContaining('INSERT INTO habit_checkins'),
    ])
  })

  it('merges huawei sleep data by date when server and local ids differ', async () => {
    const worker = new SyncWorker()
    let savedVersion = 14
    const writes: { sql: string; params: any[] }[] = []
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: (table: string, pk: string, value: any) => (
        table === 'huawei_sleep_data' && pk === 'date' && value === '2026-07-01'
          ? { id: 2, date: '2026-07-01', sleep_score: 70, pushed_at: null }
          : null
      ),
      hasPendingOutbox: (table: string, value: any) => table === 'huawei_sleep_data' && value === '2026-07-01' ? false : false,
      allRaw: (sql: string) => sql.includes('PRAGMA table_info(huawei_sleep_data)')
        ? [
          { name: 'id' }, { name: 'date' }, { name: 'sleep_score' }, { name: 'total_sleep_min' },
          { name: 'analysis_html' }, { name: 'report_status' }, { name: 'updated_at' },
          { name: 'pulled_at' }, { name: 'pushed_at' },
        ]
        : [],
      runRaw: (sql: string, params: any[]) => { writes.push({ sql, params }) },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 14,
          to_version: 15,
          changes: [{ server_version: 15 }],
          tables: {
            huawei_sleep_data: [{
              id: 99,
              date: '2026-07-01',
              sleep_score: 77,
              total_sleep_min: 343,
              analysis_html: '<p>睡眠报告</p>',
              report_status: 1,
              updated_at: '2026-07-01 20:26:15',
            }],
          },
          server_time: '2026-07-01 20:27:00',
        },
      }),
      post: async () => ({ ok: true, data: { status: 'ok' } }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(true)
    expect(savedVersion).toBe(15)
    expect(writes[0].sql).toContain('INSERT INTO huawei_sleep_data')
    expect(writes[0].params).toContain(2)
    expect(writes[0].params).not.toContain(99)
    expect(writes[0].params).toContain('2026-07-01')
  })

  it('still pulls huawei sleep data after outbox push fails', async () => {
    const worker = new SyncWorker()
    let savedVersion = 70
    const writes: { sql: string; params: any[] }[] = []
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [{
        id: 1,
        change_id: 'local-change-1',
        device_id: 'desktop',
        table_name: 'tasks',
        record_id: 'task-1',
        operation: 'upsert',
        payload_json: '{"id":"task-1","title":"local","source":"local"}',
      }],
      markOutboxSending: () => {},
      markOutboxFailed: () => {},
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: () => null,
      hasPendingOutbox: () => false,
      allRaw: (sql: string) => sql.includes('PRAGMA table_info(huawei_sleep_data)')
        ? [
          { name: 'id' }, { name: 'date' }, { name: 'sleep_score' },
          { name: 'analysis_html' }, { name: 'report_status' },
          { name: 'updated_at' }, { name: 'pulled_at' }, { name: 'pushed_at' },
        ]
        : [],
      runRaw: (sql: string, params: any[]) => { writes.push({ sql, params }) },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      post: async () => ({ ok: false, error: 'cors_preflight_failed' }),
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 70,
          to_version: 71,
          changes: [{ server_version: 71 }],
          tables: {
            huawei_sleep_data: [{
              id: 100,
              date: '2026-07-05',
              sleep_score: 88,
              analysis_html: '<p>server report</p>',
              report_status: 1,
              updated_at: '2026-07-05 22:00:00',
            }],
          },
          server_time: '2026-07-05 22:01:00',
        },
      }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false, { syncRunId: 'run-1', reason: 'sleep-date-switch' })

    expect(result.ok).toBe(true)
    expect(result.merged).toBe(1)
    expect(savedVersion).toBe(71)
    expect(result.diagnostics?.push.error).toBe('cors_preflight_failed')
    expect(writes[0].sql).toContain('INSERT INTO huawei_sleep_data')
    expect(writes[0].params).toContain('2026-07-05')
  })

  it('preserves per-change acceptance when another operation and pull fail', async () => {
    const worker = new SyncWorker()
    const entries = ['diary-change', 'other-change'].map((change_id, index) => ({
      id: index + 1, change_id, device_id: 'desktop', table_name: index ? 'tasks' : 'huawei_sleep_data',
      record_id: String(index + 1), operation: 'upsert', payload_json: index
        ? '{"id":"task-1","title":"bad"}' : '{"id":1,"date":"2026-09-08","morning_diary":"晨记"}',
    }))
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => entries, markOutboxSending() {}, markOutboxSynced() {}, markOutboxFailed() {},
      getConfig: () => '', setConfig() {}, getLastServerVersion: () => 0,
    }
    const api: any = {
      post: async () => ({ ok: true, data: { status: 'ok', operation_results: [
        { change_id: 'diary-change', table: 'huawei_sleep_data', status: 'accepted' },
        { change_id: 'other-change', table: 'tasks', status: 'rejected', reason: 'other_failed' },
      ] } }),
      get: async () => ({ ok: false, status: 0, error: 'server_unreachable' }),
    }
    worker.bind(api, db)

    const result = await worker.flushNow(false, { reason: 'sleep-morning-diary-save' })

    expect(result.diagnostics?.push.operation_results).toEqual(expect.arrayContaining([
      expect.objectContaining({ change_id: 'diary-change', status: 'accepted' }),
      expect.objectContaining({ change_id: 'other-change', status: 'rejected', reason: 'other_failed' }),
    ]))
  })

  it('reports huawei merge failures with date diagnostics', async () => {
    const worker = new SyncWorker()
    let savedVersion = 30
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      hasPendingOutbox: () => false,
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: () => null,
      allRaw: () => ['id', 'date', 'sleep_score', 'updated_at', 'pushed_at', 'pulled_at'].map(name => ({ name })),
      runRaw: () => { throw new Error('merge boom') },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 30,
          to_version: 31,
          changes: [{ server_version: 31 }],
          tables: {
            huawei_sleep_data: [{
              id: 99,
              date: '2026-07-01',
              sleep_score: 77,
              updated_at: '2026-07-01 20:26:15',
            }],
          },
          server_time: '2026-07-01 20:27:00',
        },
      }),
      post: async () => ({ ok: true, data: { status: 'ok' } }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(false)
    expect(result.error).toBe('local_merge_failed')
    expect(savedVersion).toBe(30)
    expect(result.diagnostics?.merge.errors).toEqual(['huawei_sleep_data:2026-07-01:sqlite_operation_failed'])
  })

  it('keeps huawei cursor when matching local date has pending outbox by local id', async () => {
    const worker = new SyncWorker()
    let savedVersion = 40
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: () => ({ id: 2, date: '2026-07-01', sleep_score: 70, updated_at: '2026-07-01 20:30:00' }),
      hasPendingOutbox: (table: string, value: any) => table === 'huawei_sleep_data' && value === 2,
      runRaw: () => { throw new Error('should not merge') },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 40,
          to_version: 41,
          changes: [{ server_version: 41 }],
          tables: {
            huawei_sleep_data: [{
              id: 99,
              date: '2026-07-01',
              sleep_score: 77,
              updated_at: '2026-07-01 20:26:15',
            }],
          },
          server_time: '2026-07-01 20:27:00',
        },
      }),
      post: async () => ({ ok: true, data: { status: 'ok' } }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(false)
    expect(result.error).toBe('local_outbox_conflict')
    expect(savedVersion).toBe(40)
    expect(result.diagnostics?.merge.conflicts).toEqual(['huawei_sleep_data:2026-07-01'])
  })

  it('filters server-only exercise checkin columns before local merge', async () => {
    const worker = new SyncWorker()
    let savedVersion = 0
    const inserts: { sql: string; params: any[] }[] = []
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: () => null,
      allRaw: (sql: string) => sql.includes('PRAGMA table_info(exercise_checkins)')
        ? [
          { name: 'id' }, { name: 'date' }, { name: 'plan_version' }, { name: 'item_key' },
          { name: 'status' }, { name: 'completed_time' }, { name: 'plan_item_id' },
          { name: 'item_name' }, { name: 'note' }, { name: 'created_at' },
          { name: 'updated_at' }, { name: 'pushed_at' }, { name: 'pulled_at' },
        ]
        : [],
      runRaw: (sql: string, params: any[]) => { inserts.push({ sql, params }) },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 0,
          to_version: 1,
          changes: [{ server_version: 1 }],
          tables: {
            exercise_checkins: [{
              id: 'checkin-1',
              log_id: 'server-log-1',
              date: '2026-06-29',
              plan_version: 'v0',
              item_key: 'plank',
              status: 1,
              updated_at: '2026-06-29 10:00:00',
            }],
          },
          server_time: '2026-06-29 10:01:00',
        },
      }),
      post: async () => ({ ok: true, data: { status: 'ok' } }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(true)
    expect(savedVersion).toBe(1)
    expect(inserts[0].sql).toContain('INSERT INTO exercise_checkins')
    expect(inserts[0].sql).not.toContain('log_id')
    expect(inserts[0].params).not.toContain('server-log-1')
  })

  it('fills required local exercise daily log fields from server records', async () => {
    const worker = new SyncWorker()
    let savedVersion = 50
    const writes: { sql: string; params: any[] }[] = []
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      hasPendingOutbox: () => false,
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: () => null,
      allRaw: (sql: string) => sql.includes('PRAGMA table_info(exercise_daily_logs)')
        ? [
          { name: 'id' }, { name: 'date' }, { name: 'plan_version' }, { name: 'week_num' },
          { name: 'day_name' }, { name: 'completed_items' }, { name: 'total_items' },
          { name: 'score_snapshot' }, { name: 'created_at' }, { name: 'updated_at' },
          { name: 'pulled_at' }, { name: 'pushed_at' },
        ]
        : [],
      runRaw: (sql: string, params: any[]) => { writes.push({ sql, params }) },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 50,
          to_version: 51,
          changes: [{ server_version: 51 }],
          tables: {
            exercise_daily_logs: [{
              id: 'server-log-1',
              date: '2026-07-01',
              plan_version: 'v0',
              exercise_type: 'daily',
              updated_at: '2026-07-01 20:00:00',
            }],
          },
          server_time: '2026-07-01 20:01:00',
        },
      }),
      post: async () => ({ ok: true, data: { status: 'ok' } }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(true)
    expect(savedVersion).toBe(51)
    expect(writes[0].sql).toContain('INSERT INTO exercise_daily_logs')
    expect(writes[0].sql).toContain('week_num')
    expect(writes[0].sql).toContain('day_name')
    expect(writes[0].params).toContain(1)
    expect(writes[0].params).toContain('daily')
  })

  it('merges provider fingerprint columns when local schema matches server schema', async () => {
    const worker = new SyncWorker()
    let savedVersion = 0
    const inserts: { sql: string; params: any[] }[] = []
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: () => '',
      setConfig: () => {},
      getRecordById: () => null,
      getRecordByUnique: () => null,
      runRaw: (sql: string, params: any[]) => { inserts.push({ sql, params }) },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 0,
          to_version: 1,
          changes: [{ server_version: 1 }],
          tables: {
            tasks: [{
              id: 'task-1',
              title: 'server task',
              status: 0,
              source_etag: 'server-only-etag',
              source_modified_time: 'server-only-mtime',
              updated_at: '2026-06-14 10:00:00',
            }],
          },
          server_time: '2026-06-14 10:01:00',
          diagnostics: { protocol: 'server_version' },
        },
      }),
      post: async () => ({ ok: true, data: { status: 'ok' } }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(true)
    expect(savedVersion).toBe(1)
    expect(inserts[0].sql).toContain('source_etag')
    expect(inserts[0].sql).toContain('source_modified_time')
    expect(inserts[0].sql).toContain('INSERT INTO tasks')
  })

  it('merges existing user wallet rows without writing an id column', async () => {
    const worker = new SyncWorker()
    let savedVersion = 352
    const writes: { sql: string; params: any[] }[] = []
    const config: Record<string, string> = { wallet_balance: '0' }
    const db: any = {
      setEnqueue: () => {},
      getPendingOutbox: () => [],
      getLastServerVersion: () => savedVersion,
      setLastServerVersion: (value: number) => { savedVersion = value },
      getConfig: (key: string) => config[key] ?? '',
      setConfig: (key: string, value: string) => { config[key] = String(value) },
      getRecordById: () => null,
      getRecordByUnique: (table: string, pk: string, value: any) => (
        table === 'user_wallets' && pk === 'user_id' && value === 1
          ? { user_id: 1, balance: -10, updated_at: '2026-06-18 10:00:00' }
          : null
      ),
      runRaw: (sql: string, params: any[]) => { writes.push({ sql, params }) },
      runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = {
      get: async () => ({
        ok: true,
        data: {
          status: 'ok',
          from_version: 352,
          to_version: 354,
          changes: [{ server_version: 354 }],
          tables: {
            user_wallets: [{
              user_id: 1,
              balance: -9.5,
              updated_at: '2026-06-19 10:00:00',
            }],
          },
          server_time: '2026-06-19 10:01:00',
          diagnostics: { protocol: 'server_version' },
        },
      }),
      post: async () => ({ ok: true, data: { status: 'ok' } }),
    }

    worker.bind(api, db)
    const result = await worker.flushNow(false)

    expect(result.ok).toBe(true)
    expect(savedVersion).toBe(354)
    expect(config.wallet_balance).toBe('-9.5')
    expect(writes[0].sql).toContain('INSERT INTO user_wallets')
    expect(writes[0].sql).not.toMatch(/\bid\b/)
    expect(writes[0].sql).toContain('user_id')
  })

  it('emits an authentication challenge for sync 401/403 and restores it after authenticated success', async () => {
    const originalWindow = (globalThis as any).window; const events: string[] = []
    ;(globalThis as any).window = { CustomEvent: class { constructor(public type: string) {} }, dispatchEvent: (event: any) => { events.push(event.type) } }
    const worker = new SyncWorker(); const responses = [
      { ok: false, status: 401 }, { ok: false, status: 403 },
      { ok: true, status: 200, data: { status: 'ok', tables: {}, server_time: '2026-07-20 16:00:00' } },
      { ok: false, status: 0 },
    ]
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], getConfig: () => '', setConfig: () => {},
      getRecordById: () => null, getRecordByUnique: () => null, runInTransaction: (fn: () => void) => fn(),
    }
    worker.bind({ get: vi.fn(async () => responses.shift()), post: vi.fn() } as any, db)
    try { for (let index = 0; index < 4; index += 1) await worker.pullAndMergeResult(true) } finally { (globalThis as any).window = originalWindow }
    expect(events.filter(event => event === 'mtl:auth-challenge')).toHaveLength(2)
    expect(events.filter(event => event === 'mtl:auth-expired')).toHaveLength(0)
    expect(events.filter(event => event === 'mtl:auth-restored')).toHaveLength(1)
  })

  it('retains the injected requester when configuration changes', async () => {
    const calls: Array<[string, any]> = []
    const requester: ApiRequester = async (url, init) => {
      calls.push([url, init])
      return { ok: true, status: 200, text: async () => JSON.stringify({ status: 'ok', tables: {}, server_time: '2026-07-21 11:05:00' }) }
    }
    const worker = new SyncWorker()
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], getConfig: () => '', setConfig: () => {},
      getRecordById: () => null, getRecordByUnique: () => null, runInTransaction: (fn: () => void) => fn(),
    }
    worker.bind(new ApiClient('http://old.test', 'old-token', 50, requester), db)
    worker.updateConfig('', '')
    worker.updateConfig('http://new.test', 'new-token')
    await worker.pullAndMergeResult(true, { syncRunId: 'hot-update' })
    expect(calls.some(([url, init]) => url.startsWith('http://new.test/api/sync/pull') && init.headers.Authorization === 'Bearer new-token')).toBe(true)
  })

  it.each([[401, 'auth_expired'], [403, 'auth_expired'], [0, 'server_unreachable']])(
    'preserves status %s transport error %s', async (status, error) => {
      const worker = new SyncWorker()
      const db: any = { setEnqueue: () => {}, getPendingOutbox: () => [], getConfig: () => '', setConfig: () => {} }
      worker.bind({ get: vi.fn(async () => ({ ok: false, status, error })), post: vi.fn() } as any, db)
      expect(await worker.pullAndMergeResult(true)).toMatchObject({ ok: false, error })
    },
  )

  it('disables EventSource only when the runtime policy says so', () => {
    const original = (globalThis as any).EventSource; let constructed = 0
    class FakeEventSource { onerror: any; constructor() { constructed++ } addEventListener() {} close() {} }
    ;(globalThis as any).EventSource = FakeEventSource
    try {
      new SyncWorker({ enableSSE: false }).connectSSE('http://lan.test', 'private-token')
      expect(constructed).toBe(0)
      new SyncWorker().connectSSE('https://web.test', 'private-token')
      expect(constructed).toBe(1)
    } finally { (globalThis as any).EventSource = original }
  })

  it('uses Android bulk capability without per-record database calls', async () => {
    const queries: string[] = []; const transactions: any[][] = []; let yields = 0; let version = 0
    const db: any = {
      setEnqueue: () => {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig: () => {},
      getRecordById: () => { throw new Error('legacy record lookup must not run') },
      androidBulk: {
        query: (sql: string) => {
          queries.push(sql)
          if (sql.startsWith('PRAGMA')) return (sql.includes('habit_checkins')
            ? ['id', 'habit_id', 'checkin_date', 'updated_at', 'pulled_at', 'pushed_at']
            : ['id', 'title', 'updated_at', 'pulled_at', 'pushed_at']).map(name => ({ name }))
          return []
        },
        transaction: (operations: any[]) => { transactions.push(operations) },
        yieldToUi: async () => { yields++ },
      },
    }
    const api: any = { post: async () => ({ ok: true, data: { status: 'ok' } }), get: async () => ({ ok: true, data: {
      status: 'ok', from_version: 0, to_version: 3, changes: [{ server_version: 1 }, { server_version: 2 }, { server_version: 3 }],
      server_time: '2026-07-21 12:00:00', tables: { tasks: [
        { id: 'a', title: 'one', updated_at: '2026-07-21 11:00:00' },
        { id: 'b', title: 'two', updated_at: '2026-07-21 11:01:00' },
      ], habit_checkins: [{ id: 'old-check', _sync_operation: 'delete', updated_at: '2026-07-21 11:02:00' }] },
    } }) }
    const worker = new SyncWorker(); worker.bind(api, db)
    const result = await worker.flushNow(false)
    expect(result).toMatchObject({ ok: true, merged: 3 }); expect(version).toBe(3)
    expect(transactions).toHaveLength(2); expect(transactions.flat()).toHaveLength(3); expect(yields).toBe(2)
    expect(queries.filter(sql => sql.startsWith('PRAGMA'))).toHaveLength(2)
    expect(queries.filter(sql => sql.startsWith('SELECT * FROM tasks'))).toHaveLength(1)
    expect(queries.filter(sql => sql.startsWith('SELECT * FROM habit_checkins'))).toHaveLength(1)
  })

  it('converges Android processing flash cards to the server failed state', async () => {
    const operations: any[] = []; let version = 1
    const columns = ['id', 'occurred_at', 'original_text', 'analysis_status', 'analysis_error_code', 'updated_at', 'pulled_at', 'pushed_at']
    const db: any = { setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig() {}, androidBulk: {
        query: (sql: string) => sql.startsWith('PRAGMA') ? columns.map(name => ({ name })) : sql.startsWith('SELECT * FROM flash_cards') ? [{ id: 'flash-1', analysis_status: 'processing' }] : [],
        transaction: (batch: any[]) => operations.push(...batch), yieldToUi: async () => {},
      } }
    const card = { id: 'flash-1', occurred_at: '2026-08-12 22:09:29', original_text: '原文', analysis_status: 'failed', analysis_error_code: 'flash_insight_analysis_failed', updated_at: '2026-08-12 22:09:35' }
    const worker = new SyncWorker({ enableSSE: false }); worker.bind({ post: vi.fn(), get: vi.fn(async () => ({ ok: true, data: { status: 'ok', from_version: 1, to_version: 2, changes: [{ server_version: 2 }], tables: { flash_cards: [card] }, server_time: card.updated_at } })) } as any, db)
    expect(await worker.requestSync('server-change-followup')).toMatchObject({ ok: true, merged: 1 })
    expect(operations[0].params).toEqual(expect.arrayContaining(['failed', 'flash_insight_analysis_failed']))
    expect(version).toBe(2)
  })

  it('keeps the legacy PC lookup, schema, write, and cursor sequence without bulk capability', async () => {
    const calls: string[] = []; let version = 9
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      setLastServerVersion: (next: number) => { calls.push(`cursor:${next}`); version = next },
      getConfig: () => '', setConfig: () => {}, hasPendingOutbox: () => false,
      getRecordById: () => { calls.push('lookup'); return null }, getRecordByUnique: () => null,
      allRaw: () => { calls.push('schema'); return ['id', 'title', 'updated_at', 'pulled_at', 'pushed_at'].map(name => ({ name })) },
      runRaw: () => { calls.push('write') }, runInTransaction: (fn: () => void) => fn(),
    }
    const api: any = { post: async () => ({ ok: true, data: { status: 'ok' } }), get: async () => ({ ok: true, data: {
      status: 'ok', from_version: 9, to_version: 10, changes: [{ server_version: 10 }], server_time: '2026-07-21 12:00:00',
      tables: { tasks: [{ id: 'pc-1', title: 'unchanged path', updated_at: '2026-07-21 11:59:00' }] },
    } }) }
    const worker = new SyncWorker(); worker.bind(api, db)
    expect(await worker.flushNow(false)).toMatchObject({ ok: true, merged: 1 })
    expect(calls).toEqual(['schema', 'lookup', 'write', 'cursor:10']); expect(version).toBe(10)
  })

  it('rejects a PC table missing pulled_at before INSERT and preserves success state', async () => {
    let version = 0; const writes = vi.fn(); const config = { server_to_client_synced_at: 'old', last_sync_at: 'old' }
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
      setLastServerVersion: (next: number) => { version = next }, getConfig: (key: keyof typeof config) => config[key] ?? '',
      setConfig: (key: keyof typeof config, value: string) => { config[key] = value }, allRaw: () => [{ name: 'id' }, { name: 'date' }],
      getRecordById: () => null, getRecordByUnique: () => null, runRaw: writes, runInTransaction: (fn: () => void) => fn(),
    }
    const response = { ok: true, data: { status: 'ok', snapshot: true, from_version: 0, to_version: 8, changes: [],
      server_time: '2026-07-21 18:00:00', tables: { atm_summary: [{ id: 1, date: '2026-07-20' }] } } }
    const worker = new SyncWorker(); worker.bind({ get: vi.fn(async () => response), post: vi.fn() } as any, db)

    const result = await worker.pullAndMergeResult(true)

    expect(result).toMatchObject({ ok: false, error: 'local_merge_failed' }); expect(writes).not.toHaveBeenCalled()
    expect(version).toBe(0); expect(config).toEqual({ server_to_client_synced_at: 'old', last_sync_at: 'old' })
    expect(result.diagnostics?.merge.failure_details).toEqual([expect.objectContaining({ category: 'schema_missing_required_column', columns: ['pulled_at'] })])
  })

  it('accepts a successful snapshot to_version when changes is empty', async () => {
    let version = 0; const get = vi.fn(async (_path: string, _params: any) => ({ ok: true, data: { status: 'ok', snapshot: true, from_version: version,
      to_version: 8, changes: [], server_time: '2026-07-21 18:01:00', tables: { atm_summary: [{ id: 1, date: '2026-07-20' }] } } }))
    const db: any = {
      setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version, setLastServerVersion: (next: number) => { version = next },
      getConfig: () => '', setConfig() {}, getRecordById: () => null, getRecordByUnique: () => null, runRaw() {},
      allRaw: () => ['id', 'date', 'updated_at', 'pushed_at', 'pulled_at'].map(name => ({ name })), runInTransaction: (fn: () => void) => fn(),
    }
    const worker = new SyncWorker(); worker.bind({ get, post: vi.fn() } as any, db)
    expect(await worker.pullAndMergeResult(true)).toMatchObject({ ok: true, merged: 1 })
    expect(version).toBe(8)
    await worker.pullAndMergeResult(true)
    expect(get.mock.calls[1][1]).toMatchObject({ since_version: '8' })
  })

  it('emits one-line redacted PC and Android merge diagnostics', async () => {
    const info = vi.spyOn(console, 'info').mockImplementation(() => {})
    const run = async (android: boolean, syncRunId: string) => {
      let version = 0
      const columns = ['id', 'title', 'pulled_at', 'pushed_at'].map(name => ({ name }))
      const db: any = {
        setEnqueue() {}, getPendingOutbox: () => [], getLastServerVersion: () => version,
        setLastServerVersion: (next: number) => { version = next }, getConfig: () => '', setConfig() {},
        getRecordById: () => null, getRecordByUnique: () => null, allRaw: () => columns,
        runRaw() {}, runInTransaction: (fn: () => void) => fn(),
      }
      if (android) db.androidBulk = { query: (sql: string) => sql.startsWith('PRAGMA') ? columns : [], transaction() {}, yieldToUi: async () => {} }
      const response = { ok: true, data: { status: 'ok', snapshot: true, from_version: 0, to_version: 1, changes: [],
        tables: { tasks: [{ id: 't1', title: 'private-token-payload' }] }, server_time: '2026-07-21 18:10:00' } }
      const worker = new SyncWorker(); worker.bind({ get: vi.fn(async () => response), post: vi.fn() } as any, db)
      await worker.pullAndMergeResult(true, { syncRunId })
    }
    let lines: string[] = []
    try {
      await run(false, 'pc-run'); await run(true, 'android-run')
      lines = info.mock.calls.map(call => call[0]).filter(value => typeof value === 'string' && value.startsWith('[SyncWorker] {')) as string[]
    } finally { info.mockRestore() }
    expect(lines).toHaveLength(2)
    const events = lines.map(line => JSON.parse(line.slice('[SyncWorker] '.length)))
    expect(events.map(event => event.platform)).toEqual(['pc', 'android'])
    expect(events.every(event => event.sync_run_id && event.stage === 'merge' && event.schema === 'validated'
      && event.cursor && typeof event.elapsed_ms === 'number')).toBe(true)
    expect(lines.join('\n')).not.toMatch(/\[object Object\]|private-token-payload|payload/)
  })
})
