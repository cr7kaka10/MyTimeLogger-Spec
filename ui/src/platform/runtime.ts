export type PlatformRuntime = 'electron' | 'capacitor-android' | 'web'

export interface RuntimeHost {
  electronAPI?: unknown
  Capacitor?: {
    getPlatform?: () => string
    isNativePlatform?: () => boolean
  }
}

export function detectPlatformRuntime(host: RuntimeHost | undefined = typeof window === 'undefined' ? undefined : window as RuntimeHost): PlatformRuntime {
  if (host?.electronAPI) return 'electron'
  const capacitor = host?.Capacitor
  if (capacitor?.getPlatform?.() === 'android' && capacitor.isNativePlatform?.() !== false) {
    return 'capacitor-android'
  }
  return 'web'
}
