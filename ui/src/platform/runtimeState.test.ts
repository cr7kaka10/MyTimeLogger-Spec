import { createDeviceRuntimeStateService } from './runtimeState'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const values = new Map<string, string>()
const preferences = {
  get: async ({ key }: { key: string }) => ({ value: values.get(key) ?? null }),
  set: async ({ key, value }: { key: string, value: string }) => { values.set(key, value) },
  remove: async ({ key }: { key: string }) => { values.delete(key) },
}
const firstProcess = createDeviceRuntimeStateService('capacitor-android', preferences)
await firstProcess.set('timer.logic.snapshot.v1', '{"state":"running"}')
await firstProcess.set('atimelogger.remote-context.v1', '{"activity":"a1"}')
const restartedProcess = createDeviceRuntimeStateService('capacitor-android', preferences)
assert(await restartedProcess.get('timer.logic.snapshot.v1') === '{"state":"running"}', 'timer snapshot should survive adapter recreation')
assert(await restartedProcess.get('atimelogger.remote-context.v1') === '{"activity":"a1"}', 'remote activity should survive adapter recreation')
assert([...values.keys()].every(key => key.startsWith('mtl.runtime.')), 'runtime keys must stay in the dedicated Preferences namespace')
await restartedProcess.remove('timer.logic.snapshot.v1'); assert(await restartedProcess.get('timer.logic.snapshot.v1') === null, 'runtime state should be removable')
const web = createDeviceRuntimeStateService('web', preferences); await web.set('ignored', 'secret')
assert(!web.available && !values.has('mtl.runtime.ignored'), 'Web must not write Capacitor Preferences')
const privateValues = new Map<string, string>()
const privateStore = {
  getItem: (key: string) => privateValues.get(key) ?? null,
  setItem: (key: string, value: string) => { privateValues.set(key, value) },
  removeItem: (key: string) => { privateValues.delete(key) },
}
const pc = createDeviceRuntimeStateService('electron', preferences, privateStore)
await pc.set('timer.lease.v1', '{"revision":2}')
const restartedPc = createDeviceRuntimeStateService('electron', preferences, privateStore)
assert(await restartedPc.get('timer.lease.v1') === '{"revision":2}', 'PC runtime state should survive renderer recreation')
assert([...privateValues.keys()].every(key => key.startsWith('mtl.runtime.')), 'PC runtime state must use a private namespace')
console.log('platform runtime state tests passed')
