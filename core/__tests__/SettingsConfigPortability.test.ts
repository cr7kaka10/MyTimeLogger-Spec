import { describe, expect, it } from 'vitest'
import { buildSettingsConfigPayload, parseSettingsConfigPayload } from '../core/SettingsConfigPortability'
import { isDeviceLocalSetting } from '../core/SettingDefinitions'

describe('SettingsConfigPortability', () => {
  it('将凭据定义为设备本地设置', () => {
    expect(isDeviceLocalSetting('atimelogger_password')).toBe(true)
    expect(isDeviceLocalSetting('ai_text_api_key')).toBe(true)
    expect(isDeviceLocalSetting('env_production_auth_token')).toBe(true)
    expect(isDeviceLocalSetting('theme')).toBe(false)
  })
  it('导出版本化配置且排除业务流水字段', () => {
    const payload = buildSettingsConfigPayload({
      theme: 'dark',
      input_output_countdown_min: '120',
      long_break_duration: '60',
      checklist_sync_start_date: '2026-07-01',
      ai_text_model: 'glm-test',
      ai_text_api_key: 'secret-text-key',
      atimelogger_password: 'secret-password',
      atimelogger_token: 'secret-token',
      atimelogger_enabled: 'true',
      atimelogger_type_map: '{"娱乐":"remote-id"}',
      env_development_server_url: 'http://127.0.0.1:8000',
      env_development_auth_token: 'secret-session-token',
      reward_ledger: 'should-not-export',
      study_sessions: 'should-not-export',
    })

    expect(payload.schemaVersion).toBe(1)
    expect(payload.settings.theme).toBe('dark')
    expect(payload.settings.input_output_countdown_min).toBe('120')
    expect(payload.settings.long_break_duration).toBe('60')
    expect(payload.settings.checklist_sync_start_date).toBe('2026-07-01')
    expect(payload.settings.ai_text_model).toBe('glm-test')
    expect(payload.settings.ai_text_api_key).toBeUndefined()
    expect(payload.settings.atimelogger_password).toBeUndefined()
    expect(payload.settings.atimelogger_token).toBeUndefined()
    expect(payload.settings.atimelogger_enabled).toBeUndefined()
    expect(payload.settings.atimelogger_type_map).toBeUndefined()
    expect(payload.settings.env_development_auth_token).toBeUndefined()
    expect(payload.settings.reward_ledger).toBeUndefined()
    expect(payload.settings.study_sessions).toBeUndefined()
    expect(payload.environmentProfiles.development.serverUrl).toBe('http://127.0.0.1:8000')
    expect((payload.environmentProfiles.development as any).authToken).toBeUndefined()
  })

  it('导入时只接受支持版本和白名单字段', () => {
    const parsed = parseSettingsConfigPayload({
      schemaVersion: 1,
      settings: {
        theme: 'light',
        input_output_countdown_min: '3600',
        long_break_duration: '300',
        checklist_sync_start_date: '2026-07-01',
        ai_text_api_key: 'secret',
        study_sessions: 'blocked',
      },
    })

    expect(parsed).toEqual({
      theme: 'light',
      input_output_countdown_min: '3600',
      long_break_duration: '300',
      checklist_sync_start_date: '2026-07-01',
    })
  })

  it('非法版本导入失败且不会返回部分设置', () => {
    expect(() => parseSettingsConfigPayload({ schemaVersion: 999, settings: { theme: 'dark' } })).toThrow('不支持')
  })
})
