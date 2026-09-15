import { createNotificationService, sleepTimeNotification, type NativeNotificationPlugin } from './notifications'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const calls: any[] = []; let permission = 'prompt'
const plugin: NativeNotificationPlugin = {
  checkPermissions: async () => ({ display: permission }),
  requestPermissions: async () => ({ display: permission = 'granted' }),
  createChannel: async options => { calls.push(['channel', options.id]) },
  schedule: async options => { calls.push(['schedule', options.notifications[0]]) },
  cancel: async options => { calls.push(['cancel', options.notifications[0].id]) },
  addListener: async (_event, listener) => { (plugin as any).listener = listener; return { remove: async () => {} } },
}
const service = createNotificationService('capacitor-android', plugin)
await service.initialize()
assert(calls.filter(call => call[0] === 'channel').map(call => call[1]).join(',') === 'timer,sleep,achievements,rewards,account', 'sleep channel required')
await service.notify({ eventKey: 'ext:g1', channel: 'achievements', title: '目标达成', body: '阅读 +5', route: 'goals' })
await service.schedule({ eventKey: 'timer:deadline', channel: 'timer', title: 'MyTimeLogger', body: '计时已结束', route: 'timer', atMs: 1234 })
const sent = calls.filter(call => call[0] === 'schedule').map(call => call[1])
assert(sent[0].extra.eventKey === 'ext:g1' && sent[0].extra.route === 'goals' && !sent[0].schedule, 'instant notification must carry safe eventKey and route')
assert(sent[1].schedule.at.getTime() === 1234 && sent[1].channelId === 'timer', 'timer notification must remain scheduled')
const sleep = sleepTimeNotification(22_30)
assert(sleep.eventKey === 'sleep-time:daily-2230' && sleep.route === 'sleep' && sleep.channel === 'sleep', 'sleep reminder must have a stable daily key')
permission = 'denied'
assert(await service.notify({ eventKey: 'ledger:1', channel: 'rewards', title: '金币', body: '+1', route: 'rewards' }) === 'denied', 'permission denial must not throw')
assert(await service.notify({ eventKey: 'bad', channel: 'rewards', title: 'x', body: 'x', route: 'https://bad' as any }) === 'rejected', 'unsafe route must be rejected')
console.log('notification platform tests passed')
