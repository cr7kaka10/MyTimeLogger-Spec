import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const source = readFileSync(fileURLToPath(new URL('./db.ts', import.meta.url)), 'utf8')
const syncStart = source.indexOf('export async function syncNow')
const before = source.indexOf('refreshCurrentTimerState()', syncStart)
const ordinary = source.indexOf('_syncWorker.flushNow', before)
const after = source.indexOf('refreshCurrentTimerState()', ordinary)
assert(syncStart >= 0 && before > syncStart && ordinary > before && after > ordinary, 'manual sync must run timer GET -> ordinary push/pull -> timer GET')
assert(source.indexOf('catch {', ordinary) < after, 'ordinary sync failure must still continue to the final timer GET')
assert(source.includes("new CustomEvent('mtl:current-timer-state'"), 'successful timer GET must notify the timer page')
console.log('manual sync current timer contract passed')
