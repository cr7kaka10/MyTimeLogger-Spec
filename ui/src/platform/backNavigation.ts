import { detectPlatformRuntime, type PlatformRuntime } from './runtime'
import type { BackNavigationService } from './services'

type NativeApp = { addListener(event: 'backButton', listener: () => void): Promise<{ remove(): void | Promise<void> }> | { remove(): void | Promise<void> }; exitApp(): void | Promise<void> }

const getNativeApp = (): NativeApp | null => (typeof window === 'undefined' ? null : (window as any).Capacitor?.Plugins?.App ?? null)

export const runBackNavigation = (closeOverlay: () => boolean, previousTab: () => boolean): boolean => closeOverlay() || previousTab()

export function createBackNavigationService(runtime: PlatformRuntime = detectPlatformRuntime(), app: NativeApp | null = getNativeApp()): BackNavigationService {
  const available = runtime === 'capacitor-android' && Boolean(app)
  return { available, subscribe(handler) {
    if (!available || !app) return () => {}
    let closed = false
    let remove = () => {}
    void Promise.resolve(app.addListener('backButton', () => { if (!handler()) void app.exitApp() }))
      .then(handle => { if (closed) void handle.remove(); else remove = () => { void handle.remove() } })
    return () => { closed = true; remove() }
  } }
}
