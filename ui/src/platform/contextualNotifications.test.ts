import { morningNotifications, nextBeijingDailyAt, poopReminder } from './contextualNotifications'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const before = new Date('2026-09-24T00:20:00Z')
const after = new Date('2026-09-24T00:45:00Z')
assert(nextBeijingDailyAt(8, 30, before) === Date.parse('2026-09-24T08:30:00+08:00'), '08:30 before should use current Beijing day')
assert(nextBeijingDailyAt(8, 30, after) === Date.parse('2026-09-25T08:30:00+08:00'), '08:30 after should roll to next Beijing day')
const morning = morningNotifications(before)
assert(morning[0].eventKey.endsWith('2026-09-24') && morning[0].route === 'sleep', 'sleep upload reminder must carry Beijing date and route')
assert(morning[1].atMs === Date.parse('2026-09-24T08:40:00+08:00') && morning[1].route === 'exercise', 'body reminder must open exercise')
const base: any = { state: 'countup_studying', isPaused: false, category: { name: '拉屎' }, focusCycleId: 'session-1', session: {}, timing: { elapsedMs: 120000 } }
assert(poopReminder(base, 1000)?.atMs === 361000, 'poop reminder should preserve remaining effective time')
assert(poopReminder({ ...base, capturedAtEpochMs: 1000 }, 181000)?.atMs === 361000, 'restored reminder must use elapsed wall time since capture')
assert(poopReminder({ ...base, focusCycleId: 'session-2' }, 1000)?.eventKey !== poopReminder(base, 1000)?.eventKey, 'a new session gets a distinct reminder identity')
const first = { ...base, session: { startedAtEpochMs: 1000 }, focusCycleId: 'stale-focus' }
const second = { ...first, session: { startedAtEpochMs: 2000 } }
assert(poopReminder(first, 1000)?.eventKey !== poopReminder(second, 2000)?.eventKey, 'new countup sessions must not reuse a stale focus-cycle reminder key')
assert(poopReminder({ ...base, isPaused: true }, 1000) === null, 'paused poop timer must cancel reminder')
assert(poopReminder({ ...base, state: 'stopped' }, 1000) === null, 'stopped timer must cancel reminder')
assert(poopReminder({ ...base, category: { name: '工作' } }, 1000) === null, 'switching away must cancel reminder')
console.log('contextual notification tests passed')
