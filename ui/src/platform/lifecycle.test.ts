import { createCapacitorAppLifecycleService, createCapacitorNetworkLifecycleService, createLifecycleService, installAndroidSyncLifecycle, installAndroidTimerWidgetLifecycle, type LifecycleSources } from './lifecycle'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const app: Array<(active: boolean) => void> = []
const network: Array<(online: boolean) => void> = []
let removed = 0
const sources: LifecycleSources = {
  onAppState: listener => { app.push(listener); return () => { removed++ } },
  onNetworkState: listener => { network.push(listener); return () => { removed++ } },
}
const events: string[] = []
const lifecycle = createLifecycleService(sources)
const unsubscribe = lifecycle.subscribe(event => events.push(event))
app[0]?.(true); app[0]?.(false); network[0]?.(true); network[0]?.(true); network[0]?.(false); network[0]?.(false)
assert(events.join(',') === 'foreground,background,online,offline', 'host events should map to lifecycle events')
unsubscribe()
assert(removed === 2, 'unsubscribe should remove App and Network listeners')
assert(!createLifecycleService(null).available, 'missing host sources should be unavailable')

let nativeListener = (_state: { isActive: boolean }) => {}; let nativeRemoved = 0; let nativeRegistered = 0
const nativeApp = { addListener: (_event: 'appStateChange', listener: typeof nativeListener) => { nativeRegistered++; nativeListener = listener; return { remove: () => { nativeRemoved++ } } } }
const nativeEvents: string[] = []
const nativeLifecycle = createCapacitorAppLifecycleService('capacitor-android', nativeApp)
const removeNative = nativeLifecycle.subscribe(event => nativeEvents.push(event))
nativeListener({ isActive: true }); nativeListener({ isActive: false }); await Promise.resolve(); await Promise.resolve(); removeNative()
assert(nativeEvents.join(',') === 'foreground,background', 'Capacitor App states should map to lifecycle events')
assert(nativeRegistered === 1 && nativeRemoved === 1, 'unsubscribe should remove Capacitor App listener')
assert(!createCapacitorAppLifecycleService('electron', nativeApp).available && nativeRegistered === 1, 'Electron must not register Capacitor App listener')

let networkListener = (_state: { connected: boolean }) => {}; let networkRemoved = 0; let networkRegistered = 0
const nativeNetwork = { addListener: (_event: 'networkStatusChange', listener: typeof networkListener) => { networkRegistered++; networkListener = listener; return { remove: () => { networkRemoved++ } } } }
const networkEvents: string[] = []
const networkLifecycle = createCapacitorNetworkLifecycleService('capacitor-android', nativeNetwork)
const removeNetwork = networkLifecycle.subscribe(event => networkEvents.push(event))
networkListener({ connected: true }); networkListener({ connected: true }); networkListener({ connected: false }); await Promise.resolve(); await Promise.resolve(); removeNetwork()
assert(networkEvents.join(',') === 'online,offline', 'Capacitor Network states should map once per transition')
assert(networkRegistered === 1 && networkRemoved === 1, 'unsubscribe should remove Capacitor Network listener')
assert(!createCapacitorNetworkLifecycleService('web', nativeNetwork).available && networkRegistered === 1, 'Web must not register Capacitor Network listener')

let widgetRefreshes = 0; let widgetListener = (_active: boolean) => {}; let widgetRemoved = 0
const widgetLifecycle = createLifecycleService({ onAppState: listener => { widgetListener = listener; return () => { widgetRemoved++ } } })
const removeWidget = installAndroidTimerWidgetLifecycle(widgetLifecycle, () => { widgetRefreshes++ })
assert(widgetRefreshes === 0, 'widget lifecycle must not create local timer state at bootstrap')
widgetListener(false); widgetListener(true)
assert(widgetRefreshes === 1, 'foreground must refresh the imported authoritative snapshot once')
removeWidget(); widgetListener(true)
assert(widgetRemoved === 1 && widgetRefreshes === 1, 'widget lifecycle listener must be removable')

let syncApp = (_active: boolean) => {}; let syncNetwork = (_online: boolean) => {}; let tick = () => {}; let cleared = 0
const syncReasons: string[] = []
const removeSync = installAndroidSyncLifecycle(
  createLifecycleService({ onAppState: listener => { syncApp = listener; return () => { removed++ } } }),
  createLifecycleService({ onNetworkState: listener => { syncNetwork = listener; return () => { removed++ } } }),
  reason => { syncReasons.push(reason) },
  { setInterval: (listener, ms) => { assert(ms === 60_000, 'fallback interval must be 60 seconds'); tick = listener; return 1 }, clearInterval: () => { cleared++ } },
)
assert(syncReasons.join(',') === 'android-startup', 'Android startup must synchronize once')
tick(); syncApp(false); tick(); syncApp(true); syncNetwork(true)
assert(syncReasons.join(',') === 'android-startup,android-foreground-fallback,android-foreground,android-network-online', 'foreground, online and foreground-only fallback must synchronize')
removeSync(); syncApp(true); syncNetwork(true); tick()
assert(cleared >= 1 && syncReasons.length === 4, 'background and cleanup must stop polling and unsubscribe')

let coalescedApp = (_active: boolean) => {}; let coalescedNetwork = (_online: boolean) => {}; let coalescedTick = () => {}
let releaseSync!: () => void; const coalescedReasons: string[] = []
const removeCoalesced = installAndroidSyncLifecycle(
  createLifecycleService({ onAppState: listener => { coalescedApp = listener; return () => {} } }),
  createLifecycleService({ onNetworkState: listener => { coalescedNetwork = listener; return () => {} } }),
  reason => { coalescedReasons.push(reason); return new Promise<void>(resolve => { releaseSync = resolve }) },
  { setInterval: listener => { coalescedTick = listener; return 2 }, clearInterval: () => {} },
)
coalescedTick(); coalescedApp(true); coalescedNetwork(true)
assert(coalescedReasons.join(',') === 'android-startup', 'concurrent lifecycle triggers must share one active sync')
releaseSync(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
assert(coalescedReasons.join(',') === 'android-startup,android-network-online', 'concurrent triggers must retain at most one trailing sync')
removeCoalesced()
const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const bootstrap = fs.readFileSync(new URL('../bootstrap.ts', import.meta.url), 'utf8') as string
assert(bootstrap.indexOf('installAndroidTimerWidgetLifecycle(') < bootstrap.indexOf('await loadSecureCredentialView('), 'widget recovery must install before credentials can fail')
assert(!bootstrap.includes('consumeRegisteredTimerWidgetJournal()'), 'bootstrap must never replay old native timer commands')
assert(bootstrap.includes('createCapacitorNetworkLifecycleService(runtime)'), 'bootstrap must register Android network lifecycle')
assert(bootstrap.includes('installAndroidSyncLifecycle('), 'bootstrap must install the bounded sync lifecycle')
console.log('platform lifecycle tests passed')
