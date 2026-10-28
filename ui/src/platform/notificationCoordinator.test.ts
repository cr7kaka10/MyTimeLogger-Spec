import { createNotificationCoordinator } from './notificationCoordinator'
import { createNotificationPreferences } from './notificationPreferences'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const values = new Map<string, string>(); const store = { available: true, get: async (key: string) => values.get(key) ?? null, set: async (key: string, value: string) => { values.set(key, value) }, remove: async () => {} }
const preferences = createNotificationPreferences(store); const delivered: string[] = []; let facts: any[] = [{ id: 'old', amount: 1, source_type: 'task_complete' }]
const notifications: any = { available: true, initialize: async () => {}, permissionStatus: async () => 'granted', requestPermission: async () => 'granted', notify: async (item: any) => { delivered.push(item.eventKey); return 'delivered' }, schedule: async () => 'delivered', cancel: async () => {}, subscribe: async () => () => {} }
const coordinator = createNotificationCoordinator({ readFacts: () => ({ external: [], ledger: facts }), preferences, notifications, isForeground: () => true })
await coordinator.reconcile()
facts = [...facts, { id: 'foreground', amount: 2, source_type: 'task_complete' }]; await coordinator.reconcile()
assert(delivered.length === 0, 'foreground defaults to in-App feedback without duplicate system notification')
await preferences.updateSettings({ foreground: true }); facts = [...facts, { id: 'opt-in', amount: 3, source_type: 'task_complete' }]; await coordinator.reconcile()
assert(delivered.join() === 'ledger:foreground', 'foreground skipped event joins the next opt-in summary')
await preferences.updateSettings({ rewards: false }); facts = [...facts, { id: 'disabled', amount: 4, source_type: 'task_complete' }]; await coordinator.reconcile()
assert(!delivered.includes('ledger:disabled'), 'disabled channel suppresses notification without affecting facts')
await preferences.updateSettings({ rewards: true }); await coordinator.reconcile()
assert(delivered.filter(key => key === 'ledger:disabled').length === 1, 'reenabled channel retries once')
let failOnce = true
notifications.notify = async (item: any) => { if (failOnce) { failOnce = false; throw new Error('permission temporarily denied') } delivered.push(item.eventKey); return 'delivered' }
facts = [...facts, { id: 'retry', amount: 5, source_type: 'task_complete' }]
await coordinator.reconcile(); assert(!delivered.includes('ledger:retry'), 'failed delivery stays pending')
await coordinator.reconcile(); await coordinator.reconcile()
assert(delivered.filter(key => key === 'ledger:retry').length === 1, 'successful retry is delivered once')
const dietValues = new Map<string, string>()
const dietPreferences = createNotificationPreferences({ ...store, get: async key => dietValues.get(key) ?? null, set: async (key, value) => { dietValues.set(key, value) } })
let dietFacts: any[] = []
const dietCoordinator = createNotificationCoordinator({ readFacts: () => ({ external: [], ledger: dietFacts }), preferences: dietPreferences, notifications, isForeground: () => true })
await dietCoordinator.reconcile()
dietFacts = [{ id: 'diet', amount: -20, source_type: 'exercise_diet_penalty', source_id: 'exercise-diet-penalty:1:2026-10-28:v5:lunch_on_time', target_date: '2026-10-28' }]
await dietCoordinator.reconcile()
assert(delivered.includes('ledger:diet'), 'meal penalty is visible immediately in foreground')
console.log('notification foreground policy tests passed')
