import type { LogicSnapshot } from '@core/LogicSnapshot'
import type { NotificationMessage } from './services'

const beijingDate = (at: Date) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(at)

export const nextBeijingDailyAt = (hour: number, minute: number, now = new Date()): number => {
  const date = beijingDate(now)
  const candidate = Date.parse(`${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00+08:00`)
  return candidate > now.getTime() ? candidate : candidate + 86_400_000
}

export const morningNotifications = (now = new Date()): Array<NotificationMessage & { atMs: number }> => {
  const sleepAt = nextBeijingDailyAt(8, 30, now); const bodyAt = nextBeijingDailyAt(8, 40, now)
  return [
    { eventKey: `morning:sleep-upload:${beijingDate(new Date(sleepAt))}`, channel: 'sleep', title: '上传睡眠截图', body: '请上传昨晚的睡眠截图', route: 'sleep', atMs: sleepAt },
    { eventKey: `morning:body-metrics:${beijingDate(new Date(bodyAt))}`, channel: 'achievements', title: '测量体重体脂', body: '请测量并记录体重和体脂', route: 'exercise', atMs: bodyAt },
  ]
}

export const poopReminder = (snapshot: LogicSnapshot, now = Date.now()): (NotificationMessage & { atMs: number }) | null => {
  if (snapshot.category.name !== '拉屎' || snapshot.state !== 'countup_studying' || snapshot.isPaused) return null
  const session = String(snapshot.session.startedAtEpochMs || snapshot.session.largeStartedAtEpochMs || snapshot.focusCycleId || '')
  if (!session) return null
  const elapsed = snapshot.timing.elapsedMs + (Number.isFinite(snapshot.capturedAtEpochMs)
    ? Math.max(0, now - snapshot.capturedAtEpochMs) : 0)
  return { eventKey: `timer:poop-8m:${session}`, channel: 'timer', title: '拉屎时间提醒', body: '不要拉屎玩手机', route: 'timer', atMs: now + Math.max(100, 480_000 - elapsed) }
}
