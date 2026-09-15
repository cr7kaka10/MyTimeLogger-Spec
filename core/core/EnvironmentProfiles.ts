export type EnvironmentName = 'development' | 'testing' | 'production'
export const ENVIRONMENTS: EnvironmentName[] = ['development', 'testing', 'production']
export type ProfileConnectionStatus = 'unconfigured' | 'inactive' | 'checking' | 'connected' | 'unauthorized' | 'disconnected'
export type NetworkConnectionStatus = Exclude<ProfileConnectionStatus, 'unconfigured' | 'inactive'>
export const LOCAL_DEVELOPMENT_SERVER_URL = 'http://127.0.0.1:8000'
const LEGACY_LOCAL_DEVELOPMENT_SERVER_URL = 'http://127.0.0.1:18010'

export const environmentKey = (environment: EnvironmentName, field: 'server_url' | 'username' | 'auth_token' | 'verified_user_id') =>
  `env_${environment}_${field}`

const legacyEnvironmentValue = (
  cfg: Record<string, string>,
  environment: EnvironmentName,
  field: 'server_url' | 'username' | 'auth_token',
): string => {
  const legacyKeys = [
    `${environment}_${field}`,
    `${environment === 'testing' ? 'test' : environment}_${field}`,
    `${environment}_server_${field}`,
    `${environment === 'testing' ? 'test' : environment}_server_${field}`,
  ]
  for (const key of legacyKeys) {
    if (cfg[key]) return cfg[key]
  }
  return ''
}

export function migrateEnvironmentConfig(cfg: Record<string, string>): Record<string, string> {
  const writes: Record<string, string> = {}
  if (!cfg.active_environment) writes.active_environment = 'development'

  const defaults: Record<EnvironmentName, Partial<Record<'server_url' | 'username' | 'auth_token', string>>> = {
    development: {
      server_url: cfg.server_url || LOCAL_DEVELOPMENT_SERVER_URL,
      username: cfg.server_username || '',
      auth_token: cfg.auth_token || '',
    },
    testing: {},
    production: {},
  }

  for (const environment of ENVIRONMENTS) {
    for (const field of ['server_url', 'username', 'auth_token'] as const) {
      const key = environmentKey(environment, field)
      if (cfg[key]) continue
      const value = defaults[environment][field] || legacyEnvironmentValue(cfg, environment, field)
      if (value) writes[key] = value
    }
  }

  const developmentUrlKey = environmentKey('development', 'server_url')
  const developmentUrl = cfg[developmentUrlKey] || defaults.development.server_url || ''
  if (developmentUrl.trim().replace(/\/+$/, '').toLowerCase() === LEGACY_LOCAL_DEVELOPMENT_SERVER_URL) {
    writes[developmentUrlKey] = LOCAL_DEVELOPMENT_SERVER_URL
  }

  return writes
}

export function androidSmokeResidueWrites(cfg: Record<string, string>): Record<string, string> {
  const urlKey = environmentKey('development', 'server_url')
  const usernameKey = environmentKey('development', 'username')
  const tokenKey = environmentKey('development', 'auth_token')
  const url = (cfg[urlKey] || cfg.server_url || '').trim().replace(/\/+$/, '').toLowerCase()
  const username = cfg[usernameKey] || cfg.server_username || ''
  if (url !== LEGACY_LOCAL_DEVELOPMENT_SERVER_URL || !/^android_smoke_[0-9]{8}$/.test(username)) return {}
  return { [usernameKey]: '', [tokenKey]: '' }
}

export function readEnvironmentProfile(cfg: Record<string, string>, environment: EnvironmentName) {
  return {
    serverUrl: cfg[environmentKey(environment, 'server_url')] || '',
    username: cfg[environmentKey(environment, 'username')] || '',
    authToken: cfg[environmentKey(environment, 'auth_token')] || '',
    verifiedUserId: cfg[environmentKey(environment, 'verified_user_id')] || '',
  }
}

export function readActiveEnvironmentRuntimeConfig(cfg: Record<string, string>) {
  const active = ENVIRONMENTS.includes(cfg.active_environment as EnvironmentName)
    ? cfg.active_environment as EnvironmentName
    : 'development'
  const profile = readEnvironmentProfile(cfg, active)
  return {
    environment: active,
    serverUrl: profile.serverUrl || '',
    authToken: profile.authToken || '',
  }
}

export function requireActiveEnvironmentRuntimeConfig(cfg: Record<string, string>, source = 'runtime') {
  const runtime = readActiveEnvironmentRuntimeConfig(cfg)
  const missing = [
    runtime.serverUrl.trim() ? '' : 'server_url',
    runtime.authToken.trim() ? '' : 'auth_token',
  ].filter(Boolean)
  if (missing.length) {
    const message = `${runtime.environment} 环境缺少${missing.join('、')}，请先在设置中配置并登录当前环境`
    console.error('[EnvironmentProfiles] active environment runtime config missing', {
      source,
      environment: runtime.environment,
      missing,
    })
    throw new Error(message)
  }
  return runtime
}

export function deriveProfileConnectionStatus(
  profile: { serverUrl: string; authToken: string; verifiedUserId?: string },
  isActive: boolean,
  networkStatus: NetworkConnectionStatus = 'disconnected',
): ProfileConnectionStatus {
  if (!profile.serverUrl.trim() || !profile.authToken.trim() || !profile.verifiedUserId?.trim()) return 'unconfigured'
  if (!isActive) return 'inactive'
  return networkStatus
}

export function environmentActivationWrites(environment: EnvironmentName, profile: { serverUrl: string; authToken: string }) {
  if (!profile.serverUrl || !profile.authToken) throw new Error(`${environment} 环境尚未配置地址或 Token`)
  return { active_environment: environment }
}
