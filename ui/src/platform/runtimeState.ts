import { Preferences } from '@capacitor/preferences'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'
import type { DeviceRuntimeStateService } from './services'

type PreferencesStore = {
  get(options: { key: string }): Promise<{ value: string | null }>
  set(options: { key: string, value: string }): Promise<void>
  remove(options: { key: string }): Promise<void>
}
type PrivateStore = {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

const runtimeKey = (key: string) => `mtl.runtime.${key}`

export function createDeviceRuntimeStateService(
  runtime: PlatformRuntime = detectPlatformRuntime(),
  store: PreferencesStore = Preferences,
  privateStore: PrivateStore | null = typeof localStorage === 'undefined' ? null : localStorage,
): DeviceRuntimeStateService {
  const available = runtime === 'capacitor-android' || runtime === 'electron'
  return {
    available,
    async get(key) {
      if (!available) return null
      if (runtime === 'electron') return privateStore?.getItem(runtimeKey(key)) ?? null
      return (await store.get({ key: runtimeKey(key) })).value
    },
    async set(key, value) {
      if (!available) return
      if (runtime === 'electron') privateStore?.setItem(runtimeKey(key), value)
      else await store.set({ key: runtimeKey(key), value })
    },
    async remove(key) {
      if (!available) return
      if (runtime === 'electron') privateStore?.removeItem(runtimeKey(key))
      else await store.remove({ key: runtimeKey(key) })
    },
  }
}
