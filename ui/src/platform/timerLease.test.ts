import { createTimerLeaseMonitor, loadTimerLeaseJournal, persistTimerLeaseJournal, requireTimerLeaseCapability, TimerLeaseCommandJournal } from './timerLease'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const journal = new TimerLeaseCommandJournal(2)
const first = journal.append('pause', { revision: 1 }, 'k1')
assert(journal.append('pause', { revision: 9 }, 'k1').seq === first.seq, 'duplicate idempotency key must replay')
journal.append('resume', { revision: 2 }, 'k2'); journal.append('stop', { revision: 3 }, 'k3')
assert(journal.pending().length === 2 && journal.pending()[0].idempotencyKey === 'k2', 'journal must be bounded')
assert(journal.acknowledge('k2') && journal.pending().length === 1, 'acknowledge should remove only confirmed command')
assert(requireTimerLeaseCapability({ capability: 'timer-current-state-v1', enforced: true }).ok, 'capability should be accepted')
const gated = requireTimerLeaseCapability({ capability: 'old', enforced: true })
assert(!gated.ok && gated.code === 'upgrade_required', 'old client must be gated')

const values = new Map<string, string>()
const runtime = {
  available: true,
  get: async (key: string) => values.get(key) ?? null,
  set: async (key: string, value: string) => { values.set(key, value) },
  remove: async (key: string) => { values.delete(key) },
}
await persistTimerLeaseJournal(runtime, journal)
const restored = await loadTimerLeaseJournal(runtime)
assert(restored.pending().length === 0, 'restart journal must never auto-takeover current state')
assert(restored.expired().length === 1 && restored.expired()[0].idempotencyKey === 'k3', 'old journal should remain diagnostic-only')

let reads = 0
const holder: { current?: (event: 'foreground' | 'background' | 'online' | 'offline') => void } = {}
const monitor = createTimerLeaseMonitor(async () => { reads += 1 }, next => { holder.current = next; return () => { holder.current = undefined } }, 10)
monitor.start(); await new Promise(resolve => setTimeout(resolve, 1)); holder.current?.('online')
monitor.stop(); assert(reads >= 1, 'monitor must refresh via bounded GET polling')
console.log('timer lease journal and monitor tests passed')
