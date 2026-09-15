export type SavedSessionVerification = 'checking' | 'connected' | 'network_failed' | 'unauthorized'
export type ActiveSessionVerification = 'valid' | 'invalid' | 'unavailable'
export type SavedSessionState = {
  authenticated: boolean
  clearToken: boolean
  mode: 'login' | 'restored' | 'connected' | 'offline' | 'expired'
}

export function resolveSavedSession(token: string, verification: SavedSessionVerification): SavedSessionState {
  if (!token) return { authenticated: false, clearToken: false, mode: 'login' }
  if (verification === 'unauthorized') return { authenticated: false, clearToken: true, mode: 'expired' }
  if (verification === 'connected') return { authenticated: true, clearToken: false, mode: 'connected' }
  return { authenticated: true, clearToken: false, mode: verification === 'network_failed' ? 'offline' : 'restored' }
}

export const verificationFromStatus = (status: number): SavedSessionVerification =>
  status === 200 ? 'connected' : status === 401 ? 'unauthorized' : 'network_failed'

export function resolveActiveSessionVerification(status: number, expectedUserId: string, actualUserId: unknown): ActiveSessionVerification {
  if (status === 401) return 'invalid'
  if (status !== 200) return 'unavailable'
  return String(actualUserId || '') === expectedUserId ? 'valid' : 'invalid'
}
