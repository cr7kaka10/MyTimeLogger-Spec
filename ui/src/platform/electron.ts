import type { DesktopCapabilities } from './services'

export interface ElectronApi {
  dbExecuteSync?: (sql: string, params?: any[]) => any
  dbQuerySync?: (sql: string, params?: any[]) => any
  ticktickFetch?: (url: string, options?: { method?: string; headers?: any; body?: any }) => Promise<any>
  reloadDb?: () => Promise<void> | void
  activateAccountDatabase?: (storageKey: string) => Promise<{ ok: boolean; error?: string }>
  reloadHotkeys?: () => Promise<void> | void
  openExternalUrl?: (url: string) => Promise<{ ok: boolean; error?: string }>
  onShortcutTrigger?: (handler: (event: any, payload: any) => void) => (() => void) | void
  writeTimerFlow?: (event: Record<string, any>) => void
  setTrayTooltip?: (text: string) => void
  minimizeWindow?: () => void
  closeWindow?: () => void
  encryptStringSync?: (text: string) => string
  decryptStringSync?: (encryptedText: string) => string
}

export const getElectronApi = (): ElectronApi | null => {
  if (typeof window === 'undefined') return null
  return ((window as any).electronAPI as ElectronApi | undefined) ?? null
}

export const isElectron = (): boolean => !!getElectronApi()

export interface ElectronCapabilities extends DesktopCapabilities {
  readonly database: boolean
  readonly nativeHttp: boolean
  readonly secureCredentials: boolean
  readonly externalBrowser: boolean
}

export const getElectronCapabilities = (api: ElectronApi | null = getElectronApi()): ElectronCapabilities => ({
  database: Boolean(api?.dbExecuteSync && api?.dbQuerySync),
  nativeHttp: Boolean(api?.ticktickFetch),
  secureCredentials: Boolean(api?.encryptStringSync && api?.decryptStringSync),
  externalBrowser: Boolean(api?.openExternalUrl),
  windowControls: Boolean(api?.minimizeWindow && api?.closeWindow),
  tray: Boolean(api?.setTrayTooltip),
  globalHotkeys: Boolean(api?.onShortcutTrigger && api?.reloadHotkeys),
})
