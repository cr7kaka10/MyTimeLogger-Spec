import { useCallback, useEffect, useState } from 'react'
import type { EnvironmentName } from '@core/EnvironmentProfiles'
import { getDatabase } from '../../db'
import { INHERIT_LOG_LEVEL, mergeLoggingDraft, sameEditableLoggingConfig, updateModuleLevel, type LoggingConfigState, type LoggingDraft } from './loggingSettingsState'

type LoggingConfig = LoggingConfigState

const defaultConfig: LoggingConfig = {
  global_level: 'INFO',
  module_levels: {},
  available_levels: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
  logger_names: ['server', 'server.request', 'server.sync_hub', 'server.ticktick_client', 'server.store', 'server.analyzer'],
}

const labels: Record<string, string> = {
  server: '服务端主模块',
  'server.request': '请求日志',
  'server.sync_hub': '同步引擎',
  'server.ticktick_client': 'TickTick/Dida',
  'server.store': '服务端存储',
  'server.analyzer': '睡眠分析',
  uvicorn: '服务进程',
  'uvicorn.error': '服务错误',
  'uvicorn.access': '访问日志',
}

const draftKey = (environment: EnvironmentName) => `env_${environment}_logging_config_draft`

const responseBody = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}
  try { return JSON.parse(text) } catch { return { detail: text } }
}

const normalizeConfig = (raw: any): LoggingConfig => ({
  ...defaultConfig,
  ...raw,
  module_levels: { ...(raw?.module_levels || {}) },
  available_levels: raw?.available_levels || defaultConfig.available_levels,
  logger_names: raw?.logger_names || defaultConfig.logger_names,
})

export function LoggingSettings({ serverUrl, token, environment, isActive }: { serverUrl: string; token: string; environment: EnvironmentName; isActive: boolean }) {
  const [config, setConfig] = useState<LoggingConfig>(defaultConfig)
  const [message, setMessage] = useState('')
  const base = serverUrl.replace(/\/$/, '')
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }

  const saveDraft = useCallback(async (value: LoggingConfig) => {
    const db = await getDatabase()
    db.setConfig(draftKey(environment), JSON.stringify({
      global_level: value.global_level,
      module_levels: value.module_levels,
      dirty: true,
    }))
  }, [environment])

  const clearDraft = useCallback(async () => {
    const db = await getDatabase()
    db.setConfig(draftKey(environment), '')
  }, [environment])

  const load = useCallback(async () => {
    const db = await getDatabase()
    const rawDraft = db.getConfig(draftKey(environment))
    let draft: LoggingDraft | null = null
    if (rawDraft) {
      try { draft = JSON.parse(rawDraft) } catch { draft = null }
    }
    setMessage(isActive ? '' : '可预先保存配置，启用环境后同步到服务端')
    if (draft) setConfig(draft)
    if (!isActive || !base || !token) return
    try {
      const response = await fetch(`${base}/admin/logging/config`, { headers })
      if (response.status === 404) throw new Error('服务端版本未更新或未重启')
      if (!response.ok) throw new Error(`读取失败 (${response.status})`)
      const serverConfig = normalizeConfig(await responseBody(response))
      const legacySynced = Boolean(draft && !draft.dirty && sameEditableLoggingConfig(draft, serverConfig))
      setConfig(draft && !legacySynced ? mergeLoggingDraft(serverConfig, draft) : serverConfig)
      if (legacySynced) await clearDraft()
      if (draft && !legacySynced) setMessage('本地草稿待同步到服务端')
    } catch (error: any) {
      setMessage(error.message)
    }
  }, [base, token, environment, isActive, clearDraft])

  useEffect(() => { load() }, [load])

  const setModuleLevel = (name: string, level: string) => {
    setConfig(prev => ({ ...prev, module_levels: updateModuleLevel(prev.module_levels, name, level) }))
  }

  const submit = async () => {
    await saveDraft(config)
    if (!isActive) {
      setMessage('草稿已保存，启用环境后同步到服务端')
      return
    }
    setMessage('正在保存...')
    try {
      const response = await fetch(`${base}/admin/logging/config`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ global_level: config.global_level, module_levels: config.module_levels }),
      })
      const body = await responseBody(response)
      if (response.status === 404) throw new Error('服务端版本未更新或未重启')
      if (!response.ok) throw new Error(body.detail || '保存失败')
      setConfig(normalizeConfig(body))
      await clearDraft()
      setMessage('日志级别已保存并生效')
    } catch (error: any) {
      setMessage(error.message)
    }
  }

  const levels = config.available_levels || defaultConfig.available_levels!
  const loggerNames = config.logger_names || defaultConfig.logger_names!

  return <section className="overflow-hidden rounded-xl border border-gray-100 bg-white">
    <div className="border-b border-gray-50 px-4 py-2 text-xs font-semibold uppercase text-gray-400">服务端日志级别</div>
    <label className="flex h-12 items-center justify-between gap-4 border-b border-gray-50 px-4">
      <span className="font-medium text-gray-900">全局级别</span>
      <select value={config.global_level} onChange={event => setConfig({ ...config, global_level: event.target.value })}
        className="bg-transparent text-right text-sm text-gray-500 outline-none">
        {levels.map(level => <option key={level} value={level}>{level}</option>)}
      </select>
    </label>
    {loggerNames.map(name => (
      <label key={name} className="flex h-12 items-center justify-between gap-4 border-b border-gray-50 px-4">
        <span className="font-medium text-gray-900">{labels[name] || name}</span>
        <select value={config.module_levels[name] || INHERIT_LOG_LEVEL} onChange={event => setModuleLevel(name, event.target.value)}
          className="bg-transparent text-right text-sm text-gray-500 outline-none">
          <option value={INHERIT_LOG_LEVEL}>继承全局（{config.global_level}）</option>
          {levels.map(level => <option key={level} value={level}>{level}</option>)}
        </select>
      </label>
    ))}
    <div className="flex min-h-12 items-center justify-between gap-3 px-4 py-3">
      <span className="min-w-0 flex-1 truncate text-xs text-gray-400">{message || '保存后立即应用到当前服务端'}</span>
      <button type="button" onClick={submit} className="theme-accent-button rounded-lg bg-blue-50 px-3 py-1 text-sm text-blue-600">保存日志</button>
    </div>
  </section>
}
