import { createDeviceIdentityService } from './deviceIdentity'
import { createDeviceRuntimeStateService } from './runtimeState'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const values = new Map<string, string>()
const store = {
  getItem: (key: string) => values.get(key) ?? null,
  setItem: (key: string, value: string) => { values.set(key, value) },
  removeItem: (key: string) => { values.delete(key) },
}
const runtime = createDeviceRuntimeStateService('electron', {} as any, store)
const identity = createDeviceIdentityService('electron', runtime, () => 'device_test')
assert(await identity.getOrCreate() === 'device_test', 'device ID should be generated')
assert(await identity.getOrCreate() === 'device_test', 'device ID should be stable after restart')
assert((await identity.get()) === 'device_test', 'device ID should be readable')
const web = createDeviceIdentityService('web', runtime, () => 'must-not-create')
assert(!web.available && await web.getOrCreate() === null, 'Web must not persist a device ID')
console.log('device identity tests passed')
