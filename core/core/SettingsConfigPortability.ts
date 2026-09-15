import { readEnvironmentProfile } from './EnvironmentProfiles'
import { formatBeijingDateTime } from './BeijingTime'
import { isDeviceLocalSetting } from './SettingDefinitions'

export const SETTINGS_CONFIG_SCHEMA_VERSION = 1

export const SETTINGS_EXPORT_KEYS = [
  'theme', 'study_time_min', 'study_time_max', 'short_break_duration', 'long_break_duration', 'long_break_threshold',
  'input_output_countdown_min',
  'sync_interval', 'sleep_sync_interval', 'statistics_start_date', 'checklist_sync_start_date',
  'ai_text_model', 'ai_text_endpoint', 'ai_vision_model', 'ai_vision_endpoint',
  'shortcut_toggle_timer', 'shortcut_minimize', 'music_folder',
  'ledger_format_habit_success', 'ledger_format_habit_makeup', 'ledger_format_habit_fail',
  'ledger_format_task_success', 'ledger_format_task_fail',
  'active_environment',
  'env_development_server_url', 'env_development_username',
  'env_testing_server_url', 'env_testing_username',
  'env_production_server_url', 'env_production_username',
  'env_development_webdav_backup_draft', 'env_testing_webdav_backup_draft', 'env_production_webdav_backup_draft',
  'env_development_logging_config_draft', 'env_testing_logging_config_draft', 'env_production_logging_config_draft',
]

export const SENSITIVE_SETTINGS_KEYS = [
  'atimelogger_password',
  'atimelogger_token',
  'atimelogger_refresh_token',
  'ai_text_api_key',
  'ai_vision_api_key',
  'env_development_auth_token',
  'env_testing_auth_token',
  'env_production_auth_token',
]

export const buildSettingsConfigPayload = (cfg: Record<string, any>) => ({
  schemaVersion: SETTINGS_CONFIG_SCHEMA_VERSION,
  exportedAt: formatBeijingDateTime(),
  settings: Object.fromEntries(SETTINGS_EXPORT_KEYS.filter(key => cfg[key] !== undefined && !isDeviceLocalSetting(key)).map(key => [key, cfg[key]])),
  environmentProfiles: Object.fromEntries(
    (['development', 'testing', 'production'] as const).map(environment => {
      const profile = readEnvironmentProfile(cfg, environment)
      return [environment, { serverUrl: profile.serverUrl, username: profile.username }]
    }),
  ),
})

export const parseSettingsConfigPayload = (payload: any): Record<string, string> => {
  if (typeof payload !== 'object' || payload === null) throw new Error('无效的 JSON 格式')
  if (payload.schemaVersion !== SETTINGS_CONFIG_SCHEMA_VERSION || typeof payload.settings !== 'object' || payload.settings === null) {
    throw new Error('不支持的配置文件版本')
  }
  const entries = Object.entries(payload.settings).filter(([key]) => SETTINGS_EXPORT_KEYS.includes(key) && !isDeviceLocalSetting(key))
  if (entries.length === 0) throw new Error('配置文件没有可导入的设置项')
  return Object.fromEntries(entries.map(([key, value]) => [key, String(value)]))
}
