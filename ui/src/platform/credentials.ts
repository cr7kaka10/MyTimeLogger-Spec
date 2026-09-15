import { SecureStorage } from '@aparajita/capacitor-secure-storage'
import { SENSITIVE_SETTINGS_KEYS } from '@core/SettingsConfigPortability'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'
import type { SecureCredentialsService } from './services'

export class MemoryCredentialView {
  private values = new Map<string, string>()

  async load(entries: Record<string, string | null | undefined>): Promise<void> {
    for (const [key, value] of Object.entries(entries)) {
      if (value) this.values.set(key, value)
      else this.values.delete(key)
    }
  }

  get(key: string): string | null { return this.values.get(key) ?? null }
  set(key: string, value: string): void { value ? this.values.set(key, value) : this.values.delete(key) }
}

type SecureStoragePort = Pick<typeof SecureStorage, 'getItem' | 'setItem' | 'removeItem'>
const secureKey = (key: string) => `mtl.credential.${key}`
const ACTIVE_ACCOUNT_STORAGE_KEY = 'active_account_storage_key'
const ACCOUNT_STORAGE_KEY_PATTERN = /^acct-[a-f0-9]{32}$/i

export function createSecureCredentialsService(runtime: PlatformRuntime = detectPlatformRuntime(), storage: SecureStoragePort = SecureStorage): SecureCredentialsService {
  const available = runtime === 'capacitor-android'
  return {
    available,
    async get(key) { return available ? storage.getItem(secureKey(key)) : null },
    async set(key, value) { if (available) await storage.setItem(secureKey(key), value) },
    async remove(key) { if (available) await storage.removeItem(secureKey(key)) },
  }
}

export const credentialView = new MemoryCredentialView()
let activeService: SecureCredentialsService | null = null
export const scopedCredentialKey = (namespace: string, key: string) => namespace ? `${namespace}:${key}` : key
export const isAccountStorageKey = (value: string | null | undefined): value is string => ACCOUNT_STORAGE_KEY_PATTERN.test(value || '')

export async function readActiveAccountStorageKey(): Promise<string | null> {
  if (!activeService?.available) return null
  const value = await activeService.get(ACTIVE_ACCOUNT_STORAGE_KEY)
  return isAccountStorageKey(value) ? value.toLowerCase() : null
}

export async function writeActiveAccountStorageKey(value: string): Promise<void> {
  if (!isAccountStorageKey(value)) throw new Error('invalid_account_storage_key')
  if (!activeService?.available) throw new Error('secure_credentials_unavailable')
  await activeService.set(ACTIVE_ACCOUNT_STORAGE_KEY, value.toLowerCase())
}

export async function clearActiveAccountStorageKey(): Promise<void> {
  if (!activeService?.available) throw new Error('secure_credentials_unavailable')
  await activeService.remove(ACTIVE_ACCOUNT_STORAGE_KEY)
}

export async function loadSecureCredentialView(service: SecureCredentialsService): Promise<void> {
  activeService = service
  if (!service.available) return
  const entries = await Promise.all(SENSITIVE_SETTINGS_KEYS.map(async key => [key, await service.get(key)] as const))
  await credentialView.load(Object.fromEntries(entries))
}

export async function setSecureCredential(key: string, value: string): Promise<void> {
  if (!activeService?.available) throw new Error('secure_credentials_unavailable')
  const previous = credentialView.get(key)
  credentialView.set(key, value)
  try {
    if (value) await activeService.set(key, value)
    else await activeService.remove(key)
  } catch (error) {
    credentialView.set(key, previous || '')
    throw error
  }
}

export async function loadScopedCredentialView(namespace: string): Promise<void> {
  if (!activeService?.available) return
  const entries = await Promise.all(SENSITIVE_SETTINGS_KEYS.map(async key => {
    const scoped = scopedCredentialKey(namespace, key)
    return [scoped, await activeService!.get(scoped)] as const
  }))
  await credentialView.load(Object.fromEntries(entries))
}
