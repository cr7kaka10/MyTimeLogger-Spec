import type { RemindersService } from './services'

export const MEAL_REMINDER_SLOTS = [
  { meal: 'breakfast', time: '08:25', body: '按时吃早饭打卡' },
  { meal: 'lunch', time: '11:55', body: '该吃午饭了' },
  { meal: 'lunch', time: '13:25', body: '按时吃午饭打卡' },
  { meal: 'dinner', time: '17:55', body: '该吃晚饭了' },
  { meal: 'dinner', time: '18:55', body: '按时吃晚饭打卡' },
] as const

export const mealReminderId = (date: string, meal: string, time: string) => `meal:${date}:${meal}:${time}`
export const mealReminderBody = (id: string) => MEAL_REMINDER_SLOTS.find(slot => id.endsWith(`:${slot.meal}:${slot.time}`))?.body

export async function reconcileMealReminders(service: RemindersService, date: string, completed: Record<string, boolean>, enabled: boolean, nowMs = Date.now()): Promise<void> {
  if (!service.available) return
  await Promise.all(MEAL_REMINDER_SLOTS.map(async slot => {
    const id = mealReminderId(date, slot.meal, slot.time), atMs = Date.parse(`${date}T${slot.time}:00+08:00`)
    try {
      if (enabled && !completed[slot.meal] && atMs > nowMs) await service.schedule(id, atMs)
      else await service.cancel(id)
    } catch { /* 通知权限或系统排程不可用时不阻断打卡 */ }
  }))
}
