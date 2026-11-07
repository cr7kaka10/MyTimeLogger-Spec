import { readActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import { platformFetch } from './fetch'

type NativeBridge = { cacheWeek(raw: string): boolean; clear(): void }
const bridge = (): NativeBridge | undefined => (window as any).MorningMotivationBridge

export async function prefetchMorningMotivation(db: any, request = platformFetch, native = bridge()): Promise<boolean> {
  if (!native) return false
  const { serverUrl, authToken } = readActiveEnvironmentRuntimeConfig(db.getAllConfig?.() || {})
  if (!serverUrl || !authToken) return false
  try {
    const response = await request(`${serverUrl.replace(/\/+$/, '')}/api/morning-motivation/week`, {
      method: 'GET', headers: { Authorization: `Bearer ${authToken}` }, timeoutMs: 12_000,
    } as RequestInit)
    if (!response.ok) return false
    return native.cacheWeek(JSON.stringify(await response.json()))
  } catch { return false }
}
export const clearMorningMotivation = () => bridge()?.clear()
