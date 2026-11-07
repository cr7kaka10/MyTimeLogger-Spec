import { isHabitScheduledForDate } from '@core/HabitSchedule'

export const shanghaiDay = (time = Date.now()) => new Date(time + 8 * 3600_000).toISOString().slice(0, 10)
const addDay = (date: string, offset: number) => new Date(Date.parse(`${date}T00:00:00Z`) + offset * 86400_000).toISOString().slice(0, 10)

export function projectHabits(habits: Array<{ id: string | number; repeat_rule?: string | null }>, start: string, count = 90) {
  const days: Record<string, string[]> = {}
  for (let offset = 0; offset < count; offset++) {
    const day = addDay(start, offset)
    days[day] = habits.filter(habit => isHabitScheduledForDate(habit.repeat_rule, day)).map(habit => String(habit.id))
  }
  return days
}
