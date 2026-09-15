import type { DeviceRuntimeStateService, NotificationChannel } from './services'

export type NotificationSettings = Record<'master' | NotificationChannel | 'foreground', boolean>
export const DEFAULT_NOTIFICATION_SETTINGS: NotificationSettings = {
  master: true, timer: true, sleep: true, achievements: true, rewards: true, account: true, foreground: false,
}
type State = { baseline: boolean; seen: string[]; authExpired: boolean }
const SETTINGS_KEY = 'notifications.settings.v1'; const STATE_KEY = 'notifications.state.v1'; const MAX_SEEN = 500
const cleanKeys = (keys: string[]) => keys.filter(key => /^(ext|ledger):[A-Za-z0-9_.:-]+$/.test(key))

export function createNotificationPreferences(store: DeviceRuntimeStateService) {
  const readState = async (): Promise<State> => {
    try { const value = await store.get(STATE_KEY); const state = value ? JSON.parse(value) : {}; return { baseline: state.baseline === true, seen: cleanKeys(Array.isArray(state.seen) ? state.seen : []).slice(-MAX_SEEN), authExpired: state.authExpired === true } } catch { return { baseline: false, seen: [], authExpired: false } }
  }
  const writeState = (state: State) => store.set(STATE_KEY, JSON.stringify({ ...state, seen: cleanKeys(state.seen).slice(-MAX_SEEN) }))
  return {
    async getSettings(): Promise<NotificationSettings> { try { const raw = await store.get(SETTINGS_KEY); return { ...DEFAULT_NOTIFICATION_SETTINGS, ...(raw ? JSON.parse(raw) : {}) } } catch { return { ...DEFAULT_NOTIFICATION_SETTINGS } } },
    async updateSettings(patch: Partial<NotificationSettings>) { const next = { ...await this.getSettings(), ...patch }; await store.set(SETTINGS_KEY, JSON.stringify(next)); return next },
    async reconcileKeys(keys: string[]) { const state = await readState(); const safe = cleanKeys(keys); if (!state.baseline) { await writeState({ ...state, baseline: true, seen: [...new Set(safe)].slice(-MAX_SEEN) }); return { baseline: true, unseen: [] as string[] } } const known = new Set(state.seen); return { baseline: false, unseen: safe.filter(key => !known.has(key)) } },
    async markHandled(keys: string[]) { const state = await readState(); await writeState({ ...state, seen: [...new Set([...state.seen, ...cleanKeys(keys)])].slice(-MAX_SEEN) }) },
    async beginAuthExpiry() { const state = await readState(); if (state.authExpired) return false; await writeState({ ...state, authExpired: true }); return true },
    async clearAuthExpiry() { const state = await readState(); if (state.authExpired) await writeState({ ...state, authExpired: false }) },
  }
}

export type NotificationPreferences = ReturnType<typeof createNotificationPreferences>
