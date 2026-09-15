import type { LogicSnapshot } from './LogicSnapshot'
import type { TimerWidgetCommand } from './TimerWidgetCommand'

export interface WidgetTimerCategory { id: number; name: string }
export interface WidgetCompletedSession {
  categoryId: number
  startEpochMs: number
  endEpochMs: number
  durationSeconds: number
}
export interface WidgetTimerReduction {
  status: 'applied' | 'noop' | 'requires_app'
  snapshot: LogicSnapshot
  sessions: WidgetCompletedSession[]
}

const blocked = (snapshot: LogicSnapshot): WidgetTimerReduction =>
  ({ status: 'requires_app', snapshot, sessions: [] })
const noop = (snapshot: LogicSnapshot): WidgetTimerReduction =>
  ({ status: 'noop', snapshot, sessions: [] })

const startSnapshot = (snapshot: LogicSnapshot, target: WidgetTimerCategory, at: number): LogicSnapshot => ({
  ...snapshot, capturedAtEpochMs: at, state: 'countup_studying', isPaused: false,
  category: { id: target.id, name: target.name, task: '' },
  pause: { count: 0, reasons: [], startedAtEpochMs: null }, segments: [],
  session: { ...snapshot.session, startedAtEpochMs: at, largeStartedAtEpochMs: at, durationSeconds: 0, currentCycleStudySeconds: 0, netDurationSeconds: 0 },
  timing: { mode: 'countup', elapsedMs: 0, deadlineEpochMs: null },
})

const stopSnapshot = (snapshot: LogicSnapshot, at: number): LogicSnapshot => ({
  ...snapshot, capturedAtEpochMs: at, state: 'stopped', isPaused: false,
  category: { id: null, name: '', task: '' },
  pause: { count: 0, reasons: [], startedAtEpochMs: null }, segments: [],
  session: { ...snapshot.session, startedAtEpochMs: null, largeStartedAtEpochMs: null, durationSeconds: 0, currentCycleStudySeconds: 0, netDurationSeconds: 0 },
  timing: { mode: 'countdown', elapsedMs: 0, deadlineEpochMs: null },
})

export function reduceTimerWidgetCommand(
  snapshot: LogicSnapshot,
  command: TimerWidgetCommand,
  target: WidgetTimerCategory | null,
  appliedCommandIds: ReadonlySet<string> = new Set(),
): WidgetTimerReduction {
  if (appliedCommandIds.has(command.commandId)) return noop(snapshot)
  if (!target || target.id !== command.categoryId || ['输入', '输出'].includes(target.name)) return blocked(snapshot)
  if (snapshot.state === 'stopped') {
    if (command.action !== 'start') return blocked(snapshot)
    return { status: 'applied', sessions: [], snapshot: startSnapshot(snapshot, target, command.eventEpochMs) }
  }
  if (snapshot.state !== 'countup_studying' || ['输入', '输出'].includes(snapshot.category.name)) return blocked(snapshot)
  if (command.action !== 'stop' && snapshot.category.id === target.id) return noop(snapshot)
  if (command.action !== 'stop' && command.action !== 'switch') return blocked(snapshot)
  const at = command.eventEpochMs
  const startedAt = snapshot.session.largeStartedAtEpochMs ?? snapshot.session.startedAtEpochMs
  if (startedAt === null || snapshot.category.id === null) return blocked(snapshot)
  const elapsedMs = snapshot.timing.elapsedMs + (snapshot.isPaused ? 0 : Math.max(0, at - snapshot.capturedAtEpochMs))
  const sessions = [{ categoryId: snapshot.category.id, startEpochMs: startedAt, endEpochMs: at, durationSeconds: Math.floor(elapsedMs / 1000) }]
  const stopped = stopSnapshot(snapshot, at)
  return {
    status: 'applied', sessions,
    snapshot: command.action === 'switch' ? startSnapshot(stopped, target, at) : stopped,
  }
}
