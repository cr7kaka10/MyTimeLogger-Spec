import { LocalNotifications } from '@capacitor/local-notifications'
import type { NotificationMessage, NotificationRoute, NotificationService } from './services'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'
import { getElectronApi } from './electron'

export type NativeNotificationPlugin = {
  checkPermissions(): Promise<{ display: string }>; requestPermissions(): Promise<{ display: string }>
  createChannel(options: any): Promise<unknown>; schedule(options: any): Promise<unknown>; cancel(options: any): Promise<void>
  addListener(event: 'localNotificationActionPerformed', listener: (action: any) => void): Promise<{ remove(): Promise<void> | void }> | { remove(): Promise<void> | void }
}
const routes = new Set<NotificationRoute>(['timer', 'sleep', 'goals', 'rewards', 'backpack', 'settings'])
const channels = [
  ['timer', '计时', 5], ['sleep', '睡眠提醒', 5], ['achievements', '目标成就', 4], ['rewards', '金币与奖励', 4], ['account', '账户状态', 4],
] as const
const nativeId = (key: string) => [...key].reduce((hash, char) => ((hash * 31 + char.charCodeAt(0)) & 0x7fffffff), 0) || 1
export const sleepTimeNotification = (atMs: number): NotificationMessage & { atMs: number } => ({
  eventKey: 'sleep-time:daily-2230', channel: 'sleep', title: '睡眠时间到', body: '睡眠时间到', route: 'sleep', atMs,
})

export function createNotificationService(runtime: PlatformRuntime = detectPlatformRuntime(), plugin: NativeNotificationPlugin = LocalNotifications as unknown as NativeNotificationPlugin): NotificationService {
  const available = runtime === 'capacitor-android' || runtime === 'electron'; let initialized = false
  const permission = async (request = false) => {
    if (runtime === 'electron') return 'granted'
    if (!available) return 'unavailable'
    let state = (await plugin.checkPermissions()).display
    if (request && (state === 'prompt' || state === 'prompt-with-rationale')) state = (await plugin.requestPermissions()).display
    return state
  }
  const send = async (message: NotificationMessage) => {
    if (!available) return 'unavailable' as const
    if (!routes.has(message.route) || !message.eventKey) return 'rejected' as const
    if (runtime === 'electron') return (await (getElectronApi() as any)?.notifyDesktop?.(message))?.ok ? 'delivered' as const : 'unavailable' as const
    if (await permission(true) !== 'granted') return 'denied' as const
    const item: any = { id: nativeId(message.eventKey), title: message.title, body: message.body, channelId: message.channel, extra: { eventKey: message.eventKey, route: message.route } }
    if (message.atMs !== undefined) item.schedule = { at: new Date(message.atMs) }
    await plugin.schedule({ notifications: [item] }); return 'delivered' as const
  }
  return { available,
    async initialize() { if (!available || initialized) return; if (runtime === 'capacitor-android') for (const [id, name, importance] of channels) await plugin.createChannel({ id, name, importance }); initialized = true },
    permissionStatus: () => permission(false), requestPermission: () => permission(true), notify: send, schedule: send as NotificationService['schedule'],
    async cancel(eventKey) { if (available) await plugin.cancel({ notifications: [{ id: nativeId(eventKey) }] }) },
    async subscribe(listener) { if (!available) return () => {}; if (runtime === 'electron') return (getElectronApi() as any)?.onDesktopNotificationRoute?.(listener) || (() => {}); const handle = await plugin.addListener('localNotificationActionPerformed', action => listener(String(action.notification?.extra?.route || ''))); return () => { void handle.remove() } },
  }
}
