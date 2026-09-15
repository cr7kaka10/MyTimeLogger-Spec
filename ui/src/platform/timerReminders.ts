import type { LogicSnapshot } from '@core/LogicSnapshot'
import type { RemindersService } from './services'

export const TIMER_REMINDER_ID = 'timer.logic.deadline.v1'
let timerReminders: RemindersService | null = null

export const setTimerRemindersService = (service: RemindersService | null) => { timerReminders = service }

export async function reconcileTimerReminder(
  snapshot: LogicSnapshot | null,
  service: RemindersService | null = timerReminders,
  now = Date.now(),
): Promise<'scheduled' | 'cancelled' | 'unavailable'> {
  if (!service?.available) return 'unavailable'
  const deadline = snapshot?.timing.deadlineEpochMs ?? null
  const shouldSchedule = Boolean(
    snapshot && snapshot.state !== 'stopped' && snapshot.state !== 'long_break_finished'
    && !snapshot.isPaused && snapshot.timing.mode === 'countdown'
    && deadline && deadline > now,
  )
  try {
    if (shouldSchedule) {
      await service.schedule(TIMER_REMINDER_ID, Math.ceil(deadline! / 1000) * 1000)
      return 'scheduled'
    }
    await service.cancel(TIMER_REMINDER_ID)
    return 'cancelled'
  } catch {
    console.warn('[timer-reminder] native reminder unavailable')
    return 'unavailable'
  }
}
