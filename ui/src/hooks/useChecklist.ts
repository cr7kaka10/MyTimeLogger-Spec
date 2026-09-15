import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { TaskItem } from '../types'
import type { TickTickTaskCommandResult } from '@core/ApiClient'
import { formatSyncProgress, getCurrentTimerClient, getDatabase, syncChecklistNow, syncNow, pushChecklistOnly } from '../db'
import { getElectronApi } from '../platform'
import { dateToShanghaiDateString, formatTickTickDueDate, normalizeShanghaiDateTime } from '../utils/shanghaiDate'
import { parseBeijingDateTimeMs } from '@core/BeijingTime'

export interface UseChecklistReturn {
  tasks: TaskItem[]
  isLoading: boolean
  syncStatus: string
  unknownTaskRequestId: string | null
  addTask: (title: string, dueDate: string) => Promise<void>
  completeTask: (task: TaskItem) => Promise<void>
  deleteTask: (taskId: string) => Promise<void>
  updateTaskTitle: (taskId: string, title: string) => Promise<void>
  updateTask: (task: TaskItem, patch: { title?: string; startDate?: string | null; dueDate?: string | null }) => Promise<TickTickTaskCommandResult | null>
  refreshFromTickTick: (forceRefresh?: boolean) => Promise<void>
  updateTaskPriority: (taskId: string, priority: number) => Promise<void>
  pushOnly: () => Promise<void>
  reconcileUnknownTask: () => Promise<void>
}

const formatSyncError = (raw: string): string => {
  const value = String(raw || '').trim()
  if (!value) return '未知错误'
  if (value.startsWith('tasks:')) return `任务拉取失败：${value.slice(6) || '未知错误'}`
  if (value.startsWith('habits:')) return `习惯拉取失败：${value.slice(7) || '未知错误'}`
  if (value === 'push_failed') return '本地推送失败'
  if (value === 'sync_failed') return '同步未完成，请重试'
  if (value === 'auth_expired') return '登录已失效，请重新登录'
  if (value === 'request_timeout') return '连接服务端超时，请检查局域网和服务状态'
  if (value === 'server_unreachable') return '无法连接服务端，请确认项目已启动、手机与电脑在同一 Wi-Fi，服务监听 0.0.0.0:8000 且 Windows 防火墙已放行'
  if (value === 'server_error') return '服务端返回错误，请检查服务日志后重试'
  if (value.includes('NOT NULL constraint failed')) return `服务端字段不兼容：${value}`
  if (value.includes('认证失败')) return value
  if (value === 'pull_failed') return '服务端拉取失败'
  if (value === 'ticktick_refresh_failed') return '滴答清单刷新失败'
  if (value === 'sync_worker_not_ready') return '同步服务未就绪'
  if (value === 'ticktick_not_configured') return '服务端 TickTick token 未配置，请检查部署私有配置'
  if (value === 'local_merge_failed') return '本地合并失败'
  if (value === 'local_merge_backoff') return '上一轮本地合并失败，等待自动重试'
  return value
}

const formatSyncDiagnostics = (result: { merged?: number; diagnostics?: Record<string, any>; error?: string }): string => {
  const diagnostics = result.diagnostics || {}
  const progress = formatSyncProgress(result as any)
  const withProgress = (message: string) => progress ? `${progress} · ${message}` : message
  const providerRefresh = diagnostics.provider_refresh || {}
  if (providerRefresh.status === 'degraded') {
    const retryAt = String(providerRefresh.retry_at || '').replace('T', ' ').slice(0, 16)
    return `本地已同步，外部任务源部分更新，稍后重试${retryAt ? ` · 下次 ${retryAt}` : ''}`
  }
  const providerErrors = Array.isArray(providerRefresh.errors) ? providerRefresh.errors.filter(Boolean) : []
  const errors = Array.isArray(diagnostics.errors) ? diagnostics.errors.filter(Boolean) : []
  const allErrors = [...providerErrors, ...errors]
  if (result.error && allErrors.length === 0) return withProgress(formatSyncError(result.error))
  if (allErrors.length > 0) return withProgress(allErrors.map(formatSyncError).join('；'))

  const tasks = diagnostics.tasks || providerRefresh.tasks || {}
  const habits = diagnostics.habits || providerRefresh.habits || {}
  const activeTasks = Number(tasks.active_tasks ?? 0)
  const completedTasks = Number(tasks.completed_tasks ?? 0)
  const habitsCount = Number(habits.habits ?? habits.active_habits ?? 0)
  const checkins = Number(habits.checkins ?? habits.habit_checkins ?? 0)
  const merged = Number(result.merged ?? 0)
  const protocol = diagnostics.protocol ? ` · ${diagnostics.protocol}` : ''
  const range = typeof diagnostics.from_version === 'number' || typeof diagnostics.to_version === 'number'
    ? ` · v${diagnostics.from_version ?? '?'}→${diagnostics.to_version ?? '?'}`
    : ''

  return withProgress(`任务 新${activeTasks}/完${completedTasks} · 习惯 ${habitsCount}/打卡${checkins} · 合并${merged}${range}${protocol}`)
}

const isStaleSyncTime = (value: string | null | undefined, maxAgeMs = 5 * 60 * 1000): boolean => {
  if (!value) return true
  const time = parseBeijingDateTimeMs(value)
  if (!Number.isFinite(time)) return true
  return Date.now() - time > maxAgeMs
}

const parseTaskTags = (value: any): string[] => {
  if (Array.isArray(value)) return value.map(String).filter(Boolean)
  if (value == null || value === '') return []
  if (typeof value !== 'string') return []
  const text = value.trim()
  if (!text) return []
  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean)
    if (typeof parsed === 'string') return parsed ? [parsed] : []
    return []
  } catch {
    return text.split(',').map(tag => tag.trim()).filter(Boolean)
  }
}

export const useChecklist = (): UseChecklistReturn => {
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [syncStatus, setSyncStatus] = useState('就绪')
  const [unknownTaskRequestId, setUnknownTaskRequestId] = useState<string | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const syncSeqRef = useRef(0)

  const beginSyncStatus = useCallback((nextStatus?: string): number => {
    const seq = syncSeqRef.current + 1
    syncSeqRef.current = seq
    if (nextStatus) setSyncStatus(nextStatus)
    return seq
  }, [])

  const setLatestSyncStatus = useCallback((seq: number, nextStatus: string) => {
    if (syncSeqRef.current === seq) {
      setSyncStatus(nextStatus)
    } else {
      console.info('[useChecklist] ignore stale sync status', { seq, latest: syncSeqRef.current, nextStatus })
    }
  }, [])

  const formatResultStatus = useCallback((result: { ok?: boolean; merged?: number; diagnostics?: Record<string, any>; error?: string }) => {
    const detail = formatSyncDiagnostics(result)
    if (!result.ok) return `同步失败 · ${detail}`
    return detail.startsWith('本地已同步，外部任务源部分更新') ? detail : `已同步 · ${detail}`
  }, [])

  const loadLocal = useCallback(async () => {
    try {
      const db = await getDatabase()
      
      // 查询所有任务（不指定日期，返回全部）
      const raw = db.getChecklistTasks()
      console.log('=== useChecklist.loadLocal ===')
      console.log('从数据库查询到的任务数:', raw.length)

      setTasks(raw.map((r: any) => {
        let source: any = {}
        try { source = JSON.parse(r.raw_json || '{}') } catch { source = {} }
        const rewardCfg = db.getItemReward('task', r.ticktick_id || String(r.id), 0.1)
        const dueDate = normalizeShanghaiDateTime(r.due_date || '')
        const dueAt = dueDate ? new Date(dueDate.replace(' ', 'T') + '+08:00') : null
        return {
          id: r.ticktick_id || String(r.id),
          title: r.title,
          priority: r.priority ?? 0,
          status: r.status ?? 0,
          tags: parseTaskTags(r.tags),
          due_date: dueDate,
          due_date_full: formatTickTickDueDate(dueDate),
          is_overdue: dueAt ? dueAt < new Date() : false,
          reward_coins: rewardCfg.reward,
          penalty_coins: rewardCfg.penalty,
          project_id: source.projectId || r.project_id || '',
          start_date: source.startDate ?? null,
          provider_due_date: source.dueDate ?? null,
          time_zone: source.timeZone || 'Asia/Shanghai',
          is_all_day: Boolean(source.isAllDay),
          repeat_flag: source.repeatFlag || '',
          source: r.source || (String(r.id).startsWith('local_') ? 'local' : 'ticktick'),
        }
      }))
    } catch (error) {
      console.error('[useChecklist] loadLocal failed:', error)
      setTasks([])
    } finally {
      setIsLoading(false)
    }
  }, []) // 移除 selectedDate 依赖

  // 启动时只加载本地数据；页面入口负责触发一次同步，避免多个自动同步竞争同一个状态。
  useEffect(() => {
    loadLocal()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (refreshTrigger > 0) loadLocal()
  }, [loadLocal, refreshTrigger])

  useEffect(() => {
    const handleSyncPullComplete = () => {
      console.info('[useChecklist] sync-pull-complete: reload local tasks')
      loadLocal()
      setSyncStatus(prev => {
        if (prev.startsWith('同步中')) return prev
        const now = new Date()
        return `已同步 · 后台更新 · ${now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })}`
      })
    }

    window.addEventListener('sync-pull-complete', handleSyncPullComplete)
    return () => window.removeEventListener('sync-pull-complete', handleSyncPullComplete)
  }, [loadLocal])

  const pullServerChanges = useCallback(async (reason: string) => {
    const seq = beginSyncStatus('同步中...')
    try {
      const result = await syncNow({ reason })
      if (!result.ok) {
        setLatestSyncStatus(seq, `同步失败 · ${formatSyncDiagnostics(result)}`)
        return
      }
      await loadLocal()
      setLatestSyncStatus(seq, `已同步 · ${formatSyncDiagnostics(result)}`)
    } catch (error: any) {
      setLatestSyncStatus(seq, `同步失败 · ${formatSyncError(error?.message || error)}`)
    }
  }, [beginSyncStatus, loadLocal, setLatestSyncStatus])

  useEffect(() => {
    let lastPullAt = 0
    const maybePull = (reason: string) => {
      const now = Date.now()
      if (now - lastPullAt < 10_000) return
      lastPullAt = now
      pullServerChanges(reason).catch(error => {
        console.error('[useChecklist] foreground pull failed:', error)
      })
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') maybePull('checklist-visible')
    }
    const handleFocus = () => maybePull('checklist-focus')

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('focus', handleFocus)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('focus', handleFocus)
    }
  }, [pullServerChanges])

  const runTaskCommand = useCallback(async (operation: 'create' | 'update' | 'delete', payload: Record<string, any>): Promise<TickTickTaskCommandResult | null> => {
    const request_id = globalThis.crypto?.randomUUID?.() || `task-${Date.now()}-${Math.random().toString(36).slice(2)}`
    const client = getCurrentTimerClient()
    if (!client?.commandTickTickTask) { setSyncStatus('操作失败 · 服务端连接未就绪'); return null }
    setSyncStatus('处理中 · 正在确认滴答清单…')
    const response = await client.commandTickTickTask({ request_id, operation, ...payload })
    const result = response.data
    if (!response.ok || !result || result.status !== 'confirmed') {
      if (result?.status === 'unknown') setUnknownTaskRequestId(request_id)
      setSyncStatus(result?.status === 'unknown' ? '结果未知 · 请点击核对，勿重复创建' : result?.error_code === 'task_timezone_unavailable' ? '操作失败 · 服务器缺少任务时区数据，请稍后重试' : '操作失败 · 未确认同步到滴答清单')
      return result || null
    }
    setUnknownTaskRequestId(null)
    await pullServerChanges('checklist-task-command')
    setSyncStatus('已同步至滴答清单')
    return result
  }, [pullServerChanges])

  const addTask = useCallback(async (title: string, dueDate: string) => {
    const db = await getDatabase()
    db.addTask(title, dueDate)
    setRefreshTrigger(previous => previous + 1)
    const seq = beginSyncStatus('同步中 · 原生任务已保存')
    const result = await syncChecklistNow({ reason: 'checklist-local-task-create' })
    setLatestSyncStatus(seq, formatResultStatus(result))
  }, [beginSyncStatus, formatResultStatus, setLatestSyncStatus])

  const reconcileUnknownTask = useCallback(async () => {
    if (!unknownTaskRequestId) return
    const client = getCurrentTimerClient()
    if (!client?.commandTickTickTask) { setSyncStatus('操作失败 · 服务端连接未就绪'); return }
    setSyncStatus('处理中 · 正在核对滴答清单…')
    const response = await client.commandTickTickTask({ request_id: unknownTaskRequestId, operation: 'reconcile' })
    if (!response.ok || response.data?.status !== 'confirmed') { setSyncStatus('结果仍未知 · 请在滴答清单确认后再试'); return }
    setUnknownTaskRequestId(null)
    await pullServerChanges('checklist-task-reconcile')
    setSyncStatus('已同步至滴答清单')
  }, [pullServerChanges, unknownTaskRequestId])

  const completeTask = useCallback(async (task: TaskItem) => {
    const db = await getDatabase()
    const taskId = task.id

    if (task.status === 2) {
      db.updateTaskStatus(taskId, 0)
      setRefreshTrigger(prev => prev + 1)
      const seq = beginSyncStatus('同步中...')
      const result = await syncChecklistNow({ reason: 'checklist-task-uncomplete' })
      setLatestSyncStatus(seq, formatResultStatus(result))
      return
    }

    const rewardCfg = db.getItemReward('task', taskId, 0.1)
    const coins = rewardCfg.reward

    // 本地完成 + 服务端同步（服务端会推到滴答清单）
    db.completeTask(taskId, task.title, coins)
    setRefreshTrigger(prev => prev + 1)
    // 三端同步：推送到服务端 + 拉取最新
    const seq = beginSyncStatus('同步中...')
    const result = await syncChecklistNow({ reason: 'checklist-task-complete' })
    setLatestSyncStatus(seq, formatResultStatus(result))
  }, [beginSyncStatus, formatResultStatus, setLatestSyncStatus])

  const deleteTask = useCallback(async (taskId: string) => { await runTaskCommand('delete', { task_id: taskId }) }, [runTaskCommand])
  const updateTask = useCallback(async (task: TaskItem, patch: { title?: string; startDate?: string | null; dueDate?: string | null }) => {
    return runTaskCommand('update', {
      task_id: task.id, project_id: task.project_id, patch,
      expected: { title: task.title, startDate: task.start_date, dueDate: task.provider_due_date, isAllDay: task.is_all_day, timeZone: task.time_zone, repeatFlag: task.repeat_flag },
    })
  }, [runTaskCommand])
  const updateTaskTitle = useCallback(async (taskId: string, title: string) => {
    const task = tasks.find(item => item.id === taskId)
    if (task) await updateTask(task, { title })
  }, [tasks, updateTask])

  const updateTaskPriority = useCallback(async (taskId: string, priority: number) => {
    const db = await getDatabase()
    db.updateTaskPriority(taskId, priority)
    setRefreshTrigger(prev => prev + 1)
    const seq = beginSyncStatus('同步中...')
    const result = await syncChecklistNow({ reason: 'checklist-task-priority' })
    setLatestSyncStatus(seq, formatResultStatus(result))
  }, [beginSyncStatus, formatResultStatus, setLatestSyncStatus])

  // 刷新按钮：先 flush 推本地→服务端，再 pull 拉服务端→本地，最后刷新 UI
  const refreshFromTickTick = useCallback(async (forceRefresh = true) => {
    const seq = beginSyncStatus('同步中...')
    try {
      const db = await getDatabase()
      const shouldRefreshProvider = forceRefresh || isStaleSyncTime(db.getConfig('ticktick_to_server_synced_at'))
      const result = await syncChecklistNow({
        providerRefresh: shouldRefreshProvider,
        reason: forceRefresh ? 'checklist-refresh' : 'checklist-enter',
      })
      if (!result.ok) {
        setLatestSyncStatus(seq, `同步失败 · ${formatSyncDiagnostics(result)}`)
        return
      }
      // Electron 使用 better-sqlite3 直连磁盘，此调用保持兼容。
      await getElectronApi()?.reloadDb?.()
      await loadLocal()
      const now = new Date()
      setLatestSyncStatus(seq, `${formatResultStatus(result)} · ${now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })}`)
    } catch (e: any) {
      setLatestSyncStatus(seq, `同步失败 · ${formatSyncError(e?.message || e)}`)
    }
  }, [beginSyncStatus, formatResultStatus, loadLocal, setLatestSyncStatus])

  // 独立 Push 按钮：仅推送本地 Outbox 到服务端（服务端自动同步到 TickTick）
  const pushOnlyAction = useCallback(async () => {
    const seq = beginSyncStatus('推送中...')
    console.info('[useChecklist] Push button clicked')
    try {
      const result = await pushChecklistOnly()
      if (!result.ok) {
        console.error('[useChecklist] Push failed', result.error)
        setLatestSyncStatus(seq, `推送失败 · ${formatSyncError(result.error || 'unknown')}`)
        return
      }
      
      if (result.merged === 0 && result.pending === 0) {
        console.info('[useChecklist] Push skipped: no pending changes')
        setLatestSyncStatus(seq, '本地无变更，跳过推送')
        return
      }
      
      const now = new Date()
      console.info('[useChecklist] Push success', { merged: result.merged, pending: result.pending, stats: result.statsStr })
      const statsSuffix = result.statsStr ? ` · ${result.statsStr}` : ''
      setLatestSyncStatus(seq, `已推送 · ${now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })}${statsSuffix}`)
    } catch (e: any) {
      console.error('[useChecklist] Push exception', e)
      setLatestSyncStatus(seq, `推送失败 · ${formatSyncError(e?.message || e)}`)
    }
  }, [beginSyncStatus, setLatestSyncStatus])

  return useMemo(() => ({
    tasks, isLoading, syncStatus, unknownTaskRequestId,
    addTask, completeTask, deleteTask, updateTaskTitle, updateTask,
    refreshFromTickTick, updateTaskPriority,
    pushOnly: pushOnlyAction, reconcileUnknownTask,
  }), [tasks, isLoading, syncStatus, unknownTaskRequestId, addTask, completeTask, deleteTask, updateTaskTitle, updateTask, refreshFromTickTick, updateTaskPriority, pushOnlyAction, reconcileUnknownTask])
}
