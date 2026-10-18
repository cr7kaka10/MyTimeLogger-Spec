export const HABIT_WEEKDAYS = [
  ['MO', '一'], ['TU', '二'], ['WE', '三'], ['TH', '四'], ['FR', '五'], ['SA', '六'], ['SU', '日'],
] as const

export type HabitWeekday = typeof HABIT_WEEKDAYS[number][0]
const ORDER = HABIT_WEEKDAYS.map(([code]) => code)

export const parseHabitRepeatRule = (value?: string | null): HabitWeekday[] | null => {
  const rule = String(value || '').replace(/^RRULE:/i, '').toUpperCase()
  if (!rule || rule.includes('FREQ=DAILY')) return null
  const match = /(?:^|;)BYDAY=([^;]+)/.exec(rule)
  if (!rule.includes('FREQ=WEEKLY') || !match) return null
  const selected = new Set(match[1].split(',').filter(code => ORDER.includes(code as HabitWeekday)))
  return ORDER.filter(code => selected.has(code)) as HabitWeekday[]
}

export const buildHabitRepeatRule = (days: readonly HabitWeekday[]): string => {
  const selected = ORDER.filter(code => days.includes(code as HabitWeekday))
  return selected.length === 0 || selected.length === ORDER.length
    ? 'FREQ=DAILY'
    : `FREQ=WEEKLY;BYDAY=${selected.join(',')}`
}

export const formatHabitRepeatRule = (value?: string | null): string => {
  const days = parseHabitRepeatRule(value)
  if (!days) return '每天'
  if (days.join(',') === 'MO,TU,WE,TH,FR') return '工作日'
  if (days.join(',') === 'SA,SU') return '周末'
  return `每周${days.map(code => HABIT_WEEKDAYS.find(([item]) => item === code)?.[1]).join('、')}`
}

export const isHabitScheduledForDate = (value: string | null | undefined, date: string): boolean => {
  const days = parseHabitRepeatRule(value)
  if (!days) return true
  const [year, month, day] = date.split('-').map(Number)
  if (![year, month, day].every(Number.isFinite)) return true
  const code = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'][new Date(year, month - 1, day).getDay()] as HabitWeekday
  return days.includes(code)
}
