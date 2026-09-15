import { clearTimerWidgetRuntime, configureTimerWidgetRuntime, consumeTimerWidgetJournal, createTimerWidgetJournal, registerTimerWidgetCommandListener } from './timerWidget'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const flush = () => new Promise(resolve => setTimeout(resolve, 0))
const event = { commandId: 'cmd-1', action: 'switch' as const, categoryId: 2, eventEpochMs: 123 }
let raw: string | null = JSON.stringify([event])
let writes = 0
const store = {
  get: async () => ({ value: raw }),
  set: async ({ value }: { key: string, value: string }) => { writes++; raw = value },
}
const journal = createTimerWidgetJournal(store)
let release = () => {}
let handled = 0
consumeTimerWidgetJournal(journal, async () => {
  handled++
  await new Promise<void>(resolve => { release = resolve })
})
assert(handled === 0 && writes === 0, 'consume must return without waiting for remote work')
await flush()
assert(handled === 1 && writes === 0, 'pending remote work must not ack early')
release(); await flush()
assert(writes === 1 && (await journal.read()).length === 0, 'success must ack exactly once')

raw = JSON.stringify([event]); writes = 0
consumeTimerWidgetJournal(journal, async () => { throw new Error('offline') })
await flush()
assert(writes === 0 && (await journal.read()).length === 1, 'failure must remain retryable')

raw = JSON.stringify([event, event]); writes = 0; handled = 0
consumeTimerWidgetJournal(journal, async () => { handled++ })
await flush()
assert(handled === 1 && writes === 1, 'duplicate commandId must consume and ack once')

let listener = (_event: { detail?: unknown }) => {}; let ready = 0; let removed = 0
const acks: string[] = []
const host = {
  MTLTimerWidget: { ready: () => { ready++ }, ack: (id: string, result: string) => acks.push(`${id}:${result}`) },
  addEventListener: (_name: string, next: (event: { detail?: unknown }) => void) => { listener = next },
  removeEventListener: () => { removed++ },
}
let runs = 0
const cleanup = registerTimerWidgetCommandListener(async command => {
  runs++
  if (command.categoryId === 8) return 'requires_app'
  if (command.categoryId === 9) throw new Error('failed')
  return 'applied'
}, host)
const command = (commandId: string, categoryId: number) => ({ detail: { action: 'start', commandId, categoryId, eventEpochMs: 123 } })
listener(command('live-1', 7)); await flush(); listener(command('live-1', 7)); await flush()
listener(command('input-1', 8)); listener(command('failed-1', 9)); await flush()
assert(ready === 1 && runs === 3, 'listener must register ready and never rerun duplicate commands')
assert(acks.join(',') === 'live-1:applied,live-1:applied,input-1:requires_app,failed-1:failed', 'listener must ack every result')
cleanup(); assert(removed === 1, 'listener cleanup must unregister exactly once')

let configured = ''; let cleared = 0
const runtimeHost = { MTLTimerWidget: {
  ready: () => {}, ack: () => {}, configureRuntime: (json: string) => { configured = json; return true }, clearRuntime: () => { cleared++ },
} }
assert(configureTimerWidgetRuntime({ serverUrl: 'https://example.test', authToken: 'test-token', deviceId: 'd1', verifiedUserId: 'u1', generation: 7 }, runtimeHost), 'runtime bridge must accept valid config')
assert(Object.keys(JSON.parse(configured)).sort().join(',') === 'authToken,deviceId,generation,serverUrl,verifiedUserId', 'runtime config must whitelist exactly five fields')
clearTimerWidgetRuntime(runtimeHost); assert(cleared === 1, 'runtime clear must call native bridge')

console.log('timer widget journal tests passed')
