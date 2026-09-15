import { createNotificationPreferences, DEFAULT_NOTIFICATION_SETTINGS } from './notificationPreferences'
import { createNotificationCoordinator } from './notificationCoordinator'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const values = new Map<string, string>()
const store = { available: true, get: async (key: string) => values.get(key) ?? null, set: async (key: string, value: string) => { values.set(key, value) }, remove: async (key: string) => { values.delete(key) } }
const preferences = createNotificationPreferences(store)
assert(JSON.stringify(await preferences.getSettings()) === JSON.stringify(DEFAULT_NOTIFICATION_SETTINGS), 'all channels default on and foreground defaults off')
const historical = ['ext:old', 'ledger:old']
assert((await preferences.reconcileKeys(historical)).baseline && (await preferences.reconcileKeys(historical)).unseen.length === 0, 'first observation establishes a silent baseline')
assert((await preferences.reconcileKeys(['ext:old', 'ledger:new'])).unseen.join() === 'ledger:new', 'replay is deduplicated after restart')
await preferences.markHandled(Array.from({ length: 505 }, (_, index) => `ledger:${index}`))
const saved = JSON.parse(values.get('notifications.state.v1') || '{}')
assert(saved.seen.length === 500 && saved.seen[0] === 'ledger:5', 'persisted seen keys are capped at 500')
assert(!values.get('notifications.state.v1')?.match(/password|token|response|note/i), 'state must not persist sensitive fields')
const coordinatorValues = new Map<string, string>()
const coordinatorPrefs = createNotificationPreferences({ ...store, get: async key => coordinatorValues.get(key) ?? null, set: async (key, value) => { coordinatorValues.set(key, value) } })
let external: any[] = [{ id: 'old', ext_id: 'old', item_type: 'task', item_name: '旧', coins: 1, status: 0 }]; let ledger: any[] = []; const delivered: string[] = []
const coordinator = createNotificationCoordinator({
  readFacts: () => ({ external, ledger }), preferences: coordinatorPrefs, isForeground: () => false,
  notifications: { available: true, initialize: async () => {}, permissionStatus: async () => 'granted', requestPermission: async () => 'granted', notify: async item => { delivered.push(item.eventKey); return 'delivered' }, schedule: async () => 'delivered', cancel: async () => {}, subscribe: async () => () => {} },
})
await coordinator.reconcile(); assert(delivered.length === 0, 'coordinator must not replay history on first run')
external = [...external, { id: 'new', ext_id: 'new', item_type: 'task', item_name: '新', coins: 2, status: 0 }]; ledger = [{ id: 'new', amount: 3, source_type: 'task_complete' }]
await Promise.all([coordinator.reconcile(), coordinator.reconcile()])
assert(delivered.length === 2 && new Set(delivered).size === 2, 'concurrent trigger and replay must deliver each authoritative fact once')
assert(await coordinatorPrefs.beginAuthExpiry() && !await coordinatorPrefs.beginAuthExpiry(), 'one authentication expiry episode must notify once')
await coordinatorPrefs.clearAuthExpiry(); assert(await coordinatorPrefs.beginAuthExpiry(), 'successful authentication must reset expiry suppression')
console.log('notification preference tests passed')
