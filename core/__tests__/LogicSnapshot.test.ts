import { describe, expect, it } from 'vitest'
import { LOGIC_SNAPSHOT_VERSION, validateLogicSnapshot } from '../core/LogicSnapshot'

const valid = () => ({ version: LOGIC_SNAPSHOT_VERSION, capturedAtEpochMs: Date.now(), state: 'studying', isPaused: false, category: { id: 1, name: '输入', task: '编程' }, pause: { count: 0, reasons: [], startedAtEpochMs: null }, segments: [], session: { startedAtEpochMs: Date.now(), largeStartedAtEpochMs: Date.now(), durationSeconds: 60, totalStudySeconds: 0, currentCycleStudySeconds: 0, netDurationSeconds: 0 }, timing: { mode: 'countdown', elapsedMs: 12, deadlineEpochMs: Date.now() + 1000 } } as const)

describe('LogicSnapshot', () => {
  it('accepts the current versioned snapshot', () => expect(validateLogicSnapshot(valid())).toMatchObject({ ok: true }))
  it('safely rejects unknown versions', () => expect(validateLogicSnapshot({ ...valid(), version: 2 })).toEqual({ ok: false, reason: 'unknown-version' }))
  it('safely rejects missing fields', () => expect(validateLogicSnapshot({ version: LOGIC_SNAPSHOT_VERSION })).toEqual({ ok: false, reason: 'missing-field' }))
  it('safely rejects invalid deadlines', () => expect(validateLogicSnapshot({ ...valid(), timing: { ...valid().timing, deadlineEpochMs: -1 } })).toEqual({ ok: false, reason: 'invalid-deadline' }))
})
