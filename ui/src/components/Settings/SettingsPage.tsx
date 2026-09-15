import { memo, useCallback, useState, useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import type { UseSettingsReturn } from '../../hooks/useSettings'
import { NumberSheet } from '../common/NumberSheet'
import { LoggingSettings } from './LoggingSettings'
import { NotificationSettings } from './NotificationSettings'
import { AVAILABLE_AUDIO_FILES } from '../../utils/audio'
import { getDatabase, syncNow } from '../../db'
import { getElectronCapabilities } from '../../platform/electron'
import { createExternalBrowserService } from '../../platform/externalBrowser'
import { resolveStatisticsStartDate } from '@core/ChecklistSyncStartDate'
import { platformFetch } from '../../platform'
import { formatPlatformNetworkError } from '../../platform/fetch'
import { logRewardRebuildStage, parseRewardRebuildFailure, rewardRebuildHeader } from './rewardRebuildDiagnostics'
import type { RewardRebuildFailureView } from './rewardRebuildDiagnostics'

interface SettingsPageProps extends UseSettingsReturn {
  onOpenSleep: () => void
  onOpenCategoryManager: () => void
  onSignedOut: () => void
}

interface RowProps {
  label: string
  value: string
  onClick?: () => void
}

const SettingRow = memo(({ label, value, onClick }: RowProps) => (
  <button type="button" onClick={onClick} className="flex h-12 w-full items-center justify-between gap-4 border-b border-gray-50 px-4 text-left last:border-0 active:bg-gray-50 md:hover:bg-gray-50">
    <span className="font-medium text-gray-900">{label}</span>
    <span className="text-right text-sm text-gray-400">{value}</span>
  </button>
))
SettingRow.displayName = 'SettingRow'

const audioOptions = [
  { value: 'none', label: '无/静音' },
  ...Object.keys(AVAILABLE_AUDIO_FILES).map(k => ({ value: k, label: k }))
]

const AudioSelectRow = ({ label, value, onChange, onPlay }: { label: string, value: string, onChange: (v: string) => void, onPlay: () => void }) => (
  <div className="flex h-12 items-center justify-between gap-4 border-b border-gray-50 px-4">
    <span className="font-medium text-gray-900">{label}</span>
    <div className="flex items-center gap-2">
      <select
        className="rounded bg-transparent text-sm text-gray-400 outline-none hover:text-gray-600 focus:text-blue-600 cursor-pointer text-right appearance-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {audioOptions.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <button 
        type="button" 
        onClick={onPlay}
        className="text-gray-400 hover:text-blue-600 ml-1 p-1 text-base"
        title="试听"
      >
        🎵
      </button>
    </div>
  </div>
)


const statusClass = (state: 'ok' | 'warn' | 'muted') => (
  state === 'ok' ? 'text-green-600' : state === 'warn' ? 'text-amber-600' : 'text-gray-400'
)

const actionButtonClass = 'inline-flex h-8 w-16 flex-none items-center justify-center rounded-full border border-blue-100 bg-blue-50 px-3 text-xs font-semibold text-blue-700 transition hover:bg-blue-100 active:scale-95 whitespace-nowrap'

const requestRewardRebuildConfirmation = (preview: Record<string, any>, phrase: string): Promise<string | null> => new Promise(resolve => {
  const overlay = document.createElement('div'); overlay.className = 'fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4 backdrop-blur-sm'
  const panel = document.createElement('div'); panel.className = 'w-full max-w-[440px] rounded-3xl bg-white p-6 shadow-2xl'
  const title = document.createElement('h3'); title.className = 'text-lg font-bold text-gray-900'; title.textContent = '确认重新拉取并重算金币'
  const summary = document.createElement('p'); summary.className = 'mt-2 text-sm leading-6 text-gray-500'
  summary.textContent = `将保留行为并重建全部金币流水：${preview.old_ledger_rows || 0} 笔 → 预计 ${preview.new_ledger_rows_estimate || 0} 笔，余额 ${preview.old_balance || 0} → 预计 ${preview.new_balance_estimate || 0}。背包 ${preview.old_backpack_items || 0} → ${preview.new_backpack_items_estimate || 0}，碎片 ${preview.old_fragment_rows || 0} → ${preview.new_fragment_rows_estimate || 0}。失败时自动恢复旧账。`
  const diagnostics = document.createElement('p'); diagnostics.className = 'mt-3 whitespace-pre-line rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700'
  const skipped = Array.isArray(preview.skipped_preview) ? preview.skipped_preview.slice(0, 5) : []
  const warnings = Array.isArray(preview.warnings) ? preview.warnings : []
  diagnostics.textContent = [...warnings, ...skipped.map((item: any) => `跳过 ${item.source || '未知来源'}${item.business_date ? ` ${item.business_date}` : ''}：${item.reason || '不可验证'}`)].join('\n') || '没有发现不可验证行为'
  const hint = document.createElement('p'); hint.className = 'mt-4 text-xs text-gray-500'; hint.textContent = '请输入确认短语：'
  const code = document.createElement('code'); code.className = 'mt-1 block select-all rounded-xl bg-gray-50 px-3 py-2 text-sm text-rose-600'; code.textContent = phrase
  const input = document.createElement('input'); input.className = 'mt-3 h-11 w-full rounded-xl border border-gray-200 px-3 text-sm outline-none focus:border-blue-400'; input.placeholder = phrase
  const actions = document.createElement('div'); actions.className = 'mt-5 grid grid-cols-2 gap-3'
  const cancel = document.createElement('button'); cancel.className = 'h-11 rounded-2xl bg-gray-100 text-sm font-semibold text-gray-600'; cancel.textContent = '取消'
  const confirm = document.createElement('button'); confirm.className = 'h-11 rounded-2xl bg-rose-600 text-sm font-bold text-white disabled:opacity-40'; confirm.textContent = '确认重建'; confirm.disabled = true
  const finish = (value: string | null) => { overlay.remove(); resolve(value) }
  input.addEventListener('input', () => { confirm.disabled = input.value.trim() !== phrase })
  input.addEventListener('keydown', event => { if (event.key === 'Escape') finish(null); if (event.key === 'Enter' && !confirm.disabled) finish(phrase) })
  cancel.addEventListener('click', () => finish(null)); confirm.addEventListener('click', () => finish(phrase))
  actions.append(cancel, confirm); panel.append(title, summary, diagnostics, hint, code, input, actions); overlay.append(panel); document.body.append(overlay); input.focus()
})

const RewardRebuildFailurePanel = ({ failure }: { failure: RewardRebuildFailureView }) => {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(failure.copyText)
    } catch {
      const area = document.createElement('textarea')
      area.value = failure.copyText; area.style.position = 'fixed'; area.style.opacity = '0'
      document.body.append(area); area.select(); document.execCommand('copy'); area.remove()
    }
    setCopied(true); window.setTimeout(() => setCopied(false), 1500)
  }
  return <div className="border-b border-rose-100 bg-rose-50 px-4 py-3 text-xs text-rose-800">
    <div className="font-semibold">{failure.message}</div>
    <div className="mt-1">失败阶段：{failure.stage} · {failure.recovery}</div>
    {failure.causes.length > 0 && <div className="mt-2 space-y-1">{failure.causes.map((cause, index) => <div key={`${index}-${cause}`}>· {cause}</div>)}</div>}
    {failure.suggestions.length > 0 && <div className="mt-2">建议：{failure.suggestions.join('；')}</div>}
    <details className="mt-2 rounded-lg bg-white/70 px-3 py-2">
      <summary className="cursor-pointer select-none font-medium">诊断详情</summary>
      <div className="mt-2 break-all whitespace-pre-line text-gray-600">错误码：{failure.code}{'\n'}诊断编号：{failure.traceId}{failure.jobId ? `\n作业编号：${failure.jobId}` : ''}{'\n'}时间：{failure.occurredAt}</div>
      <button type="button" onClick={() => void copy()} className="mt-2 rounded-full border border-rose-200 bg-white px-3 py-1 font-medium text-rose-700">{copied ? '已复制' : '复制脱敏诊断'}</button>
    </details>
  </div>
}

const ServiceRow = memo(({
  label,
  status,
  statusTone = 'muted',
  onStatusClick,
  onConfigure,
  action,
  controls,
  children,
}: {
  label: string
  status: string
  statusTone?: 'ok' | 'warn' | 'muted'
  onStatusClick?: () => void
  onConfigure: () => void
  action?: ReactNode
  controls?: ReactNode
  children?: ReactNode
}) => (
  <div className="border-b border-gray-50 px-4 py-3 last:border-0">
    <div className="grid min-h-9 grid-cols-[148px_minmax(0,1fr)_max-content] items-center gap-3 max-sm:grid-cols-1 max-sm:items-stretch">
      <span className="whitespace-nowrap font-medium text-gray-900">{label}</span>
      <div className="min-w-0">
        {controls}
      </div>
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-2 max-sm:justify-start">
        {onStatusClick
          ? <button type="button" onClick={onStatusClick} className={`text-right text-sm font-medium underline-offset-2 hover:underline max-sm:text-left ${statusClass(statusTone)}`}>{status}</button>
          : <span className={`text-right text-sm font-medium max-sm:text-left ${statusClass(statusTone)}`}>{status}</span>}
        {action ?? <button type="button" onClick={onConfigure} className={actionButtonClass}>配置</button>}
      </div>
    </div>
    {children}
  </div>
))
ServiceRow.displayName = 'ServiceRow'

export const SettingsPage = memo(({
  settings, updateSetting,
  onOpenCategoryManager, exportConfig, importConfig,
  activeEnvironment, selectedEnvironment, selectedEnvironmentProfile, clearActiveSession, logoutActiveSession, verifyActiveSession, onSignedOut,
}: SettingsPageProps) => {
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editingValue, setEditingValue] = useState(0)
  const [integrationStatus, setIntegrationStatus] = useState<any>(null)
  const [showGuide, setShowGuide] = useState(false)
  const [atimeloggerUsername, setAtimeloggerUsername] = useState('')
  const [atimeloggerPassword, setAtimeloggerPassword] = useState('')
  const [atimeloggerMessage, setAtimeloggerMessage] = useState('')
  const [atimeloggerSaving, setAtimeloggerSaving] = useState(false)
  const [atimeloggerFailures, setAtimeloggerFailures] = useState<any[]>([])
  const [showAtimeloggerFailures, setShowAtimeloggerFailures] = useState(false)
  const [atimeloggerFailuresLoading, setAtimeloggerFailuresLoading] = useState(false)
  const [atimeloggerFailuresMessage, setAtimeloggerFailuresMessage] = useState('')
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [rewardRebuildBusy, setRewardRebuildBusy] = useState(false)
  const [rewardRebuildMessage, setRewardRebuildMessage] = useState('')
  const [rewardRebuildFailure, setRewardRebuildFailure] = useState<RewardRebuildFailureView | null>(null)
  const [statisticsStartDateDraft, setStatisticsStartDateDraft] = useState(settings.statistics_start_date)
  const atimeloggerPasswordRef = useRef<HTMLInputElement>(null)
  const desktopCapabilities = getElectronCapabilities()
  const beijingToday = new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10)

  useEffect(() => {
    setStatisticsStartDateDraft(settings.statistics_start_date)
  }, [settings.statistics_start_date])

  const playPreview = useCallback((srcKey: string) => {
    if (srcKey && srcKey !== 'none') {
      const src = AVAILABLE_AUDIO_FILES[srcKey]
      if (src) new Audio(src).play().catch(e => console.warn(e))
    }
  }, [])

  const signOut = async () => {
    setSigningOut(true)
    try { await logoutActiveSession(); onSignedOut() }
    finally { setSigningOut(false); setShowSignOutConfirm(false) }
  }

  const rebuildRewardLedger = useCallback(async (startDate: string) => {
    const base = selectedEnvironmentProfile.serverUrl?.replace(/\/$/, ''); const token = selectedEnvironmentProfile.authToken
    if (!base || !token) return alert('请先登录当前环境')
    if (rewardRebuildBusy) return
    const requestId = `reward-rebuild-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
    let traceId = requestId; let jobId = ''; let stage = 'capability_check'
    const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, 'X-Request-ID': requestId }
    const fail = (job: unknown, message?: string) => {
      const failure = parseRewardRebuildFailure(job, { traceId, jobId, stage, message })
      setRewardRebuildFailure(failure); setRewardRebuildMessage('重建失败 · 可展开查看原因')
      return failure
    }
    setRewardRebuildBusy(true); setRewardRebuildMessage('正在检查…'); setRewardRebuildFailure(null)
    try {
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: 'start' })
      const pingResponse = await platformFetch(`${base}/ping`, { headers: { 'X-Request-ID': requestId } })
      const ping = await pingResponse.json().catch(() => ({}))
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: pingResponse.ok ? 'success' : 'failure', httpStatus: pingResponse.status })
      if (!pingResponse.ok || Number(ping?.capabilities?.reward_ledger_rebuild?.version || 0) < 2) return fail({}, '服务端尚未升级或重启，暂不能重建金币流水')
      stage = 'preview'; setRewardRebuildMessage('正在统计影响…')
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: 'start' })
      const previewResponse = await platformFetch(`${base}/api/rewards/rebuild/preview`, { method: 'POST', headers, body: JSON.stringify({ contract_version: 2, statistics_start_date: startDate }) })
      const preview = await previewResponse.json().catch(() => ({}))
      traceId = preview?.trace_id || rewardRebuildHeader(previewResponse.headers, 'x-trace-id') || rewardRebuildHeader(previewResponse.headers, 'x-request-id') || traceId
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: previewResponse.ok ? 'success' : 'failure', httpStatus: previewResponse.status })
      if (previewResponse.status === 401 || previewResponse.status === 403) {
        const session = await verifyActiveSession()
        if (session === 'invalid') {
          await clearActiveSession()
          onSignedOut()
          return alert('登录会话已被服务器撤销，请重新登录后再拉取')
        }
        return alert(session === 'unavailable'
          ? '无法确认登录状态，已保留本地登录；请恢复网络后重试'
          : '当前请求被服务器拒绝，但登录会话仍有效')
      }
      if (!previewResponse.ok) return fail(preview, preview?.detail || `预览失败（${previewResponse.status}）`)
      const capabilitiesResponse = await platformFetch(`${base}/api/rewards/rebuild/capabilities`, { headers })
      const capabilities = await capabilitiesResponse.json().catch(() => ({}))
      const phrase = await requestRewardRebuildConfirmation(preview, capabilities.confirmation_phrase || 'REBUILD REWARD LEDGER')
      if (!phrase) return setRewardRebuildMessage('已取消')
      stage = 'job_create'; setRewardRebuildMessage('正在重新拉取并重算…')
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: 'start' })
      const response = await platformFetch(`${base}/api/rewards/rebuild/start`, { method: 'POST', headers, body: JSON.stringify({ contract_version: 2, statistics_start_date: startDate, preview_hash: preview.preview_hash, confirmation_phrase: phrase }) })
      const started = await response.json().catch(() => ({}))
      traceId = started?.job?.trace_id || rewardRebuildHeader(response.headers, 'x-trace-id') || rewardRebuildHeader(response.headers, 'x-request-id') || traceId
      jobId = started?.job?.id || ''
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: response.ok ? 'success' : 'failure', httpStatus: response.status })
      if (!response.ok) return fail(started, started?.detail || '启动失败')
      let job = started.job
      stage = 'job_poll'; logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: 'start' })
      for (let attempt = 0; attempt < 600 && ['queued', 'running'].includes(job?.status); attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 1000))
        const statusResponse = await platformFetch(`${base}/api/rewards/rebuild/jobs/${encodeURIComponent(job.id)}`, { headers })
        job = await statusResponse.json(); if (!statusResponse.ok) throw new Error(job?.detail || '查询重建进度失败')
      }
      traceId = job?.trace_id || traceId; jobId = job?.id || jobId
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: job?.status === 'succeeded' ? 'success' : 'failure' })
      if (job?.status !== 'succeeded') return fail(job)
      stage = 'client_sync'; setRewardRebuildMessage('正在同步新流水…')
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: 'start' })
      const localPull = await syncNow({ reason: 'reward-ledger-rebuild' })
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: localPull.ok ? 'success' : 'failure' })
      if (!localPull.ok) return fail({}, '服务端已完成重建，本地刷新失败；请点击同步重试')
      const result = job.result || {}
      const skipped = Array.isArray(result.skipped) ? result.skipped.length : 0
      const skippedDetails = Array.isArray(result.skipped) ? result.skipped.slice(0, 5).map((item: any) => `\n· ${item.source || '未知来源'}${item.business_date ? ` ${item.business_date}` : ''}：${item.reason || '不可验证'}`).join('') : ''
      const warnings = Array.isArray(result.warnings) && result.warnings.length ? `\n警告：${result.warnings.join('；')}` : ''
      setRewardRebuildMessage(`已完成 · ${result.ledger_rows || 0} 笔 · 余额 ${result.balance || 0}`)
      alert(`金币流水已重建：${result.ledger_rows || 0} 笔，余额 ${result.balance || 0}，背包 ${result.backpack_items || 0}，碎片 ${result.fragment_rows || 0}${skipped ? `；跳过 ${skipped} 条` : ''}${warnings}${skippedDetails}`)
    } catch (error: any) {
      const message = formatPlatformNetworkError(error)
      logRewardRebuildStage({ requestId, traceId, jobId, stage, outcome: 'failure', errorType: error?.name || 'NetworkError' })
      fail({}, `${message}`)
    } finally {
      setRewardRebuildBusy(false)
    }
  }, [selectedEnvironmentProfile.serverUrl, selectedEnvironmentProfile.authToken, rewardRebuildBusy, clearActiveSession, verifyActiveSession, onSignedOut])

  const loadIntegrationStatus = useCallback(async () => {
    const base = selectedEnvironmentProfile.serverUrl?.replace(/\/$/, '')
    const token = selectedEnvironmentProfile.authToken
    if (!base || !token || activeEnvironment !== selectedEnvironment) {
      setIntegrationStatus(null)
      return Promise.resolve(null)
    }
    return platformFetch(`${base}/admin/integration-config/status`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(response => response.ok ? response.json() : null)
      .then(body => {
        setIntegrationStatus(body)
        console.info('[login-info]', {
          account: selectedEnvironmentProfile.username || '未设置',
          environment: activeEnvironment,
          serverUrl: selectedEnvironmentProfile.serverUrl || '未配置',
          device: `${(window as any).electronAPI ? 'Electron 桌面端' : 'Web 客户端'} · ${navigator.platform || 'Unknown'}`,
          statusCheckedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
        })
        return body
      })
      .catch(() => { setIntegrationStatus(null); return null })
  }, [selectedEnvironmentProfile.serverUrl, selectedEnvironmentProfile.authToken, selectedEnvironmentProfile.username, activeEnvironment, selectedEnvironment])

  useEffect(() => { loadIntegrationStatus() }, [loadIntegrationStatus])

  useEffect(() => {
    setAtimeloggerUsername(integrationStatus?.atimelogger?.username || '')
  }, [integrationStatus?.atimelogger?.username])

  const bindAtimelogger = useCallback(async () => {
    const base = selectedEnvironmentProfile.serverUrl?.replace(/\/$/, '')
    const token = selectedEnvironmentProfile.authToken
    if (!base || !token || activeEnvironment !== selectedEnvironment) {
      setAtimeloggerMessage('请先登录当前环境')
      return
    }
    if (!atimeloggerUsername.trim() || !atimeloggerPassword) {
      setAtimeloggerMessage('请输入账号和密码')
      return
    }
    setAtimeloggerSaving(true)
    setAtimeloggerMessage('正在登录...')
    try {
      const response = await platformFetch(`${base}/admin/provider-bindings/atimelogger`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          enabled: true,
          username: atimeloggerUsername.trim(),
          password: atimeloggerPassword,
          owner_username: selectedEnvironmentProfile.username.trim(),
          auth_required: false,
        }),
        timeoutMs: 10000,
      } as any)
      const body = await response.json().catch(() => ({}))
      if (!response.ok) {
        setAtimeloggerMessage(body?.detail || `登录失败 (${response.status})`)
        return
      }
      setAtimeloggerPassword('')
      setAtimeloggerMessage('已验证登录，完成记录将由服务端异步备份')
      await loadIntegrationStatus()
    } catch (error: any) {
      setAtimeloggerMessage(formatPlatformNetworkError(error))
    } finally {
      setAtimeloggerSaving(false)
    }
  }, [selectedEnvironmentProfile.serverUrl, selectedEnvironmentProfile.authToken, selectedEnvironmentProfile.username, activeEnvironment, selectedEnvironment, atimeloggerUsername, atimeloggerPassword, loadIntegrationStatus])

  const loadAtimeloggerFailures = useCallback(async () => {
    const base = selectedEnvironmentProfile.serverUrl?.replace(/\/$/, '')
    const token = selectedEnvironmentProfile.authToken
    if (!base || !token) return
    setAtimeloggerFailuresLoading(true); setAtimeloggerFailuresMessage('')
    try {
      const response = await platformFetch(`${base}/admin/provider-bindings/atimelogger/failures`, {
        headers: { Authorization: `Bearer ${token}` }, timeoutMs: 10000,
      } as any)
      const body = await response.json().catch(() => ({}))
      if (response.status === 404) {
        setAtimeloggerFailures([]); setAtimeloggerFailuresMessage('服务端暂不支持失败详情')
      } else if (!response.ok) {
        setAtimeloggerFailures([]); setAtimeloggerFailuresMessage(body?.detail || `加载失败（${response.status}）`)
      } else {
        setAtimeloggerFailures(Array.isArray(body?.items) ? body.items : [])
      }
    } catch (error: any) {
      setAtimeloggerFailures([]); setAtimeloggerFailuresMessage(formatPlatformNetworkError(error))
    } finally {
      setAtimeloggerFailuresLoading(false)
    }
  }, [selectedEnvironmentProfile.serverUrl, selectedEnvironmentProfile.authToken])

  const openAtimeloggerFailures = useCallback(() => {
    setShowAtimeloggerFailures(true)
    void loadAtimeloggerFailures()
  }, [loadAtimeloggerFailures])

  const retryAtimelogger = useCallback(async () => {
    const base = selectedEnvironmentProfile.serverUrl?.replace(/\/$/, '')
    const token = selectedEnvironmentProfile.authToken
    if (!base || !token) return
    setAtimeloggerSaving(true)
    try {
      const response = await platformFetch(`${base}/admin/provider-bindings/atimelogger/retry`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, timeoutMs: 10000,
      } as any)
      const body = await response.json().catch(() => ({}))
      setAtimeloggerMessage(response.ok ? `已提交 ${body.released || 0} 条待备份记录` : body?.detail || '重试失败')
      await loadIntegrationStatus()
      if (response.ok && showAtimeloggerFailures) await loadAtimeloggerFailures()
    } catch (error: any) {
      setAtimeloggerMessage(formatPlatformNetworkError(error))
    } finally {
      setAtimeloggerSaving(false)
    }
  }, [selectedEnvironmentProfile.serverUrl, selectedEnvironmentProfile.authToken, loadIntegrationStatus, showAtimeloggerFailures, loadAtimeloggerFailures])

  const serviceConfigUrl = useCallback(() => {
    const raw = selectedEnvironmentProfile.serverUrl?.trim()
    if (!raw) return ''
    const withScheme = /^https?:\/\//i.test(raw) ? raw : `http://${raw}`
    try {
      const url = new URL(withScheme)
      if (!url.port) url.port = '8000'
      url.pathname = '/config'
      url.search = ''
      url.hash = ''
      return url.toString()
    } catch {
      return ''
    }
  }, [selectedEnvironmentProfile.serverUrl])

  const openOnlineServiceConfig = useCallback(async () => {
    const url = serviceConfigUrl()
    if (!url) {
      alert('请先登录或配置当前环境的服务器地址')
      return
    }
    await createExternalBrowserService().open(url).catch(error => alert(error?.message || '无法打开浏览器'))
  }, [serviceConfigUrl])

  const atimeloggerVerified = integrationStatus?.atimelogger?.authenticated === true
  const atimeloggerConfigured = integrationStatus?.atimelogger?.configured === true
  const providerStatusText = (provider: any, ready = '运行中') => provider?.configured ? ready : '已启用，待配置'
  const atimeloggerAuthText = integrationStatus?.atimelogger?.pending_count
    ? `待备份 ${integrationStatus.atimelogger.pending_count} 条`
    : integrationStatus?.atimelogger?.failed_count
      ? `备份失败 ${integrationStatus.atimelogger.failed_count} 条`
      : atimeloggerVerified
    ? '最近记录已备份'
    : atimeloggerConfigured ? '需重新验证' : '未绑定'
  const sectionClass = 'overflow-hidden rounded-xl border border-gray-100 bg-white'

  return (
    <div className="min-h-full space-y-4 bg-[#FAFAFA] p-6">
      <section className={sectionClass}>
        <div className="px-4 py-2 text-xs font-semibold text-gray-400 uppercase border-b border-gray-50">服务连接</div>
        <ServiceRow
          label="aTimeLogger备份"
          status={atimeloggerAuthText}
          statusTone={atimeloggerVerified ? 'ok' : atimeloggerConfigured ? 'warn' : 'muted'}
          onStatusClick={integrationStatus?.atimelogger?.failed_count > 0 ? openAtimeloggerFailures : undefined}
          onConfigure={openOnlineServiceConfig}
          action={(
            <div className="flex flex-wrap justify-end gap-2 max-sm:justify-start">
            {(integrationStatus?.atimelogger?.pending_count > 0 || integrationStatus?.atimelogger?.failed_count > 0) && (
              <button type="button" onClick={retryAtimelogger} disabled={atimeloggerSaving} className={actionButtonClass}>
                重试备份
              </button>
            )}
            <button
              type="button"
              onClick={bindAtimelogger}
              disabled={atimeloggerSaving}
              className={actionButtonClass}
            >
              {atimeloggerSaving ? '登录中' : '登录'}
            </button>
            </div>
          )}
          controls={(
            <div className="grid min-w-0 grid-cols-[minmax(112px,1fr)_minmax(128px,1fr)] items-center gap-2 max-sm:grid-cols-1">
              <input
                name="atimelogger-username"
                type="text"
                inputMode="email"
                autoComplete="username"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                enterKeyHint="next"
                value={atimeloggerUsername}
                onChange={event => setAtimeloggerUsername(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); atimeloggerPasswordRef.current?.focus() } }}
                placeholder="账号"
                disabled={atimeloggerSaving}
                readOnly={false}
                className="h-9 min-w-0 rounded-lg border border-gray-100 bg-white px-3 text-sm outline-none focus:border-blue-300 disabled:bg-gray-50"
              />
              <input
                ref={atimeloggerPasswordRef}
                name="atimelogger-password"
                value={atimeloggerPassword}
                onChange={event => setAtimeloggerPassword(event.target.value)}
                placeholder={atimeloggerVerified ? '已验证，输入新密码可替换' : atimeloggerConfigured ? '已保存，输入密码重新验证' : '密码'}
                type="password"
                autoComplete="current-password"
                enterKeyHint="done"
                onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); bindAtimelogger() } }}
                disabled={atimeloggerSaving}
                readOnly={false}
                className="h-9 min-w-0 rounded-lg border border-gray-100 bg-white px-3 text-sm outline-none focus:border-blue-300 disabled:bg-gray-50"
              />
            </div>
          )}
        >
          {atimeloggerMessage && <div className="mt-2 text-xs text-gray-400">{atimeloggerMessage}</div>}
          {showAtimeloggerFailures && <div className="mt-3 rounded-lg border border-rose-100 bg-rose-50 p-3 text-xs text-rose-800">
            <div className="flex items-center justify-between gap-3 font-medium"><span>失败备份详情</span><button type="button" onClick={() => setShowAtimeloggerFailures(false)} className="text-rose-700 hover:underline">关闭</button></div>
            {atimeloggerFailuresLoading && <div className="mt-2">正在加载…</div>}
            {atimeloggerFailuresMessage && <div className="mt-2">{atimeloggerFailuresMessage}</div>}
            {!atimeloggerFailuresLoading && !atimeloggerFailuresMessage && (atimeloggerFailures.length
              ? <div className="mt-2 space-y-2">{atimeloggerFailures.map(item => <div key={item.stable_session_id} className="rounded bg-white/80 p-2 text-gray-700"><div className="font-medium">{item.session_id ? (item.session_summary || '未填写小结') : '原记录已不可用'}{item.category_name ? ` · ${item.category_name}` : ''}</div><div className="mt-1">{item.date || '日期未知'} {item.start_time || ''}–{item.end_time || ''}</div><div>原因：{item.last_error_code || '未知'} · {item.last_error_step || '步骤未知'} · 已尝试 {item.attempts || 0} 次</div><div>下次重试：{item.next_retry_at || '等待手动或后台重试'}</div></div>)}</div>
              : <div className="mt-2">当前没有仍处于失败状态的备份记录。</div>)}
          </div>}
        </ServiceRow>

        <div className="flex min-h-14 w-full items-center justify-between gap-4 border-b border-gray-50 px-4 py-2">
          <div><div className="font-medium text-gray-900">统计起始日期</div>{rewardRebuildMessage && <div className="mt-0.5 text-xs text-gray-400">{rewardRebuildMessage}</div>}</div>
          <div className="flex items-center gap-2">
            <input type="date" max={beijingToday} value={statisticsStartDateDraft} onChange={event => {
              const value = event.target.value
              if (resolveStatisticsStartDate(value).date === value && value <= beijingToday) setStatisticsStartDateDraft(value)
            }} className="bg-transparent text-sm text-gray-400 outline-none hover:text-gray-600 focus:text-blue-600" />
            <button type="button" disabled={rewardRebuildBusy} onClick={() => void rebuildRewardLedger(statisticsStartDateDraft)} className="text-xs text-blue-600 hover:text-blue-700 disabled:text-gray-300">{rewardRebuildBusy ? '处理中' : '重新拉取并重算金币'}</button>
          </div>
        </div>
        {rewardRebuildFailure && <RewardRebuildFailurePanel failure={rewardRebuildFailure} />}

        <button type="button" onClick={() => setShowGuide(true)} className="grid min-h-12 w-full grid-cols-[148px_minmax(0,1fr)_112px_64px] items-center gap-3 px-4 py-3 text-left active:bg-gray-50 md:hover:bg-gray-50 max-sm:grid-cols-1">
          <span className="font-medium text-gray-900">首次使用教程</span>
          <span />
          <span />
          <span className={actionButtonClass}>打开</span>
        </button>
        <button type="button" onClick={() => setShowSignOutConfirm(true)} className="flex h-12 w-full items-center justify-between gap-4 border-t border-gray-50 px-4 text-left text-rose-600 active:bg-rose-50 md:hover:bg-rose-50">
          <span className="font-medium">退出当前账号</span><span className="text-sm">›</span>
        </button>
      </section>


      {/* 计时设置 */}
      <section className={sectionClass}>
        <div className="flex h-12 items-center justify-between gap-4 border-b border-gray-50 px-4">
          <span className="font-medium text-gray-900">随机休息提醒频率</span>
          <select
            className="rounded bg-transparent text-sm text-gray-400 outline-none hover:text-gray-600 focus:text-blue-600 cursor-pointer text-right appearance-none"
            value={
              settings.study_time_min <= 0.5 && settings.study_time_max === 1 ? '0.5-1' :
              settings.study_time_min === 3 && settings.study_time_max === 5 ? '3-5' :
              settings.study_time_min === 6 && settings.study_time_max === 8 ? '6-8' :
              '5-7'
            }
            onChange={(e) => {
              const val = e.target.value
              let min = 5, max = 7
              if (val === '0.5-1') { min = 0.5; max = 1 }
              else if (val === '3-5') { min = 3; max = 5 }
              else if (val === '5-7') { min = 5; max = 7 }
              else if (val === '6-8') { min = 6; max = 8 }
              updateSetting('study_time_min', min)
              updateSetting('study_time_max', max)
            }}
          >
            <option value="0.5-1">30秒~1分钟（测试）</option>
            <option value="3-5">3~5 分钟</option>
            <option value="5-7">5~7 分钟</option>
            <option value="6-8">6~8 分钟</option>
          </select>
        </div>

        <div className="flex h-12 items-center justify-between gap-4 border-b border-gray-50 px-4">
          <span className="font-medium text-gray-900">输入/输出倒计时时长</span>
          <select
            className="rounded bg-transparent text-sm text-gray-400 outline-none hover:text-gray-600 focus:text-blue-600 cursor-pointer text-right appearance-none"
            value={String(settings.input_output_countdown_min || 90)}
            onChange={(e) => updateSetting('input_output_countdown_min', Number(e.target.value))}
          >
            <option value="2">2min（测试）</option>
            <option value="30">30min</option>
            <option value="60">60min</option>
            <option value="90">90min（默认）</option>
          </select>
        </div>

        <div className="flex h-12 items-center justify-between gap-4 border-b border-gray-50 px-4">
          <span className="font-medium text-gray-900">长休息时长</span>
          <select
            className="rounded bg-transparent text-sm text-gray-400 outline-none hover:text-gray-600 focus:text-blue-600 cursor-pointer text-right appearance-none"
            value={String(settings.long_break_duration || 20)}
            onChange={(e) => updateSetting('long_break_duration', Number(e.target.value))}
          >
            <option value="1">1min（测试）</option>
            <option value="5">5min</option>
            <option value="10">10min</option>
            <option value="20">20min（默认）</option>
          </select>
        </div>

        {desktopCapabilities.globalHotkeys && <>
          <div className="flex h-12 items-center justify-between gap-4 border-b border-gray-50 px-4">
            <span className="font-medium text-gray-900">切换计时</span><span className="text-sm text-gray-400">Alt+C</span>
          </div>
          <div className="flex h-12 items-center justify-between gap-4 border-b border-gray-50 px-4">
            <span className="font-medium text-gray-900">隐藏/显示</span><span className="text-sm text-gray-400">Alt+X</span>
          </div>
        </>}
        {desktopCapabilities.tray && (
          <div className="flex h-12 items-center justify-between gap-4 px-4">
            <span className="font-medium text-gray-900">托盘图标</span>
            <span className="text-sm text-gray-400">已启用</span>
          </div>
        )}
      </section>

      <NotificationSettings />

      {/* 声音设置 */}
      <section className={sectionClass}>
        <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-gray-500 border-b border-gray-50 bg-gray-50/50">声音设置</div>
        <AudioSelectRow label="专注开始" value={settings.audio_start || 'start_study'} onChange={v => updateSetting('audio_start', v)} onPlay={() => playPreview(settings.audio_start || 'start_study')} />
        <AudioSelectRow label="微休息开始" value={settings.audio_microBreak || 'start_short_break'} onChange={v => updateSetting('audio_microBreak', v)} onPlay={() => playPreview(settings.audio_microBreak || 'start_short_break')} />
        <AudioSelectRow label="微休息结束" value={settings.audio_endMicroBreak || 'end_short_break'} onChange={v => updateSetting('audio_endMicroBreak', v)} onPlay={() => playPreview(settings.audio_endMicroBreak || 'end_short_break')} />
        <AudioSelectRow label="长休息开始" value={settings.audio_startLongBreak || 'start_long_break'} onChange={v => updateSetting('audio_startLongBreak', v)} onPlay={() => playPreview(settings.audio_startLongBreak || 'start_long_break')} />
        <AudioSelectRow label="长休息结束" value={settings.audio_end || 'end_long_break'} onChange={v => updateSetting('audio_end', v)} onPlay={() => playPreview(settings.audio_end || 'end_long_break')} />
        <AudioSelectRow label="金币/胜利" value={settings.audio_coin || 'victory'} onChange={v => updateSetting('audio_coin', v)} onPlay={() => playPreview(settings.audio_coin || 'victory')} />
      </section>

      {/* 其他 */}
      <section className={sectionClass}>
        <SettingRow label="分类管理" value="›" onClick={onOpenCategoryManager} />
        <SettingRow label="导出完整配置" value="›" onClick={exportConfig} />
        <SettingRow label="导入完整配置" value="›" onClick={importConfig} />
      </section>

      <LoggingSettings serverUrl={selectedEnvironmentProfile.serverUrl} token={selectedEnvironmentProfile.authToken} environment={selectedEnvironment} isActive={activeEnvironment === selectedEnvironment} />

      {/* NumberSheet */}
      {editingKey && (
        <NumberSheet title="设置数值" value={editingValue}
          min={editingKey === 'study_time_min' ? 0 : (editingKey.endsWith('_interval') ? 5 : 1)}
          max={editingKey.endsWith('_interval') ? 86400 : 180}
          onSave={v => { updateSetting(editingKey, v); setEditingKey(null) }}
          onClose={() => setEditingKey(null)} />
      )}

      {showGuide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 backdrop-blur-sm">
          <div className="max-h-[82vh] w-full max-w-[560px] overflow-auto rounded-3xl bg-white p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between gap-4">
              <h3 className="text-lg font-bold text-gray-900">家人首次使用</h3>
              <button type="button" onClick={() => setShowGuide(false)} className="rounded-full bg-gray-100 px-3 py-1 text-sm font-semibold text-gray-500">关闭</button>
            </div>
            <div className="space-y-3 text-sm leading-6 text-gray-600">
              <p>新用户直接注册或登录即可开始使用。</p>
              <p>滴答清单、aTimeLogger 和大模型均为当前登录用户的私有配置；未配置时不会读取其他账号数据。</p>
              <p>S3 容灾备份由服务管理者统一配置，普通账号不能查看或修改全库备份凭据。</p>
              <div className="mt-4 flex justify-end border-t border-gray-100 pt-4 max-sm:flex-col">
                <button
                  type="button"
                  onClick={openOnlineServiceConfig}
                  className="h-11 rounded-xl bg-blue-600 px-6 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-500 active:bg-blue-700"
                >
                  我的服务配置
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showSignOutConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 backdrop-blur-sm">
          <div className="w-full max-w-[360px] rounded-3xl bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-gray-900">退出当前账号？</h3>
            <p className="mt-2 text-sm leading-6 text-gray-500">将退出 {selectedEnvironmentProfile.username || '当前账号'}，不会删除本地或服务端数据。</p>
            <div className="mt-6 grid grid-cols-2 gap-3"><button type="button" disabled={signingOut} onClick={() => setShowSignOutConfirm(false)} className="h-11 rounded-2xl bg-gray-100 text-sm font-semibold text-gray-600">取消</button><button type="button" disabled={signingOut} onClick={signOut} className="h-11 rounded-2xl bg-rose-600 text-sm font-bold text-white disabled:opacity-60">{signingOut ? '正在退出...' : '退出账号'}</button></div>
          </div>
        </div>
      )}

    </div>
  )
})

SettingsPage.displayName = 'SettingsPage'
