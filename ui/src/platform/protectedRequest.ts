import type { EnvironmentName } from '@core/EnvironmentProfiles'
import { platformFetch } from './fetch'

export type ProtectedRuntime = {
  environment: EnvironmentName
  serverUrl: string
  authToken: string
}

export const publishAuthExpired = (environment: EnvironmentName) => {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('mtl:auth-expired', { detail: { environment } }))
}

export const protectedPlatformFetch = async (
  runtime: ProtectedRuntime,
  path: string,
  init: RequestInit = {},
) => {
  const response = await platformFetch(`${runtime.serverUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${runtime.authToken}`,
      'X-Auth-Token': runtime.authToken,
      ...(init.headers || {}),
    },
  })
  if (response.status === 401) publishAuthExpired(runtime.environment)
  return response
}
