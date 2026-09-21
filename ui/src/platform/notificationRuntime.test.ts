import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { nextSleepReminderAt } from './notificationRuntime'

const before = new Date('2026-08-28T14:29:00.000Z')
const after = new Date('2026-08-28T14:31:00.000Z')
assert(nextSleepReminderAt(before) === Date.UTC(2026, 7, 28, 14, 30), 'must schedule Beijing 22:30 today')
assert(nextSleepReminderAt(after) === Date.UTC(2026, 7, 29, 14, 30), 'must schedule the next day after 22:30')
const source = readFileSync(new URL('./notificationRuntime.ts', import.meta.url), 'utf8')
assert(source.includes('schedule(sleepTimeNotification(nextSleepReminderAt()))'), 'runtime must register one stable daily sleep reminder')
assert(source.includes("n.sleep_date = strftime('%Y-%m-%d', 'now', '+8 hours')"), 'PC sleep notifications must only select the current Beijing sleep date')
assert(source.includes('n.notification_id=n.id AND r.device_id=?') || source.includes('r.notification_id=n.id AND r.device_id=?'), 'current-day filtering must retain the device receipt boundary')
console.log('notification runtime tests passed')
