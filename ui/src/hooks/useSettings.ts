// ui/src/hooks/useSettings.ts
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { SystemSettings } from '../types'
import { activateAccountStorage, getDatabase, refreshSyncConfiguration } from '../db'
import { createAccountIdentity } from '@core/AccountIdentity'
import { androidSmokeResidueWrites, deriveProfileConnectionStatus, environmentActivationWrites, environmentKey, migrateEnvironmentConfig, readEnvironmentProfile, type EnvironmentName, type NetworkConnectionStatus, type ProfileConnectionStatus } from '@core/EnvironmentProfiles'
import { buildSettingsConfigPayload, parseSettingsConfigPayload } from '@core/SettingsConfigPortability'
import { DEFAULT_INPUT_OUTPUT_COUNTDOWN_MINUTES, DEFAULT_LONG_BREAK_MINUTES, resolveInputOutputCountdownMinutes, resolveLongBreakMinutes } from '@core/TimerSettings'
import { DEFAULT_STATISTICS_START_DATE, resolveStatisticsStartDate } from '@core/ChecklistSyncStartDate'
import { getElectronApi, platformFetch } from '../platform'
import { shareTextFile } from '../platform/fileShare'
import { detectPlatformRuntime } from '../platform/runtime'
import { clearActiveAccountStorageKey, setSecureCredential, writeActiveAccountStorageKey } from '../platform/credentials'
import { formatPlatformNetworkError } from '../platform/fetch'
import { clearTimerWidgetRuntime, configureTimerWidgetRuntime } from '../platform/timerWidget'
import { resolveActiveSessionVerification, type ActiveSessionVerification } from '../auth/sessionState'
import {
  AUDIO_SETTING_DEFAULTS,
  audioConfigFromSettings,
  normalizeAudioSettingValue,
  syncAudioConfig,
} from '../utils/audio'
import { millisecondsUntilAndroidThemeBoundary, nextAndroidThemeBoundaryAt, resolveAndroidTheme, type AndroidThemeOverride } from '../utils/androidScheduledTheme'

export const formatSettingsNetworkError = formatPlatformNetworkError

const provisionTimerWidgetRuntime = (db: any, profile: { serverUrl: string, authToken: string, verifiedUserId: string }) => {
  if (detectPlatformRuntime() !== 'capacitor-android') return
  if (!profile.serverUrl || !profile.authToken || !profile.verifiedUserId) { clearTimerWidgetRuntime(); return }
  let deviceId = db.getConfig('device_id')
  if (!deviceId) { deviceId = `mtl-${crypto.randomUUID()}`; db.setConfig('device_id', deviceId) }
  configureTimerWidgetRuntime({ ...profile, deviceId, generation: Date.now() })
}

export const safeFetch = async (url: string, options?: any, timeout = 3000): Promise<{ ok: boolean; status: number; text: () => Promise<string>; json: () => Promise<any> }> => {
  let timeoutId: ReturnType<typeof setTimeout> | undefined
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => reject(new DOMException('Aborted', 'AbortError')), timeout)
  })
  try {
    return await Promise.race([platformFetch(url, { ...options, timeoutMs: timeout } as any), timeoutPromise])
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }
}

export interface UseSettingsReturn {

  settings: SystemSettings
  theme: 'light' | 'dark'
  updateSetting: (key: string, value: string | number | boolean) => Promise<{ ok: boolean; error?: string }>
  toggleTheme: () => void
  syncNow: () => void
  syncStatus: 'idle' | 'syncing' | 'error'
  exportConfig: () => void
  importConfig: () => void
  connectionStatus: ProfileConnectionStatus
  profileReady: boolean
  testConnection: (customUrl?: string, customToken?: string, environment?: EnvironmentName) => Promise<{ success: boolean; error?: string }>
  verifyActiveSession: () => Promise<ActiveSessionVerification>
  loginEnvironment: (username: string, password: string, environment?: EnvironmentName) => Promise<{ success: boolean; error?: string }>
  clearActiveSession: () => Promise<void>
  logoutActiveSession: () => Promise<void>
  activeEnvironment: EnvironmentName
  switchEnvironment: (environment: EnvironmentName) => Promise<{ success: boolean; error?: string }>
  selectedEnvironment: EnvironmentName
  selectedEnvironmentProfile: { serverUrl: string; username: string; authToken: string; verifiedUserId: string }
  selectEnvironment: (environment: EnvironmentName) => void
  updateEnvironmentSetting: (field: 'server_url' | 'username', value: string, environment?: EnvironmentName) => Promise<void>
}


const defaultSettings: SystemSettings = {
  server_url: '',
  auth_token: '',
  study_time_min: 25,
  study_time_max: 90,
  short_break_duration: 5,
  long_break_duration: DEFAULT_LONG_BREAK_MINUTES,
  long_break_threshold: 90,
  input_output_countdown_min: DEFAULT_INPUT_OUTPUT_COUNTDOWN_MINUTES,
  sync_interval: 15,
  statistics_start_date: DEFAULT_STATISTICS_START_DATE,
  last_sync_at: '—',
  atimelogger_enabled: false,
  atimelogger_username: '',
  atimelogger_password: '',
  atimelogger_owner_username: '',
  atimelogger_token: '',
  atimelogger_refresh_token: '',
  atimelogger_device_id: '',
  atimelogger_auth_required: false,
  atimelogger_type_map: '{}',
  atimelogger_unmatched_categories: '[]',
  sleep_sync_enabled: true,
  sleep_sync_interval: 30,
  ai_text_model: '',
  ai_text_api_key: '',
  ai_text_endpoint: '',
  ai_vision_model: '',
  ai_vision_api_key: '',
  ai_vision_endpoint: '',
  shortcut_toggle_timer: 'Alt+C',
  shortcut_minimize: 'Alt+Z',
  music_folder: 'assets/audio',
  ...AUDIO_SETTING_DEFAULTS,
  ledger_format_habit_success: '√ 习惯 {icon}{title}',
  ledger_format_habit_makeup: '√ 习惯 {icon}[补]{title}',
  ledger_format_habit_fail: '× 习惯 {icon}{title}',
  ledger_format_task_success: '√ 任务 {title}',
  ledger_format_task_fail: '× 任务 {title}',
}

const configNumber = (cfg: Record<string, any>, key: string, fallback: number): number => {
  const value = cfg[key]
  if (value === undefined || value === null || value === '') return fallback
  return Number(value)
}

export const studySecondsToMinutes = (value: unknown, fallbackSeconds: number): number => {
  const seconds = Number(value)
  return (Number.isFinite(seconds) ? seconds : fallbackSeconds) / 60
}

export const minutesToStoredSeconds = (value: string | number): string => String(Number(value) * 60)

const bundledEnvironmentDefaults = () => {
  const env = (import.meta as any).env || {}
  const active = env.VITE_MTL_DEFAULT_ENVIRONMENT as EnvironmentName | undefined
  const writes: Record<string, string> = {}
  if (active && ['development', 'testing', 'production'].includes(active)) writes.active_environment = active
  const developmentUrl = env.VITE_MTL_DEVELOPMENT_SERVER_URL
  if (developmentUrl) writes[environmentKey('development', 'server_url')] = developmentUrl
  return writes
}

const HOTKEY_SETTING_KEYS = new Set(['shortcut_toggle_timer', 'shortcut_minimize'])
export const shouldReloadHotkeysForSetting = (key: string): boolean => HOTKEY_SETTING_KEYS.has(key)

export const useSettings = (): UseSettingsReturn => {
  const [settings, setSettings] = useState<SystemSettings>(defaultSettings)
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [connectionStatuses, setConnectionStatuses] = useState<Record<EnvironmentName, NetworkConnectionStatus>>({ development: 'disconnected', testing: 'disconnected', production: 'disconnected' })
  const [activeEnvironment, setActiveEnvironment] = useState<EnvironmentName>('development')
  const [selectedEnvironment, setSelectedEnvironment] = useState<EnvironmentName>('development')
  const [selectedEnvironmentProfile, setSelectedEnvironmentProfile] = useState({ serverUrl: '', username: '', authToken: '', verifiedUserId: '' })
  const [profileReady, setProfileReady] = useState(false)
  const environmentInitialized = useRef(false)
  const connectionRequestIds = useRef<Record<EnvironmentName, number>>({ development: 0, testing: 0, production: 0 })
  const androidThemeOverrideRef = useRef<AndroidThemeOverride | null>(null)

  useEffect(() => {
    if (!profileReady || detectPlatformRuntime() !== 'capacitor-android') return
    let timeout: ReturnType<typeof setTimeout> | undefined
    const apply = () => {
      const now = new Date()
      const resolved = resolveAndroidTheme(androidThemeOverrideRef.current, now)
      if (!resolved.usesOverride) androidThemeOverrideRef.current = null
      setTheme(resolved.theme)
      document.documentElement.classList.toggle('dark', resolved.theme === 'dark')
      const delay = resolved.usesOverride
        ? Math.max(1_000, androidThemeOverrideRef.current!.expiresAt - now.getTime())
        : millisecondsUntilAndroidThemeBoundary(now)
      timeout = setTimeout(apply, delay)
    }
    const onVisibilityChange = () => { if (!document.hidden) { if (timeout) clearTimeout(timeout); apply() } }
    const onWindowFocus = () => { if (timeout) clearTimeout(timeout); apply() }
    apply(); document.addEventListener('visibilitychange', onVisibilityChange); window.addEventListener('focus', onWindowFocus)
    return () => {
      if (timeout) clearTimeout(timeout)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('focus', onWindowFocus)
    }
  }, [profileReady, settings])

  const applyImportedLoggingConfig = useCallback(async (cfg: Record<string, string>, environment: EnvironmentName) => {
    const rawDraft = cfg[`env_${environment}_logging_config_draft`]
    if (!rawDraft) return
    const profile = readEnvironmentProfile(cfg, environment)
    const token = profile.authToken
    let url = profile.serverUrl.trim()
    if (!url || !token) return
    if (!url.startsWith('http://') && !url.startsWith('https://')) url = `http://${url}`
    const loggingConfig = JSON.parse(rawDraft)
    const response = await safeFetch(`${url.replace(/\/$/, '')}/admin/logging/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(loggingConfig),
    }, 5000)
    if (!response.ok) {
      const text = await response.text().catch(() => '')
      throw new Error(`服务端返回错误 (${response.status}): ${text}`)
    }
  }, [])

  const testConnection = useCallback(async (customUrl?: string, customToken?: string, environment: EnvironmentName = 'development'): Promise<{ success: boolean; error?: string }> => {
    const requestId = ++connectionRequestIds.current[environment]
    const setTargetStatus = (status: NetworkConnectionStatus) => {
      if (connectionRequestIds.current[environment] === requestId) setConnectionStatuses(prev => ({ ...prev, [environment]: status }))
    }
    setTargetStatus('checking')
    try {
      const db = await getDatabase()
      const profile = readEnvironmentProfile(db.getAllConfig(), environment)
      const url = (customUrl !== undefined ? customUrl : profile.serverUrl) || ''
      const token = (customToken !== undefined ? customToken : profile.authToken) || ''

      if (!url) {
        setTargetStatus('disconnected')
        return { success: false, error: '未配置服务端地址' }
      }

      let cleanUrl = url.trim()
      if (!cleanUrl.startsWith('http://') && !cleanUrl.startsWith('https://')) {
        cleanUrl = `http://${cleanUrl}`
      }

      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (token) {
          headers['Authorization'] = `Bearer ${token}`
        }

        const resp = await safeFetch(`${cleanUrl}/auth/me`, {
          method: 'GET',
          headers
        }, 3000)

        if (resp.status === 200) {
          const body = await resp.json().catch(() => null)
          if (String(body?.user?.id || '') !== String(profile.verifiedUserId || '')) {
            setTargetStatus('unauthorized')
            return { success: false, error: '已验证账号身份不匹配，请重新登录' }
          }
          setTargetStatus('connected')
          return { success: true }
        } else if (resp.status === 401) {
          setTargetStatus('unauthorized')
          return { success: false, error: '登录已失效，请重新登录' }
        } else {
          const text = await resp.text().catch(() => '')
          setTargetStatus('disconnected')
          return { success: false, error: `服务端返回错误 (${resp.status}): ${text}` }
        }
      } catch (fetchErr: any) {
        setTargetStatus('disconnected')
        return { success: false, error: formatSettingsNetworkError(fetchErr) }
      }
    } catch (err: any) {
      setTargetStatus('disconnected')
      return { success: false, error: `测试连接失败: ${err.message}` }
    }
  }, [])

  const verifyActiveSession = useCallback(async (): Promise<ActiveSessionVerification> => {
    const db = await getDatabase()
    const profile = readEnvironmentProfile(db.getAllConfig(), activeEnvironment)
    const url = profile.serverUrl.trim().replace(/\/$/, '')
    if (!url || !profile.authToken || !profile.verifiedUserId) return 'unavailable'
    try {
      const response = await safeFetch(`${url}/auth/me`, {
        method: 'GET', headers: { Authorization: `Bearer ${profile.authToken}` },
      }, 5000)
      const body = await response.json().catch(() => null)
      const result = resolveActiveSessionVerification(response.status, profile.verifiedUserId, body?.user?.id)
      setConnectionStatuses(previous => ({ ...previous, [activeEnvironment]: result === 'valid' ? 'connected' : result === 'invalid' ? 'unauthorized' : 'disconnected' }))
      return result
    } catch {
      setConnectionStatuses(previous => ({ ...previous, [activeEnvironment]: 'disconnected' }))
      return 'unavailable'
    }
  }, [activeEnvironment])

  const loginEnvironment = useCallback(async (username: string, password: string, environment: EnvironmentName = selectedEnvironment) => {
    let db = await getDatabase()
    const profile = readEnvironmentProfile(db.getAllConfig(), environment)
    let url = profile.serverUrl.trim()
    if (!url || !username.trim() || !password) return { success: false, error: '请填写服务端地址、账号和密码' }
    if (!url.startsWith('http://') && !url.startsWith('https://')) url = `http://${url}`
    setConnectionStatuses(prev => ({ ...prev, [environment]: 'checking' }))
    try {
      const response = await safeFetch(`${url}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: username.trim(), password }) }, 5000)
      const body = await response.json()
      if (response.status === 401) {
        setConnectionStatuses(prev => ({ ...prev, [environment]: 'unauthorized' }))
        return { success: false, error: '账号或密码错误' }
      }
      if (!response.ok || !body?.token) {
        setConnectionStatuses(prev => ({ ...prev, [environment]: 'disconnected' }))
        return { success: false, error: body?.detail || `登录失败 (${response.status})` }
      }
      const verified = await safeFetch(`${url}/auth/me`, {
        method: 'GET', headers: { Authorization: `Bearer ${body.token}` },
      }, 5000)
      const verifiedBody = await verified.json().catch(() => null)
      const userId = Number(verifiedBody?.user?.id)
      if (!verified.ok || !Number.isSafeInteger(userId) || userId <= 0) {
        setConnectionStatuses(prev => ({ ...prev, [environment]: 'unauthorized' }))
        return { success: false, error: '账号身份确认失败，请重新登录' }
      }
      db = await activateAccountStorage(createAccountIdentity(url, userId))
      db.setConfig(environmentKey(environment, 'server_url'), url)
      db.setConfig('active_environment', environment)
      db.setConfig(environmentKey(environment, 'username'), username.trim())
      db.setConfig(environmentKey(environment, 'verified_user_id'), String(userId))
      const tokenKey = environmentKey(environment, 'auth_token')
      if (detectPlatformRuntime() === 'capacitor-android') {
        try {
          if (typeof (db as any).setSecureConfig === 'function') await (db as any).setSecureConfig(tokenKey, body.token)
          else await setSecureCredential(tokenKey, body.token)
          await writeActiveAccountStorageKey(createAccountIdentity(url, userId).storageKey)
        } catch { throw new Error('secure_credentials_write_failed') }
      }
      else db.setConfig(tokenKey, body.token)
      provisionTimerWidgetRuntime(db, { serverUrl: url, authToken: body.token, verifiedUserId: String(userId) })
      if (environment === activeEnvironment) await refreshSyncConfiguration(db)
      setSelectedEnvironmentProfile({ serverUrl: url, username: username.trim(), authToken: body.token, verifiedUserId: String(userId) })
      setConnectionStatuses(prev => ({ ...prev, [environment]: 'connected' }))
      return { success: true, activated: true }
    } catch (error: any) {
      setConnectionStatuses(prev => ({ ...prev, [environment]: 'disconnected' }))
      return { success: false, error: error?.message === 'secure_credentials_write_failed'
        ? '安全凭据保存失败，登录状态未提交' : formatSettingsNetworkError(error) }
    }
  }, [activeEnvironment, selectedEnvironment])

  const clearActiveSession = useCallback(async () => {
    const db = await getDatabase(); const tokenKey = environmentKey(activeEnvironment, 'auth_token')
    if (detectPlatformRuntime() === 'capacitor-android') {
      if (typeof (db as any).setSecureConfig === 'function') await (db as any).setSecureConfig(tokenKey, '')
      else await setSecureCredential(tokenKey, '')
      await clearActiveAccountStorageKey()
      clearTimerWidgetRuntime()
    } else db.setConfig(tokenKey, '')
    db.setConfig(environmentKey(activeEnvironment, 'username'), '')
    db.setConfig(environmentKey(activeEnvironment, 'verified_user_id'), '')
    await refreshSyncConfiguration(db)
    if (selectedEnvironment === activeEnvironment) setSelectedEnvironmentProfile(previous => ({ ...previous, authToken: '', username: '', verifiedUserId: '' }))
    setConnectionStatuses(previous => ({ ...previous, [activeEnvironment]: 'unauthorized' }))
  }, [activeEnvironment, selectedEnvironment])

  const logoutActiveSession = useCallback(async () => {
    const db = await getDatabase()
    const profile = readEnvironmentProfile(db.getAllConfig(), activeEnvironment)
    const url = profile.serverUrl.trim().replace(/\/$/, '')
    try {
      if (url && profile.authToken) {
        await safeFetch(`${url}/auth/logout`, {
          method: 'POST', headers: { Authorization: `Bearer ${profile.authToken}` },
        }, 5000)
      }
    } catch {
      // The user explicitly signed out, so local credentials must be removed even while offline.
    } finally {
      await clearActiveSession()
    }
  }, [activeEnvironment, clearActiveSession])

  useEffect(() => {
    getDatabase().then(async db => {
      const cfg = db.getAllConfig()
      const migration = migrateEnvironmentConfig(cfg)
      const smokeResidue = detectPlatformRuntime() === 'capacitor-android' ? androidSmokeResidueWrites(cfg) : {}
      Object.assign(migration, smokeResidue)
      const developmentTokenKey = environmentKey('development', 'auth_token')
      if (Object.prototype.hasOwnProperty.call(smokeResidue, developmentTokenKey)) {
        await setSecureCredential(developmentTokenKey, '')
      }
      const bundledDefaults = bundledEnvironmentDefaults()
      Object.entries(bundledDefaults).forEach(([key, value]) => {
        if (value && !cfg[key]) migration[key] = value
      })
      Object.entries(migration).forEach(([key, value]) => { db.setConfig(key, value); cfg[key] = value })
      setActiveEnvironment(cfg.active_environment as EnvironmentName)
      if (!environmentInitialized.current) {
        const initial = cfg.active_environment as EnvironmentName
        setSelectedEnvironment(initial)
        setSelectedEnvironmentProfile(readEnvironmentProfile(cfg, initial))
        environmentInitialized.current = true
      } else {
        setSelectedEnvironmentProfile(readEnvironmentProfile(cfg, selectedEnvironment))
      }
      setProfileReady(true)
      const active = cfg.active_environment as EnvironmentName
      const activeProfile = readEnvironmentProfile(cfg, active)
      if (detectPlatformRuntime() === 'capacitor-android' && !db.getConfig('account_identity_key') && activeProfile.serverUrl && activeProfile.authToken) {
        const response = await safeFetch(`${activeProfile.serverUrl.replace(/\/$/, '')}/auth/me`, { headers: { Authorization: `Bearer ${activeProfile.authToken}` } }, 5000)
        const userId = Number((await response.json().catch(() => null))?.user?.id)
        if (response.ok && Number.isSafeInteger(userId) && userId > 0) {
          const accountDb = await activateAccountStorage(createAccountIdentity(activeProfile.serverUrl, userId))
          accountDb.setConfig(environmentKey(active, 'server_url'), activeProfile.serverUrl)
          accountDb.setConfig('active_environment', active)
          accountDb.setConfig(environmentKey(active, 'verified_user_id'), String(userId))
          await accountDb.setSecureConfig?.(environmentKey(active, 'auth_token'), activeProfile.authToken)
          await writeActiveAccountStorageKey(createAccountIdentity(activeProfile.serverUrl, userId).storageKey)
          provisionTimerWidgetRuntime(accountDb, { ...activeProfile, verifiedUserId: String(userId) })
          await refreshSyncConfiguration(accountDb)
          setRefreshTrigger(prev => prev + 1)
          return
        }
      }
      provisionTimerWidgetRuntime(db, activeProfile)
      setSettings({
        server_url: activeProfile.serverUrl || defaultSettings.server_url,
        auth_token: activeProfile.authToken || '',
        study_time_min: studySecondsToMinutes(cfg.study_time_min, 1500),
        study_time_max: studySecondsToMinutes(cfg.study_time_max, 5400),
        short_break_duration: Math.round(configNumber(cfg, 'short_break_duration', 300) / 60),
        long_break_duration: resolveLongBreakMinutes(cfg['long_break_duration']),
        long_break_threshold: Math.round(configNumber(cfg, 'long_break_threshold', 5400) / 60),
        input_output_countdown_min: resolveInputOutputCountdownMinutes(cfg['input_output_countdown_min']),
        sync_interval: configNumber(cfg, 'sync_interval', defaultSettings.sync_interval),
        statistics_start_date: resolveStatisticsStartDate(cfg['statistics_start_date'] || cfg['checklist_sync_start_date']).date,
        last_sync_at: cfg['last_sync_at'] || '—',
        atimelogger_enabled: false,
        atimelogger_username: '',
        atimelogger_password: '',
        atimelogger_owner_username: '',
        atimelogger_token: '',
        atimelogger_refresh_token: '',
        atimelogger_device_id: '',
        atimelogger_auth_required: false,
        atimelogger_type_map: '{}',
        atimelogger_unmatched_categories: '[]',
        sleep_sync_enabled: true,
        sleep_sync_interval: configNumber(cfg, 'sleep_sync_interval', 30),
        ai_text_model: cfg['ai_text_model'] || '',
        ai_text_api_key: '',
        ai_text_endpoint: cfg['ai_text_endpoint'] || '',
        ai_vision_model: cfg['ai_vision_model'] || '',
        ai_vision_api_key: '',
        ai_vision_endpoint: cfg['ai_vision_endpoint'] || '',
        shortcut_toggle_timer: cfg['shortcut_toggle_timer'] || 'Alt+C',
        shortcut_minimize: cfg['shortcut_minimize'] || 'Alt+Z',
        music_folder: cfg['music_folder'] || 'assets/audio',
        audio_start: normalizeAudioSettingValue('audio_start', cfg.audio_start),
        audio_microBreak: normalizeAudioSettingValue('audio_microBreak', cfg.audio_microBreak),
        audio_endMicroBreak: normalizeAudioSettingValue('audio_endMicroBreak', cfg.audio_endMicroBreak),
        audio_startLongBreak: normalizeAudioSettingValue('audio_startLongBreak', cfg.audio_startLongBreak),
        audio_end: normalizeAudioSettingValue('audio_end', cfg.audio_end),
        audio_coin: normalizeAudioSettingValue('audio_coin', cfg.audio_coin),
        ledger_format_habit_success: cfg['ledger_format_habit_success'] || defaultSettings.ledger_format_habit_success,
        ledger_format_habit_makeup: cfg['ledger_format_habit_makeup'] || defaultSettings.ledger_format_habit_makeup,
        ledger_format_habit_fail: cfg['ledger_format_habit_fail'] || defaultSettings.ledger_format_habit_fail,
        ledger_format_task_success: cfg['ledger_format_task_success'] || defaultSettings.ledger_format_task_success,
        ledger_format_task_fail: cfg['ledger_format_task_fail'] || defaultSettings.ledger_format_task_fail,
      })
      const savedTheme = (cfg['theme'] || 'light') as 'light' | 'dark'
      setTheme(savedTheme)
      if (savedTheme === 'dark') {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
      testConnection(activeProfile.serverUrl, activeProfile.authToken, active).catch(() => {})
    })
  }, [refreshTrigger, testConnection, selectedEnvironment])

  const selectEnvironment = useCallback((environment: EnvironmentName) => {
    setSelectedEnvironment(environment)
    getDatabase().then(db => setSelectedEnvironmentProfile(readEnvironmentProfile(db.getAllConfig(), environment)))
  }, [])

  const updateEnvironmentSetting = useCallback(async (field: 'server_url' | 'username', value: string, environment?: EnvironmentName) => {
    const db = await getDatabase()
    const targetEnvironment = environment || selectedEnvironment
    db.setConfig(environmentKey(targetEnvironment, field), value)
    if (targetEnvironment === selectedEnvironment) {
      setSelectedEnvironmentProfile(prev => ({
        ...prev,
        [field === 'server_url' ? 'serverUrl' : 'username']: value,
      }))
    }
  }, [selectedEnvironment])

  const updateSetting = useCallback(async (key: string, value: string | number | boolean) => {
    const db = await getDatabase()
      let finalVal = String(value)
      const timeKeys = ['study_time_min', 'study_time_max', 'short_break_duration', 'long_break_duration', 'long_break_threshold', 'input_output_countdown_min']
      if (timeKeys.includes(key)) {
        finalVal = minutesToStoredSeconds(value as string | number)
      }

      db.setConfig(key, finalVal)
      if (key in AUDIO_SETTING_DEFAULTS) {
        const next = { ...db.getAllConfig(), [key]: finalVal }
        syncAudioConfig(audioConfigFromSettings(next))
      }
      setRefreshTrigger(prev => prev + 1)
    if (!shouldReloadHotkeysForSetting(key)) return { ok: true }
    const result: any = await getElectronApi()?.reloadHotkeys?.()
    const registration = result?.[key === 'shortcut_toggle_timer' ? 'timer' : 'minimize']
    if (registration?.ok) return { ok: true }
    return { ok: false, error: registration?.reason === 'invalid' ? '快捷键格式无效' : registration?.reason === 'unavailable' ? '快捷键已被系统或其他程序占用' : '桌面快捷键服务不可用' }
  }, [activeEnvironment])

  const switchEnvironment = useCallback(async (environment: EnvironmentName) => {
    const db = await getDatabase()
    const profile = readEnvironmentProfile(db.getAllConfig(), environment)
    const url = profile.serverUrl
    const token = profile.authToken
    let writes: Record<string, string>
    try { writes = environmentActivationWrites(environment, profile) }
    catch (err: any) { return { success: false, error: err.message } }
    const tested = await testConnection(url, token, environment)
    if (!tested.success) return tested
    Object.entries(writes).forEach(([key, value]) => db.setConfig(key, value))
    provisionTimerWidgetRuntime(db, profile)
    await refreshSyncConfiguration(db)
    setActiveEnvironment(environment)
    setRefreshTrigger(prev => prev + 1)
    return { success: true }
  }, [testConnection])

  const toggleTheme = useCallback(() => {
    const nextTheme = theme === 'light' ? 'dark' : 'light'
    if (detectPlatformRuntime() === 'capacitor-android') {
      androidThemeOverrideRef.current = { theme: nextTheme, expiresAt: nextAndroidThemeBoundaryAt() }
    }
    setTheme(nextTheme)
    document.documentElement.classList.toggle('dark', nextTheme === 'dark')
    updateSetting('theme', nextTheme)
  }, [theme, updateSetting])

  const syncNow = useCallback(() => {}, [])

  const connectionStatus = deriveProfileConnectionStatus(
    selectedEnvironmentProfile,
    selectedEnvironment === activeEnvironment,
    connectionStatuses[selectedEnvironment],
  )

  const exportConfig = useCallback(async () => {
    try {
      const db = await getDatabase()
      const cfg = db.getAllConfig()
      const payload = buildSettingsConfigPayload(cfg)
      await shareTextFile('mytimelogger_config.json', JSON.stringify(payload, null, 2))
    } catch (err: any) {
      alert(`导出配置失败: ${err.message}`)
    }
  }, [])

  const importConfig = useCallback(async () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return

      const reader = new FileReader()
      reader.onload = async (event) => {
        try {
          const content = event.target?.result as string
          const payload = JSON.parse(content)
          const db = await getDatabase()
          const settings = parseSettingsConfigPayload(payload)
          for (const [key, value] of Object.entries(settings)) {
            db.setConfig(key, value)
          }
          try {
            await applyImportedLoggingConfig({ ...db.getAllConfig(), ...settings }, activeEnvironment)
          } catch (applyErr: any) {
            alert(`配置已导入，但日志级别同步到服务端失败: ${applyErr.message}`)
            setRefreshTrigger(prev => prev + 1)
            return
          }
          alert('配置导入成功！')
          setRefreshTrigger(prev => prev + 1)
        } catch (err: any) {
          alert(`导入配置失败: ${err.message}`)
        }
      }
      reader.readAsText(file)
    }
    input.click()
  }, [activeEnvironment, applyImportedLoggingConfig])

  return useMemo(
    () => ({
      settings,
      theme,
      updateSetting,
      toggleTheme,
      syncNow,
      syncStatus: 'idle' as const,
      exportConfig,
      importConfig,
      connectionStatus,
      profileReady,
      testConnection,
      verifyActiveSession,
      loginEnvironment,
      clearActiveSession,
      logoutActiveSession,
      activeEnvironment,
      switchEnvironment,
      selectedEnvironment,
      selectedEnvironmentProfile,
      selectEnvironment,
      updateEnvironmentSetting,
    }),
    [settings, theme, updateSetting, toggleTheme, syncNow, exportConfig, importConfig, connectionStatus, profileReady, testConnection, verifyActiveSession, loginEnvironment, clearActiveSession, logoutActiveSession, activeEnvironment, switchEnvironment, selectedEnvironment, selectedEnvironmentProfile, selectEnvironment, updateEnvironmentSetting],
  )
}
