import type { LifecycleEvent, DeviceRuntimeStateService } from './services'

export type TimerLeaseJournalCommand = 'pause' | 'resume' | 'stop' | 'switch' | 'start'
export interface TimerLeaseJournalEntry {
  seq: number
  command: TimerLeaseJournalCommand
  payload: Record<string, unknown>
  idempotencyKey: string
}

export class TimerLeaseCommandJournal {
  private entries: TimerLeaseJournalEntry[] = []
  private expiredEntries: TimerLeaseJournalEntry[] = []
  private nextSeq = 1
  constructor(private readonly maxEntries = 100) {}
  restore(entries: TimerLeaseJournalEntry[]): void {
    this.expiredEntries = entries.slice(-this.maxEntries)
    this.entries = []
    this.nextSeq = (this.expiredEntries.at(-1)?.seq ?? 0) + 1
  }
  append(command: TimerLeaseJournalCommand, payload: Record<string, unknown>, idempotencyKey: string): TimerLeaseJournalEntry {
    const existing = this.entries.find(entry => entry.idempotencyKey === idempotencyKey)
    if (existing) return existing
    const entry = { seq: this.nextSeq++, command, payload: { ...payload }, idempotencyKey }
    this.entries.push(entry)
    if (this.entries.length > this.maxEntries) this.entries.splice(0, this.entries.length - this.maxEntries)
    return entry
  }
  acknowledge(idempotencyKey: string): boolean {
    const before = this.entries.length
    this.entries = this.entries.filter(entry => entry.idempotencyKey !== idempotencyKey)
    return before !== this.entries.length
  }
  pending(): TimerLeaseJournalEntry[] { return this.entries.map(entry => ({ ...entry, payload: { ...entry.payload } })) }
  expired(): TimerLeaseJournalEntry[] { return this.expiredEntries.map(entry => ({ ...entry, payload: { ...entry.payload } })) }
}

const JOURNAL_KEY = 'timer.lease.commands.v1'
export async function loadTimerLeaseJournal(runtime: DeviceRuntimeStateService, journal = new TimerLeaseCommandJournal()): Promise<TimerLeaseCommandJournal> {
  if (!runtime.available) return journal
  const raw = await runtime.get(JOURNAL_KEY)
  if (raw) {
    try { journal.restore(JSON.parse(raw) as TimerLeaseJournalEntry[]) } catch { journal.restore([]) }
  }
  return journal
}
export async function persistTimerLeaseJournal(runtime: DeviceRuntimeStateService, journal: TimerLeaseCommandJournal): Promise<void> {
  if (runtime.available) await runtime.set(JOURNAL_KEY, JSON.stringify(journal.pending()))
}

export type LeaseCapabilityResult = { ok: true } | { ok: false; code: 'upgrade_required' | 'unavailable' }
export function requireTimerLeaseCapability(capability: { capability?: string; enforced?: boolean } | null | undefined, required = 'timer-current-state-v1'): LeaseCapabilityResult {
  if (!capability || capability.capability !== required) return { ok: false, code: 'upgrade_required' }
  return capability.enforced === false ? { ok: false, code: 'upgrade_required' } : { ok: true }
}

export interface TimerLeaseMonitor {
  start(): void
  stop(): void
  notify(event: LifecycleEvent): void
}
export function createTimerLeaseMonitor(
  read: () => Promise<unknown>,
  subscribe: (listener: (event: LifecycleEvent) => void) => () => void,
  intervalMs = 15_000,
  isActive = () => true,
  isForeground = () => true,
): TimerLeaseMonitor {
  let timer: ReturnType<typeof setTimeout> | null = null
  let stopped = true
  let unsubscribe = () => {}
  const poll = () => {
    if (stopped) return
    if (!isActive() || !isForeground()) {
      timer = setTimeout(poll, intervalMs)
      return
    }
    void read().finally(() => { if (!stopped) timer = setTimeout(poll, intervalMs) })
  }
  return {
    start() {
      if (!stopped) return
      stopped = false
      unsubscribe = subscribe(event => {
        if (event === 'foreground' || event === 'online') poll()
      })
      poll()
    },
    stop() {
      stopped = true
      if (timer) clearTimeout(timer)
      timer = null
      unsubscribe()
      unsubscribe = () => {}
    },
    notify(event) {
      if (event === 'foreground' || event === 'online') poll()
    },
  }
}
