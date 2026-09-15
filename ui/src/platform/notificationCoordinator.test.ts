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
assert(delivered.join() === 'ledger:opt-in', 'foreground system notification is available after explicit opt-in')
await preferences.updateSettings({ rewards: false }); facts = [...facts, { id: 'disabled', amount: 4, source_type: 'task_complete' }]; await coordinator.reconcile()
assert(delivered.length === 1, 'disabled channel suppresses notification without affecting facts')
console.log('notification foreground policy tests passed')
