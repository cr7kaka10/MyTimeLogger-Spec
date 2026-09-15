import { describe, expect, it } from 'vitest'
import type { LogicSnapshot } from '../core/LogicSnapshot'
import { reduceTimerWidgetCommand } from '../core/TimerWidgetReducer'

const stopped = (): LogicSnapshot => ({
  version: 1, capturedAtEpochMs: 100, state: 'stopped', isPaused: false,
  category: { id: null, name: '', task: '' }, pause: { count: 0, reasons: [], startedAtEpochMs: null }, segments: [],
  session: { startedAtEpochMs: null, largeStartedAtEpochMs: null, durationSeconds: 0, totalStudySeconds: 0, currentCycleStudySeconds: 0, netDurationSeconds: 0 },
  timing: { mode: 'countdown', elapsedMs: 0, deadlineEpochMs: null },
})
const start = { action: 'start', commandId: 'cmd-1', categoryId: 7, eventEpochMs: 1_000 } as const

describe('TimerWidgetReducer start', () => {
  it('starts an ordinary category from stopped at the command boundary', () => {
    const result = reduceTimerWidgetCommand(stopped(), start, { id: 7, name: '副业研发' })
    expect(result.status).toBe('applied')
    expect(result.snapshot).toMatchObject({ state: 'countup_studying', category: { id: 7, name: '副业研发' }, session: { startedAtEpochMs: 1_000 }, timing: { mode: 'countup', elapsedMs: 0 } })
  })

  it.each(['输入', '输出'])('rejects %s without changing the snapshot', name => {
    const before = stopped()
    const result = reduceTimerWidgetCommand(before, start, { id: 7, name })
    expect(result).toEqual({ status: 'requires_app', snapshot: before, sessions: [] })
  })
})

describe('TimerWidgetReducer active count-up', () => {
  const running = () => reduceTimerWidgetCommand(stopped(), start, { id: 7, name: '副业研发' }).snapshot
  const command = (action: 'switch' | 'stop', categoryId: number, eventEpochMs: number, commandId = 'cmd-2') =>
    ({ action, categoryId, eventEpochMs, commandId } as const)

  it('keeps the active category unchanged on a same-category command or replay', () => {
    const before = running()
    expect(reduceTimerWidgetCommand(before, command('switch', 7, 4_500), { id: 7, name: '副业研发' })).toEqual({ status: 'noop', snapshot: before, sessions: [] })
    expect(reduceTimerWidgetCommand(before, command('stop', 7, 4_500), { id: 7, name: '副业研发' }, new Set(['cmd-2']))).toEqual({ status: 'noop', snapshot: before, sessions: [] })
  })

  it('switches once at one integer-second boundary', () => {
    const result = reduceTimerWidgetCommand(running(), command('switch', 8, 4_500), { id: 8, name: '吃饭' })
    expect(result.sessions).toEqual([{ categoryId: 7, startEpochMs: 1_000, endEpochMs: 4_500, durationSeconds: 3 }])
    expect(result.snapshot).toMatchObject({ state: 'countup_studying', category: { id: 8 }, session: { startedAtEpochMs: 4_500 } })
  })

  it('stops a running or paused count-up using net elapsed seconds', () => {
    const active = running()
    const stoppedResult = reduceTimerWidgetCommand(active, command('stop', 7, 4_750), { id: 7, name: '副业研发' })
    expect(stoppedResult.sessions[0].durationSeconds).toBe(3)
    const paused = { ...active, capturedAtEpochMs: 5_000, isPaused: true, timing: { ...active.timing, elapsedMs: 2_300 } }
    expect(reduceTimerWidgetCommand(paused, command('stop', 7, 9_000), { id: 7, name: '副业研发' }).sessions[0].durationSeconds).toBe(2)
  })

  it('rejects structured active state without changes', () => {
    const before = { ...running(), state: 'studying' as const }
    expect(reduceTimerWidgetCommand(before, command('switch', 8, 4_500), { id: 8, name: '吃饭' })).toEqual({ status: 'requires_app', snapshot: before, sessions: [] })
  })
})
