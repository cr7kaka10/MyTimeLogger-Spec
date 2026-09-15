export type SettingScope = 'syncable' | 'device-local'

const deviceLocalPatterns = [
  /(?:password|token|api_key|refresh_token)$/,
  /^env_(?:development|testing|production)_auth_token$/,
]

export const getSettingScope = (key: string): SettingScope =>
  deviceLocalPatterns.some(pattern => pattern.test(key)) ? 'device-local' : 'syncable'

export const isDeviceLocalSetting = (key: string): boolean => getSettingScope(key) === 'device-local'
