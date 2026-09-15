import { describe, expect, it } from 'vitest'
import { contiguousSuccessVersion, pullCursorDecision, SyncFailureGate } from '../core/SyncFailureGate'

describe('SyncFailureGate', () => {
  it('advances only through changes before the first failed version', () => {
    const changes = [
      { server_version: 11, table_name: 'server_tasks', record_id: 'ok' },
      { server_version: 12, table_name: 'server_tasks', record_id: 'bad' },
      { server_version: 13, table_name: 'server_tasks', record_id: 'later' },
    ]
    expect(contiguousSuccessVersion(10, changes, [{ table: 'tasks', recordId: 'bad' }])).toBe(11)
    expect(contiguousSuccessVersion(10, changes, [{ table: 'tasks', recordId: 'snapshot-only' }])).toBe(10)
    expect(contiguousSuccessVersion(10, changes, [])).toBe(13)
  })

  it('backs off the same failure and clears on success or version change', () => {
    const gate = new SyncFailureGate()
    expect(gate.fail('tasks:bad', 12, 1_000)).toBe(61_000)
    expect(gate.canAttempt('tasks:bad', 12, 2_000)).toEqual({ allowed: false, retryAt: 61_000 })
    expect(gate.canAttempt('tasks:bad', 13, 2_000)).toEqual({ allowed: true })
    gate.fail('tasks:bad', 13, 2_000); gate.succeed()
    expect(gate.canAttempt('tasks:bad', 13, 2_001)).toEqual({ allowed: true })
  })

  it('keeps cursor on failure and accepts successful empty-change snapshots', () => {
    expect(pullCursorDecision(0, 737, { versioned: true, snapshot: true, succeeded: false }))
      .toEqual({ previous: 0, next: 0, advanced: false })
    expect(pullCursorDecision(0, 737, { versioned: true, snapshot: true, succeeded: true }))
      .toEqual({ previous: 0, next: 737, advanced: true })
    expect(pullCursorDecision(737, 738, { versioned: true, snapshot: false, succeeded: true }))
      .toEqual({ previous: 737, next: 738, advanced: true })
  })
})
