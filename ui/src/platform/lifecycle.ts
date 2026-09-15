import { App } from '@capacitor/app'
import { Network } from '@capacitor/network'
import type { LifecycleEvent, LifecycleService } from './services'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'

type Cleanup = () => void | Promise<void>
export interface LifecycleSources {
  onAppState?(listener: (active: boolean) => void): Cleanup | Promise<Cleanup>
  onNetworkState?(listener: (online: boolean) => void): Cleanup | Promise<Cleanup>
}

type NativeApp = {
  addListener(event: 'appStateChange', listener: (state: { isActive: boolean }) => void):
    { remove(): void | Promise<void> } | Promise<{ remove(): void | Promise<void> }>
}

type NativeNetwork = {
  addListener(event: 'networkStatusChange', listener: (state: { connected: boolean }) => void):
    { remove(): void | Promise<void> } | Promise<{ remove(): void | Promise<void> }>
}

export function createCapacitorAppLifecycleService(runtime: PlatformRuntime = detectPlatformRuntime(), app: NativeApp = App): LifecycleService {
  if (runtime !== 'capacitor-android') return createLifecycleService(null)
  return createLifecycleService({ onAppState: listener => Promise.resolve(app.addListener('appStateChange', state => listener(state.isActive))).then(handle => () => handle.remove()) })
}

export function createCapacitorNetworkLifecycleService(runtime: PlatformRuntime = detectPlatformRuntime(), network: NativeNetwork = Network): LifecycleService {
  if (runtime !== 'capacitor-android') return createLifecycleService(null)
  return createLifecycleService({ onNetworkState: listener => Promise.resolve(network.addListener('networkStatusChange', state => listener(state.connected))).then(handle => () => handle.remove()) })
}

export function createLifecycleService(sources: LifecycleSources | null): LifecycleService {
  return {
    available: Boolean(sources),
    subscribe(listener: (event: LifecycleEvent) => void) {
      let closed = false
      let lastOnline: boolean | undefined
      const cleanups: Cleanup[] = []
      const attach = (value: Cleanup | Promise<Cleanup>) => {
        if (!(value instanceof Promise)) { cleanups.push(value); return }
        void value.then(async cleanup => { if (closed) await cleanup(); else cleanups.push(cleanup) })
      }
      if (sources?.onAppState) {
        attach(sources.onAppState(active => listener(active ? 'foreground' : 'background')))
      }
      if (sources?.onNetworkState) {
        attach(sources.onNetworkState(online => {
          if (online === lastOnline) return
          lastOnline = online; listener(online ? 'online' : 'offline')
        }))
      }
      return () => { closed = true; for (const cleanup of cleanups.splice(0)) void cleanup() }
    },
  }
}

export interface SyncLifecycleScheduler {
  setInterval(listener: () => void, milliseconds: number): unknown
  clearInterval(handle: unknown): void
}

const defaultSyncScheduler: SyncLifecycleScheduler = {
  setInterval: (listener, milliseconds) => globalThis.setInterval(listener, milliseconds),
  clearInterval: handle => globalThis.clearInterval(handle as number),
}

export function installAndroidSyncLifecycle(
  appLifecycle: LifecycleService,
  networkLifecycle: LifecycleService,
  synchronize: (reason: string) => void | Promise<unknown>,
  scheduler: SyncLifecycleScheduler = defaultSyncScheduler,
): () => void {
  if (!appLifecycle.available && !networkLifecycle.available) return () => {}
  let closed = false; let foreground = true; let interval: unknown
  let syncInFlight = false; let trailingReason: string | null = null
  const trigger = (reason: string) => {
    if (closed) return
    if (syncInFlight) { trailingReason = reason; return }
    try {
      const pending = synchronize(reason)
      if (!pending || typeof (pending as Promise<unknown>).then !== 'function') return
      syncInFlight = true
      void Promise.resolve(pending).catch(() => {}).finally(() => {
        syncInFlight = false
        const trailing = trailingReason; trailingReason = null
        if (trailing) trigger(trailing)
      })
    } catch { /* retry on next trigger */ }
  }
  const stopPolling = () => {
    if (interval !== undefined) scheduler.clearInterval(interval)
    interval = undefined
  }
  const startPolling = () => {
    stopPolling()
    if (foreground && !closed) interval = scheduler.setInterval(() => {
      if (foreground) trigger('android-foreground-fallback')
    }, 60_000)
  }
  trigger('android-startup'); startPolling()
  const removeApp = appLifecycle.subscribe(event => {
    if (event === 'background') { foreground = false; stopPolling(); return }
    if (event === 'foreground') { foreground = true; trigger('android-foreground'); startPolling() }
  })
  const removeNetwork = networkLifecycle.subscribe(event => {
    if (event === 'online') trigger('android-network-online')
  })
  return () => { if (!closed) { closed = true; stopPolling(); removeApp(); removeNetwork() } }
}

export function installAndroidTimerWidgetLifecycle(
  lifecycle: LifecycleService,
  refresh: () => void,
): () => void {
  if (!lifecycle.available) return () => {}
  let closed = false
  const unsubscribe = lifecycle.subscribe(event => {
    if (event !== 'foreground' || closed) return
    refresh()
  })
  return () => { if (!closed) { closed = true; unsubscribe() } }
}
