import { describe, expect, it } from 'vitest'
import { buildHabitRepeatRule, formatHabitRepeatRule, isHabitScheduledForDate, parseHabitRepeatRule } from '../core/HabitSchedule'

describe('HabitSchedule', () => {
  it('normalizes daily and named weekly schedules', () => {
    expect(buildHabitRepeatRule([])).toBe('FREQ=DAILY')
    expect(formatHabitRepeatRule('RRULE:FREQ=DAILY')).toBe('每天')
    expect(formatHabitRepeatRule('FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR')).toBe('工作日')
    expect(formatHabitRepeatRule('FREQ=WEEKLY;BYDAY=SA,SU')).toBe('周末')
  })

  it('orders arbitrary weekdays and filters dates safely', () => {
    expect(buildHabitRepeatRule(['WE', 'MO'])).toBe('FREQ=WEEKLY;BYDAY=MO,WE')
    expect(parseHabitRepeatRule('FREQ=WEEKLY;BYDAY=WE,MO')).toEqual(['MO', 'WE'])
    expect(isHabitScheduledForDate('FREQ=WEEKLY;BYDAY=MO,WE', '2026-09-23')).toBe(true)
    expect(isHabitScheduledForDate('FREQ=WEEKLY;BYDAY=MO,WE', '2026-09-24')).toBe(false)
    expect(isHabitScheduledForDate('not-an-rrule', '2026-09-24')).toBe(true)
  })
})
