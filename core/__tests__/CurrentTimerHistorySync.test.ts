import { describe, expect, it } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

describe('current timer completed history', () => {
  it('upserts repeated pulls by the stable server session id', () => {
    const rows = new Map<string, Record<string, unknown>>()
    rows.set('timer-session-1', { id: 'timer-session-1', session_summary: '临时记录' })
    const columns = [
      'id', 'start_time', 'end_time', 'net_duration_minutes', 'net_duration_seconds',
      'date', 'day_of_week', 'pause_count', 'pause_reasons', 'session_summary',
      'category_id', 'updated_at', 'pushed_at', 'pulled_at',
    ]
    const db: any = {
      allRaw: () => columns.map(name => ({ name })),
      runRaw: (sql: string, params: unknown[]) => {
        expect(sql).toContain('INSERT OR REPLACE INTO study_sessions')
        const keys = sql.slice(sql.indexOf('(') + 1, sql.indexOf(')')).split(', ')
        const row = Object.fromEntries(keys.map((key, index) => [key, params[index]]))
        rows.set(String(row.id), row)
      },
      setConfig: () => {},
    }
    const worker = new SyncWorker()
    ;(worker as any)._db = db
    const stable = {
      id: 'timer-session-1', start_time: '2026-07-24 20:00:00',
      end_time: '2026-07-24 20:10:00', net_duration_minutes: 10,
      net_duration_seconds: 600, date: '2026-07-24', day_of_week: '星期五',
      pause_count: 0, pause_reasons: '[]', session_summary: '服务端完成记录',
      category_id: 7, updated_at: '2026-07-24 20:10:00',
    }
    expect((worker as any)._upsertLocal('study_sessions', stable, '2026-07-24 20:11:00')).toBe(true)
    expect((worker as any)._upsertLocal('study_sessions', stable, '2026-07-24 20:12:00')).toBe(true)
    expect(rows).toHaveLength(1)
    expect(rows.get('timer-session-1')).toMatchObject({
      id: 'timer-session-1', session_summary: '服务端完成记录',
      pulled_at: '2026-07-24 20:12:00',
    })
  })

  it('applies repeated versioned deletes without creating an outbox record', () => {
    const rows = new Map<string, Record<string, unknown>>([
      ['timer-session-delete', { id: 'timer-session-delete' }],
    ])
    const writes: string[] = []
    const db: any = {
      runRaw: (sql: string, params: unknown[]) => {
        writes.push(sql)
        if (sql.startsWith('DELETE FROM study_sessions')) rows.delete(String(params[0]))
      },
      setConfig: () => {},
    }
    const worker = new SyncWorker()
    ;(worker as any)._db = db
    const deleted = { id: 'timer-session-delete', _sync_operation: 'delete' }

    expect((worker as any)._upsertLocal('study_sessions', deleted, '2026-07-27 10:10:00')).toBe(true)
    expect((worker as any)._upsertLocal('study_sessions', deleted, '2026-07-27 10:11:00')).toBe(true)
    expect(rows).toHaveLength(0)
    expect(writes).toEqual([
      'DELETE FROM study_sessions WHERE id = ?',
      'DELETE FROM study_sessions WHERE id = ?',
    ])
  })
})
