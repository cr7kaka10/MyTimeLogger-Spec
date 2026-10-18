export type SleepAutomationError = 'unavailable' | 'native_error' | 'rejected' | 'invalid_status'
export type SleepAutomationResult = { ok: boolean, error?: SleepAutomationError }
export type SleepAutomationStatus = { available: boolean, enabled: boolean, configured?: boolean, stage?: string, reason?: string, nextRunAt?: string, history?: unknown[], error?: SleepAutomationError }
type NativeSleepAutomation = { status(): string, enable(): boolean, disable(): void, test(): boolean, cancel(): void, configure(url: string, token: string): boolean, authorize(permission: string): boolean, clearConfiguration(): void }
type Host = { MTLSleepAutomation?: NativeSleepAutomation }

export function createSleepAutomation(host: Host = globalThis as unknown as Host) {
  const native = host.MTLSleepAutomation
  const action = (run?: () => boolean): SleepAutomationResult => {
    if (!run) return { ok: false, error: 'unavailable' }
    try { return run() ? { ok: true } : { ok: false, error: 'rejected' } } catch { return { ok: false, error: 'native_error' } }
  }
  return {
    status(): SleepAutomationStatus {
      if (!native) return { available: false, enabled: false, error: 'unavailable' }
      try {
        const value = JSON.parse(native.status()) as Record<string, unknown>
        if (!value || typeof value.enabled !== 'boolean') return { available: true, enabled: false, error: 'invalid_status' }
        return { ...value, available: true, enabled: value.enabled } as SleepAutomationStatus
      } catch { return { available: true, enabled: false, error: 'native_error' } }
    },
    enable: () => action(native && (() => native.enable())),
    disable: () => action(native && (() => { native.disable(); return true })),
    test: () => action(native && (() => native.test())),
    cancel: () => action(native && (() => { native.cancel(); return true })),
    configure: (url: string, token: string) => action(native && (() => native.configure(url, token))),
    authorize: (permission: string) => action(native && (() => native.authorize(permission))),
    clearConfiguration: () => action(native && (() => { native.clearConfiguration(); return true })),
  }
}
export const sleepAutomation = createSleepAutomation()
export type SleepAutomationConfig = { url: string, token: string } | null
const SLEEP_AUDIT_FIELDS = ['stage', 'result', 'reason', 'huaweiVersion', 'selectorType', 'attempt', 'durationMs'] as const
export function normalizeSleepAutomationAudit(metadata: Record<string, unknown>) {
  const output: Record<string, string | number> = {}
  for (const key of SLEEP_AUDIT_FIELDS) {
    const value = metadata[key]
    if (typeof value === 'number' && Number.isFinite(value)) output[key] = value
    else if (typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,80}$/.test(value)) output[key] = value
  }
  return output
}
export function createSleepAutomationConfigSync(api = sleepAutomation) {
  let previous: SleepAutomationConfig | undefined
  return (config: SleepAutomationConfig) => {
    const status = api.status()
    if (previous !== undefined && previous?.url === config?.url && previous?.token === config?.token && (config === null || status.configured)) return
    api.cancel()
    if (config) api.configure(config.url, config.token)
    else { api.disable(); api.clearConfiguration() }
    previous = config
  }
}
