import type { PlatformRuntime } from './runtime'
import type { DeviceIdentityService, DeviceRuntimeStateService } from './services'

const DEVICE_ID_KEY = 'device.id.v1'

const makeDeviceId = (): string => {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `device_${random}`
}

export function createDeviceIdentityService(
  runtime: PlatformRuntime,
  runtimeState: DeviceRuntimeStateService,
  createId: () => string = makeDeviceId,
): DeviceIdentityService {
  const available = runtime === 'electron' || runtime === 'capacitor-android'
  return {
    available,
    async get() {
      return available ? runtimeState.get(DEVICE_ID_KEY) : null
    },
    async getOrCreate() {
      if (!available || !runtimeState.available) return null
      const existing = await runtimeState.get(DEVICE_ID_KEY)
      if (existing) return existing
      const created = createId()
      await runtimeState.set(DEVICE_ID_KEY, created)
      return created
    },
  }
}
