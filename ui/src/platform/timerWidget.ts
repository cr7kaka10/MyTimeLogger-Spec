import { Preferences } from '@capacitor/preferences'
import { parseTimerWidgetCommand, type TimerWidgetCommand } from '@core/TimerWidgetCommand'

export type TimerWidgetJournalEvent = { commandId: string, action: 'start' | 'switch' | 'stop', categoryId: number, eventEpochMs: number }
type JournalStore = {
  get(options: { key: string }): Promise<{ value: string | null }>
  set(options: { key: string, value: string }): Promise<void>
}
const KEY = 'mtl.runtime.timer.widget.integration-journal.v1'
const isEvent = (value: unknown): value is TimerWidgetJournalEvent => {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  const keys = Object.keys(item)
  return keys.every(key => ['commandId', 'action', 'categoryId', 'eventEpochMs'].includes(key))
    && typeof item.commandId === 'string'
    && ['start', 'switch', 'stop'].includes(String(item.action))
    && Number.isSafeInteger(item.categoryId) && Number(item.categoryId) > 0
    && Number.isSafeInteger(item.eventEpochMs)
}

export function createTimerWidgetJournal(store: JournalStore = Preferences) {
  const read = async () => {
    try {
      const parsed: unknown = JSON.parse((await store.get({ key: KEY })).value ?? '[]')
      return Array.isArray(parsed) ? parsed.filter(isEvent) : []
    } catch { return [] }
  }
  return {
    read,
    async ack(commandId: string) {
      const pending = (await read()).filter(event => event.commandId !== commandId)
      await store.set({ key: KEY, value: JSON.stringify(pending) })
    },
  }
}

export type TimerWidgetJournal = ReturnType<typeof createTimerWidgetJournal>
export function consumeTimerWidgetJournal(journal: TimerWidgetJournal, consume: (event: TimerWidgetJournalEvent) => Promise<void>): void {
  void (async () => {
    const seen = new Set<string>()
    for (const event of await journal.read()) {
      if (seen.has(event.commandId)) continue
      seen.add(event.commandId)
      try { await consume(event); await journal.ack(event.commandId) } catch { /* retry later */ }
    }
  })()
}

export type TimerWidgetCommandResult = 'applied' | 'requires_app' | 'failed'
type TimerWidgetHost = {
  MTLTimerWidget?: {
    ready(): void, refresh?(): void, ack(commandId: string, result: TimerWidgetCommandResult): void
    configureRuntime?(json: string): boolean, clearRuntime?(): void
  }
  addEventListener(name: string, listener: (event: { detail?: unknown }) => void): void
  removeEventListener(name: string, listener: (event: { detail?: unknown }) => void): void
}

export const refreshTimerWidget = (host: Pick<TimerWidgetHost, 'MTLTimerWidget'> = window as unknown as TimerWidgetHost) => {
  host.MTLTimerWidget?.refresh?.()
}

export type TimerWidgetRuntimeConfig = {
  serverUrl: string, authToken: string, deviceId: string, verifiedUserId: string, generation: number
}
export const configureTimerWidgetRuntime = (
  config: TimerWidgetRuntimeConfig,
  host: Pick<TimerWidgetHost, 'MTLTimerWidget'> = window as unknown as TimerWidgetHost,
) => host.MTLTimerWidget?.configureRuntime?.(JSON.stringify({
  serverUrl: config.serverUrl, authToken: config.authToken, deviceId: config.deviceId,
  verifiedUserId: config.verifiedUserId, generation: config.generation,
})) === true
export const clearTimerWidgetRuntime = (
  host: Pick<TimerWidgetHost, 'MTLTimerWidget'> = window as unknown as TimerWidgetHost,
) => host.MTLTimerWidget?.clearRuntime?.()

export function registerTimerWidgetCommandListener(
  handle: (command: TimerWidgetCommand) => Promise<TimerWidgetCommandResult>,
  host: TimerWidgetHost = window as unknown as TimerWidgetHost,
): () => void {
  const results = new Map<string, Promise<TimerWidgetCommandResult>>()
  const listener = (event: { detail?: unknown }) => {
    const parsed = parseTimerWidgetCommand(event.detail)
    if (!parsed.ok) return
    let result = results.get(parsed.command.commandId)
    if (!result) {
      result = Promise.resolve().then(() => handle(parsed.command)).then(
        value => ['applied', 'requires_app', 'failed'].includes(value) ? value : 'failed',
        () => 'failed',
      )
      results.set(parsed.command.commandId, result)
    }
    void result.then(value => host.MTLTimerWidget?.ack(parsed.command.commandId, value))
  }
  host.addEventListener('mtl:timer-widget-command', listener)
  host.MTLTimerWidget?.ready()
  let closed = false
  return () => {
    if (closed) return
    closed = true
    host.removeEventListener('mtl:timer-widget-command', listener)
  }
}
