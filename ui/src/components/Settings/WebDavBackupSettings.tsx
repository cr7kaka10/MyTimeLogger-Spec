import { useCallback, useEffect, useState } from 'react'
import type { EnvironmentName } from '@core/EnvironmentProfiles'

type Config = {
  enabled: boolean
  endpoint: string
  bucket: string
  region: string
  access_key: string
  secret_key: string
  reports_prefix: string
  secret_configured?: boolean
}

const defaultConfig: Config = {
  enabled: false,
  endpoint: '',
  bucket: 'obss3',
  region: 'us-east-1',
  access_key: '',
  secret_key: '',
  reports_prefix: 'reports',
}
const responseBody = async (response: Response) => {
  const text = await response.text()
  if (!text) return {}
  try { return JSON.parse(text) } catch { return { detail: text } }
}

const normalizeConfig = (raw: any): Config => {
  const migrated = { ...raw }
  if (!migrated.endpoint) migrated.endpoint = migrated.reports_endpoint || ''
  if (!migrated.bucket) migrated.bucket = migrated.reports_bucket || 'obss3'
  if (!migrated.region) migrated.region = migrated.reports_region || 'us-east-1'
  if (!migrated.access_key) migrated.access_key = migrated.reports_access_key || ''
  if (!migrated.secret_key) migrated.secret_key = migrated.reports_secret_key || ''
  if (!migrated.secret_configured) migrated.secret_configured = migrated.reports_secret_configured
  return { ...defaultConfig, ...migrated }
}

export function WebDavBackupSettings({ serverUrl, token, environment, isActive }: { serverUrl: string; token: string; environment: EnvironmentName; isActive: boolean }) {
  const [config, setConfig] = useState<Config>(defaultConfig)
  const [message, setMessage] = useState('')
  const base = serverUrl.replace(/\/$/, '')
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }

  const load = useCallback(async () => {
    setConfig(defaultConfig)
    setMessage(isActive ? '' : '当前环境未启用')
    if (!isActive || !base || !token) return
    try {
      const configResponse = await fetch(`${base}/admin/s3-backup/config`, { headers })
      if (configResponse.status === 404) throw new Error('服务端版本未更新或未重启')
      if (!configResponse.ok) throw new Error(`读取失败 (${configResponse.status})`)
      const serverConfig = await responseBody(configResponse)
      setConfig({ ...normalizeConfig(serverConfig), secret_key: '' })
      setMessage('已读取服务端状态')
    } catch (error: any) {
      setMessage(error.message)
    }
  }, [base, token, environment, isActive])

  useEffect(() => { load() }, [load, environment])

  const submit = async () => {
    if (!isActive) {
      setMessage('请先登录当前环境')
      return
    }
    setMessage('正在保存...')
    try {
      const response = await fetch(`${base}/admin/s3-backup/config`, {
        method: 'PUT', headers, body: JSON.stringify({ enabled: config.enabled }),
      })
      const body = await responseBody(response)
      if (response.status === 404) throw new Error('服务端版本未更新或未重启')
      if (!response.ok) throw new Error(body.detail || '操作失败')
      setConfig({ ...config, ...body, secret_key: config.secret_key })
      await load()
      setMessage('配置已保存')
    } catch (error: any) { setMessage(error.message) }
  }

  const connectionStatus = config.secret_configured ? '已连接' : '未连接'

  return <section className="overflow-hidden rounded-xl border border-gray-100 bg-white">
    <div className="border-b border-gray-50 px-4 py-2 text-xs font-semibold uppercase text-gray-400">S3 容灾备份</div>
    <div className="flex h-12 items-center justify-between border-b border-gray-50 px-4"><span className="font-medium">启用远程备份</span><input type="checkbox" checked={config.enabled} onChange={e => setConfig({ ...config, enabled: e.target.checked })} /></div>
    <div className="flex min-h-12 items-center justify-between gap-3 border-b border-gray-50 px-4 py-3">
      <span className="font-medium text-gray-900">连接状态</span>
      <span className="text-sm text-gray-400">{connectionStatus}</span>
    </div>
    <div className="flex min-h-12 items-center justify-between gap-3 px-4 py-3">
      <span className="min-w-0 text-sm text-gray-400">{message || '具体配置由私有环境文件管理'}</span>
      <button type="button" onClick={() => submit()} className="theme-accent-button rounded-lg bg-blue-50 px-3 py-1 text-sm text-blue-600">保存开关</button>
    </div>
  </section>
}
