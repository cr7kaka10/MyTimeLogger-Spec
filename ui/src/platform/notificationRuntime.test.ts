import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { nextSleepReminderAt } from './notificationRuntime'

const before = new Date('2026-08-28T14:29:00.000Z')
const after = new Date('2026-08-28T14:31:00.000Z')
assert(nextSleepReminderAt(before) === Date.UTC(2026, 7, 28, 14, 30), 'must schedule Beijing 22:30 today')
assert(nextSleepReminderAt(after) === Date.UTC(2026, 7, 29, 14, 30), 'must schedule the next day after 22:30')
const source = readFileSync(new URL('./notificationRuntime.ts', import.meta.url), 'utf8')
assert(source.includes('schedule(sleepTimeNotification(nextSleepReminderAt()))'), 'runtime must register one stable daily sleep reminder')
assert(source.includes('queuePoop(lastTimerSnapshot)'), 'foreground return must reconcile active timer reminder')
const timerSource = readFileSync(new URL('../hooks/useTimer.ts', import.meta.url), 'utf8')
assert(timerSource.includes("new CustomEvent('mtl:timer-snapshot', { detail: snapshot })"), 'restored timer must publish its active snapshot to notification runtime')
assert(source.includes('poopStateKey') && source.includes('runtimeState.set(poopStateKey'), 'scheduled session identity must survive renderer restart')
assert(source.includes("permissionStatus().catch(() => 'unavailable')") && source.includes("reason: 'permission_changed'"), 'permission changes must invalidate a stale scheduled-session marker')
assert(source.includes("n.sleep_date = strftime('%Y-%m-%d', 'now', '+8 hours')"), 'PC sleep notifications must only select the current Beijing sleep date')
assert(source.includes('n.notification_id=n.id AND r.device_id=?') || source.includes('r.notification_id=n.id AND r.device_id=?'), 'current-day filtering must retain the device receipt boundary')
console.log('notification runtime tests passed')
