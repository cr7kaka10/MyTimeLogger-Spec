import type { LogicSnapshot } from '@core/LogicSnapshot'
import { createRemindersService } from './reminders'
import { reconcileTimerReminder, TIMER_REMINDER_ID } from './timerReminders'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const calls: string[] = []
const service = createRemindersService({
  schedule: async (id, at) => { calls.push(`schedule:${id}:${at}`) },
  cancel: async id => { calls.push(`cancel:${id}`) },
})
const snapshot = (overrides: Partial<LogicSnapshot> = {}): LogicSnapshot => ({
  version: 1, capturedAtEpochMs: 1000, state: 'studying', isPaused: false,
  category: { id: 1, name: '输入', task: '' }, pause: { count: 0, reasons: [], startedAtEpochMs: null },
  segments: [], session: { startedAtEpochMs: 1000, largeStartedAtEpochMs: 1000, durationSeconds: 60, totalStudySeconds: 0, currentCycleStudySeconds: 0, netDurationSeconds: 0 },
  timing: { mode: 'countdown', elapsedMs: 0, deadlineEpochMs: 61_001 }, ...overrides,
})
await reconcileTimerReminder(snapshot(), service, 1000)
await reconcileTimerReminder(snapshot(), service, 1000)
await reconcileTimerReminder(snapshot({ isPaused: true }), service, 1000)
await reconcileTimerReminder(snapshot({ timing: { mode: 'countup', elapsedMs: 0, deadlineEpochMs: null } }), service, 1000)
await reconcileTimerReminder(snapshot({ timing: { mode: 'countdown', elapsedMs: 60_000, deadlineEpochMs: 999 } }), service, 1000)
assert(calls[0] === `schedule:${TIMER_REMINDER_ID}:62000`, 'future countdown should schedule a rounded stable deadline')
assert(calls.filter(call => call.startsWith('schedule:')).length === 1, 'same deadline should be deduplicated')
assert(calls.filter(call => call.startsWith('cancel:')).length === 1, 'pause/countup/expired reconciliation should be idempotent')
assert(await reconcileTimerReminder(snapshot(), null, 1000) === 'unavailable', 'Electron/no backend should be a no-op')
console.log('timer reminder coordinator tests passed')
