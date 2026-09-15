import { LocalNotifications } from '@capacitor/local-notifications'
import type { RemindersService } from './services'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'

export interface ReminderBackend {
  schedule(id: string, atMs: number): Promise<void>
  cancel(id: string): Promise<void>
}

type NativeNotifications = {
  checkPermissions(): Promise<{ display: string }>
  requestPermissions(): Promise<{ display: string }>
  schedule(options: { notifications: Array<{ id: number, title: string, body: string, schedule: { at: Date } }> }): Promise<unknown>
  cancel(options: { notifications: Array<{ id: number }> }): Promise<void>
}

const nativeId = (id: string) => [...id].reduce((hash, char) => ((hash * 31 + char.charCodeAt(0)) & 0x7fffffff), 0) || 1

export function createCapacitorRemindersService(runtime: PlatformRuntime = detectPlatformRuntime(), plugin: NativeNotifications = LocalNotifications): RemindersService {
  if (runtime !== 'capacitor-android') return createRemindersService(null)
  const allowDisplay = async () => {
    let state = (await plugin.checkPermissions()).display
    if (state === 'prompt' || state === 'prompt-with-rationale') state = (await plugin.requestPermissions()).display
    return state === 'granted'
  }
  return createRemindersService({
    async schedule(id, atMs) {
      if (!await allowDisplay()) throw new Error('notification_permission_denied')
      await plugin.schedule({ notifications: [{ id: nativeId(id), title: 'MyTimeLogger', body: '计时已结束', schedule: { at: new Date(atMs) } }] })
    },
    async cancel(id) { await plugin.cancel({ notifications: [{ id: nativeId(id) }] }) },
  })
}

export function createRemindersService(backend: ReminderBackend | null): RemindersService {
  const scheduled = new Map<string, number>()
  const cancelled = new Set<string>()
  return {
    available: Boolean(backend),
    async schedule(id, atMs) {
      if (!backend || scheduled.get(id) === atMs) return
      if (scheduled.has(id)) await backend.cancel(id)
      await backend.schedule(id, atMs); scheduled.set(id, atMs)
      cancelled.delete(id)
    },
    async cancel(id) {
      if (!backend || (cancelled.has(id) && !scheduled.has(id))) return
      await backend.cancel(id); scheduled.delete(id); cancelled.add(id)
    },
  }
}
