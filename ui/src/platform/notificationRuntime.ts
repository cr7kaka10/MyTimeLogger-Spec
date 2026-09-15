import type { LifecycleService } from './services'
import type { PlatformRuntime } from './runtime'
import { createDeviceRuntimeStateService } from './runtimeState'
import { createNotificationService, sleepTimeNotification } from './notifications'
import { createNotificationPreferences } from './notificationPreferences'
import { createNotificationCoordinator } from './notificationCoordinator'
import { classifySleepNotificationEvents } from './notificationEvents'

let cleanup = () => {}; let current: ReturnType<typeof buildRuntime> | null = null
export const nextSleepReminderAt = (now = new Date()): number => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  const value = (type: string) => Number(parts.find(part => part.type === type)?.value)
  const at = Date.UTC(value('year'), value('month') - 1, value('day'), 14, 30)
  return at > now.getTime() ? at : at + 86_400_000
}
const buildRuntime = (runtime: PlatformRuntime, db: any, lifecycle: LifecycleService) => {
  const notifications = createNotificationService(runtime)
  const preferences = createNotificationPreferences(createDeviceRuntimeStateService(runtime))
  let foreground = true
  const coordinator = createNotificationCoordinator({
    readFacts: () => ({ external: db.getUnclaimedRewards(), ledger: db.getLedgerFull(500, 0) }),
    preferences, notifications, isForeground: () => foreground,
  })
  return { notifications, preferences, coordinator, lifecycle, isForeground: () => foreground, setForeground: (value: boolean) => { foreground = value } }
}

export async function installNotificationRuntime(runtime: PlatformRuntime, db: any, lifecycle: LifecycleService) {
  cleanup(); if (runtime === 'web') { current = null; return }
  current = buildRuntime(runtime, db, lifecycle); await current.notifications.initialize().catch(() => {})
  if (runtime === 'capacitor-android') await current.notifications.schedule(sleepTimeNotification(nextSleepReminderAt())).catch(() => {})
  const reconcileSleep = async () => {
    const deviceId = String(db.ensureDeviceId?.() || ''); if (!deviceId) return
    const rows = db.allRaw("SELECT n.* FROM sleep_notifications n LEFT JOIN sleep_notification_receipts r ON r.notification_id=n.id AND r.device_id=? WHERE r.id IS NULL", [deviceId])
    for (const item of classifySleepNotificationEvents(rows)) if (await current?.notifications.notify(item) === 'delivered') {
      const id = `sleep-notification-receipt:${deviceId}:${item.eventKey.slice(6)}`
      db.runRaw("INSERT OR IGNORE INTO sleep_notification_receipts (id,device_id,notification_id,status,created_at,updated_at) VALUES (?,?,?,'displayed',datetime('now','localtime'),datetime('now','localtime'))", [id, deviceId, item.eventKey.slice(6)])
      db._afterWrite?.('sleep_notification_receipts', id)
    }
  }
  const reconcile = () => { void current?.coordinator.reconcile().catch(() => {}); void reconcileSleep().catch(() => {}) }
  const events = ['sync-pull-complete', 'balance-updated', 'mtl:goals-settled']
  events.forEach(event => window.addEventListener(event, reconcile))
  const authExpired = () => { void (async () => {
    const context = current; if (!context || !await context.preferences.beginAuthExpiry()) return
    const settings = await context.preferences.getSettings()
    if (settings.master && settings.account && (!context.isForeground() || settings.foreground)) await context.notifications.notify({ eventKey: 'auth:expired', channel: 'account', title: '登录已失效', body: '请重新登录后继续同步', route: 'settings' })
  })().catch(() => {}) }
  const authRestored = () => { void current?.preferences.clearAuthExpiry() }
  window.addEventListener('mtl:auth-expired', authExpired); window.addEventListener('mtl:auth-restored', authRestored)
  const unsubscribe = lifecycle.subscribe(event => { current?.setForeground(event === 'foreground'); if (event === 'foreground') reconcile() })
  cleanup = () => { events.forEach(event => window.removeEventListener(event, reconcile)); window.removeEventListener('mtl:auth-expired', authExpired); window.removeEventListener('mtl:auth-restored', authRestored); unsubscribe() }
  await current.coordinator.reconcile().catch(() => {})
}

export const getNotificationRuntime = () => current
