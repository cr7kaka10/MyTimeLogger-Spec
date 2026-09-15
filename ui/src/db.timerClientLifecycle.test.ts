import { createCurrentTimerClientStore } from './db'
import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const store = createCurrentTimerClientStore()
const notifications: Array<object | null> = []
const unsubscribe = store.subscribe(client => notifications.push(client))
const client = { readCurrentTimer() {} }
store.set(client)
store.set(null)
unsubscribe()
store.set({ readCurrentTimer() {} })

assert(notifications.length === 3, 'listener must receive initial, ready, and cleared states')
assert(notifications[0] === null && notifications[1] === client && notifications[2] === null, 'client lifecycle order must be stable')
assert(JSON.stringify(notifications).indexOf('token') < 0, 'lifecycle values must not serialize credentials')
const dbSource = readFileSync(new URL('./db.ts', import.meta.url), 'utf8')
assert(dbSource.includes('setCurrentTimerClient(_currentTimerClient, true)'), 'configuration refresh must notify timer consumers')
assert(dbSource.includes('setCurrentTimerClient(null)'), 'account switch and logout must clear the timer client')
console.log('timer client lifecycle tests passed')
