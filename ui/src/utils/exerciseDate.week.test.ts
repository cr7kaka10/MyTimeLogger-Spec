import { planDayForDate, weekOfYear } from './exerciseDate'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
assert(weekOfYear('2026-01-01') === 1, 'the week containing January 1 must be week 1')
assert(weekOfYear('2026-08-22') === 34, '2026-08-22 Beijing date must be week 34')
assert(weekOfYear('2026-12-31') === 53, 'calendar year week calculation must remain stable at year end')
for (const [date, day] of [['2026-09-07','周一'],['2026-09-08','周二'],['2026-09-09','周三'],['2026-09-10','周四'],['2026-09-11','周五'],['2026-09-12','六'],['2026-09-13','日']] as const) {
  assert(planDayForDate(date) === day, `${date} must map to ${day} in Beijing time`)
}
console.log('exercise calendar week tests passed')
