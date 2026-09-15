import { createCapacitorRemindersService, createRemindersService } from './reminders'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const calls: string[] = []
const reminders = createRemindersService({
  schedule: async (id, at) => { calls.push(`schedule:${id}:${at}`) },
  cancel: async id => { calls.push(`cancel:${id}`) },
})
await reminders.schedule('timer', 1000)
await reminders.schedule('timer', 1000)
await reminders.schedule('timer', 2000)
await reminders.cancel('timer')
await reminders.cancel('timer')
assert(calls.join(',') === 'schedule:timer:1000,cancel:timer,schedule:timer:2000,cancel:timer', 'updates should replace one pending reminder and repeated cancel should be idempotent')
assert(!createRemindersService(null).available, 'missing native reminder backend should be unavailable')

let permission = 'prompt'; const nativeCalls: string[] = []
const plugin = {
  checkPermissions: async () => ({ display: permission }),
  requestPermissions: async () => { nativeCalls.push('permission'); permission = 'granted'; return { display: permission } },
  schedule: async ({ notifications }: any) => { nativeCalls.push(`schedule:${notifications[0].schedule.at.getTime()}`) },
  cancel: async () => { nativeCalls.push('cancel') },
}
const capacitor = createCapacitorRemindersService('capacitor-android', plugin)
await capacitor.schedule('timer', 1000); await capacitor.schedule('timer', 2000); await capacitor.cancel('timer')
assert(nativeCalls.join(',') === 'permission,schedule:1000,cancel,schedule:2000,cancel', 'Capacitor reminder should request display permission, replace, and cancel')
permission = 'denied'; let denied = ''
try { await createCapacitorRemindersService('capacitor-android', plugin).schedule('denied', 3000) } catch (error) { denied = (error as Error).message }
assert(denied === 'notification_permission_denied' && !nativeCalls.includes('schedule:3000'), 'denied permission must block scheduling')
assert(!createCapacitorRemindersService('electron', plugin).available, 'Electron must not use Local Notifications')
console.log('platform reminders tests passed')
