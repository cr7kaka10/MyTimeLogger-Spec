import { Browser } from '@capacitor/browser'
import { getElectronApi } from './electron'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'
import type { ExternalBrowserService } from './services'

type AndroidBrowser = { open(options: { url: string }): Promise<void> }

export function createExternalBrowserService(runtime: PlatformRuntime = detectPlatformRuntime(), androidBrowser: AndroidBrowser = Browser): ExternalBrowserService {
  const electronApi = getElectronApi()
  const available = runtime === 'capacitor-android' ? true : runtime === 'electron' ? Boolean(electronApi?.openExternalUrl) : typeof window !== 'undefined'
  return { available, async open(url) {
    if (runtime === 'capacitor-android') {
      await androidBrowser.open({ url }); return
    }
    if (runtime === 'electron') {
      const result = await electronApi?.openExternalUrl?.(url)
      if (!result?.ok) throw new Error(result?.error || 'ELECTRON_BROWSER_UNAVAILABLE')
      return
    }
    window.open(url, '_blank', 'noopener,noreferrer')
  } }
}
