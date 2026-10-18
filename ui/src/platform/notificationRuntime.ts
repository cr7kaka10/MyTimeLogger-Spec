import type { LifecycleService } from './services'
import type { PlatformRuntime } from './runtime'
import { createDeviceRuntimeStateService } from './runtimeState'
import { createNotificationService, sleepTimeNotification } from './notifications'
import { createNotificationPreferences } from './notificationPreferences'
import { createNotificationCoordinator } from './notificationCoordinator'
import { classifySleepNotificationEvents } from './notificationEvents'
import { morningNotifications, poopReminder } from './contextualNotifications'
import type { LogicSnapshot } from '@core/LogicSnapshot'
import { recordBehavior } from '../utils/behaviorAudit'

let cleanup = () => {}; let current: ReturnType<typeof buildRuntime> | null = null
export const nextSleepReminderAt = (now = new Date()): number => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  const value = (type: string) => Number(parts.find(part => part.type === type)?.value)
  const at = Date.UTC(value('year'), value('month') - 1, value('day'), 14, 30)
  return at > now.getTime() ? at : at + 86_400_000
}
const buildRuntime = (runtime: PlatformRuntime, db: any, lifecycle: LifecycleService) => {
  const notifications = createNotificationService(runtime)
  const runtimeState = createDeviceRuntimeStateService(runtime)
  const preferences = createNotificationPreferences(runtimeState)
  let foreground = true
  const coordinator = createNotificationCoordinator({
    readFacts: () => ({ external: db.getUnclaimedRewards(), ledger: db.getLedgerFull(500, 0) }),
    preferences, notifications, isForeground: () => foreground,
  })
  return { notifications, preferences, coordinator, lifecycle, runtimeState, isForeground: () => foreground, setForeground: (value: boolean) => { foreground = value } }
}

export async function installNotificationRuntime(runtime: PlatformRuntime, db: any, lifecycle: LifecycleService) {
  cleanup(); if (runtime === 'web') { current = null; return }
  current = buildRuntime(runtime, db, lifecycle); await current.notifications.initialize().catch(() => {})
  if (runtime === 'capacitor-android') await current.notifications.schedule(sleepTimeNotification(nextSleepReminderAt())).catch(() => {})
  let morningKeys: string[] = []; let poopKey: string | null = null
  let lastTimerSnapshot: LogicSnapshot | null = null
  const poopStateKey = 'notifications.poop-scheduled-key.v1'
  if (runtime === 'capacitor-android') poopKey = await current.runtimeState.get(poopStateKey).catch(() => null)
  const contextualEnabled = import.meta.env.VITE_CONTEXTUAL_NOTIFICATIONS !== 'false'
  const reconcileMorning = async () => {
    if (!contextualEnabled || runtime !== 'capacitor-android' || !current) return
    for (const key of morningKeys) await current.notifications.cancel(key).catch(() => {})
    const messages = morningNotifications(); morningKeys = []
    for (const message of messages) { const result = await current.notifications.schedule(message).catch(() => 'unavailable'); recordBehavior('notification.schedule', { notification_type: message.eventKey.includes('sleep-upload') ? 'sleep_upload' : 'body_metrics', permission_state: result, reason: 'daily', result }, message.eventKey); if (result === 'delivered') morningKeys.push(message.eventKey) }
  }
  const reconcilePoop = async (snapshot: LogicSnapshot | null) => {
    if (!contextualEnabled || runtime !== 'capacitor-android' || !current) return
    const message = snapshot ? poopReminder(snapshot) : null
    if (!message) { if (poopKey) { await current.notifications.cancel(poopKey).catch(() => {}); recordBehavior('notification.cancel', { notification_type: 'poop_8m', reason: 'timer_ineligible', result: 'succeeded' }) }; poopKey = null; await current.runtimeState.remove(poopStateKey).catch(() => {}); return }
    if (poopKey === message.eventKey) {
      const permission = await current.notifications.permissionStatus().catch(() => 'unavailable')
      if (permission === 'granted' || permission === 'unavailable') return
      recordBehavior('notification.cancel', { notification_type: 'poop_8m', permission_state: permission, reason: 'permission_changed', result: 'succeeded' }, poopKey)
      await current.notifications.cancel(poopKey).catch(() => {})
      poopKey = null
      await current.runtimeState.remove(poopStateKey).catch(() => {})
    }
    if (poopKey) await current.notifications.cancel(poopKey).catch(() => {})
    const result = await current.notifications.schedule(message).catch(() => 'unavailable'); recordBehavior('notification.schedule', { notification_type: 'poop_8m', permission_state: result, reason: 'timer_active', result }, message.eventKey); poopKey = result === 'delivered' ? message.eventKey : null
    if (poopKey) await current.runtimeState.set(poopStateKey, poopKey).catch(() => {})
    else await current.runtimeState.remove(poopStateKey).catch(() => {})
  }
  await reconcileMorning().catch(() => {})
  const reconcileSleep = async () => {
    const deviceId = String(db.ensureDeviceId?.() || ''); if (!deviceId) return
    const rows = db.allRaw("SELECT n.* FROM sleep_notifications n LEFT JOIN sleep_notification_receipts r ON r.notification_id=n.id AND r.device_id=? WHERE r.id IS NULL AND n.sleep_date = strftime('%Y-%m-%d', 'now', '+8 hours')", [deviceId])
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
  let poopWork = Promise.resolve()
  const queuePoop = (snapshot: LogicSnapshot | null) => { poopWork = poopWork.then(() => reconcilePoop(snapshot)).catch(() => {}); return poopWork }
  const timerSnapshot = (event: Event) => { lastTimerSnapshot = (event as CustomEvent<LogicSnapshot | null>).detail; void queuePoop(lastTimerSnapshot) }
  const authCleared = () => { lastTimerSnapshot = null; void queuePoop(null); for (const key of morningKeys) void current?.notifications.cancel(key); morningKeys = [] }
  window.addEventListener('mtl:timer-snapshot', timerSnapshot); window.addEventListener('mtl:auth-cleared', authCleared)
  const unsubscribe = lifecycle.subscribe(event => { current?.setForeground(event === 'foreground'); if (event === 'foreground') { reconcile(); void reconcileMorning(); void queuePoop(lastTimerSnapshot) } })
  cleanup = () => { events.forEach(event => window.removeEventListener(event, reconcile)); window.removeEventListener('mtl:auth-expired', authExpired); window.removeEventListener('mtl:auth-restored', authRestored); window.removeEventListener('mtl:timer-snapshot', timerSnapshot); window.removeEventListener('mtl:auth-cleared', authCleared); unsubscribe() }
  await current.coordinator.reconcile().catch(() => {})
}

export const getNotificationRuntime = () => current
