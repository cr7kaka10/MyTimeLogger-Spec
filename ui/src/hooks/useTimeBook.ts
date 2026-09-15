// ui/src/hooks/useTimeBook.ts
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { SessionEditData, SessionRecord } from '../types'
import { deleteServerSession, formatSyncProgress, getDatabase, pullTimeBookSessionVisibility, syncAfterDateSwitch, syncNow, flushSync, type SyncNowResult } from '../db'
import { runLocalFirstRefresh } from '@core/LocalFirstRefresh'
import { formatBeijingDate, parseBeijingDateTimeMs } from '@core/BeijingTime'
import { sessionBusinessDate } from '@core/SessionBusinessDate'
import { platformFetch } from '../platform/fetch'
import type { ManagementPlanRuntime } from './useManagementPlan'
import { useChecklistTaskSubmission, type ChecklistTaskSubmission } from './useChecklistTaskSubmission'

const resolveEditDurationSeconds = (startTime: string, endTime: string): number => {
  const start = parseBeijingDateTimeMs(startTime)
  const end = parseBeijingDateTimeMs(endTime)
  return Number.isFinite(start) && Number.isFinite(end) && end >= start
    ? Math.floor((end - start) / 1000)
    : 0
}

const isInternalExerciseKey = (value: string) => /^(?:sc|ex)-\d{4}-\d{2}-\d{2}-(?:\d+|[gr]-\d+)$/.test(value)

export const resolveExerciseCheckinName = (checkin: any, db: any, date: string): string => {
  const itemKey = String(checkin.item_key || '').trim()
  const savedName = String(checkin.item_name || '').trim()
  if (savedName && !isInternalExerciseKey(savedName)) return savedName
  const planItem = checkin.plan_item_id && db.allRaw?.('SELECT name FROM exercise_plan_items WHERE id = ?', [checkin.plan_item_id])?.[0]
  if (String(planItem?.name || '').trim()) return String(planItem.name).trim()
  const scheduleIndex = itemKey.match(/^sc-\d{4}-\d{2}-\d{2}-(\d+)$/)?.[1]
  if (scheduleIndex !== undefined && typeof db.getExercisePlanDefinition === 'function') {
    const day = ['日', '周一', '周二', '周三', '周四', '周五', '六'][new Date(`${date}T00:00:00Z`).getUTCDay()]
    const definition = db.getExercisePlanDefinition(checkin.plan_version)
    const rows = day === '六' ? definition?.restSchedule : day === '日' ? [...(definition?.restSchedule || []), definition?.sundayExtra] : definition?.weekdaySchedule
    const resolved = String(rows?.[Number(scheduleIndex)]?.item || '').trim()
    if (resolved) return resolved
  }
  return '运动打卡项'
}

const formatSyncError = (value: string): string => {
  if (value === 'local_merge_failed') return '本地同步合并失败，请查看后台日志'
  if (value === 'local_merge_backoff') return '上一轮本地合并失败，等待自动重试'
  if (value === 'auth_expired') return '登录已失效，请重新登录'
  if (value === 'request_timeout') return '连接服务端超时，请检查局域网和服务状态'
  if (value === 'server_unreachable') return '无法连接服务端，请确认项目已启动、手机与电脑在同一 Wi-Fi，服务监听 0.0.0.0:8000 且 Windows 防火墙已放行'
  if (value === 'server_error') return '服务端返回错误，请检查服务日志后重试'
  if (value === 'local_outbox_conflict') return '本地还有待推送变更，暂未合并云端记录'
  if (value === 'pull_failed') return '服务端拉取失败'
  if (value === 'push_failed') return '本地记录已显示，远端同步失败，请稍后重试'
  if (value === 'sync_worker_not_ready') return '同步服务未就绪'
  return value || '增量同步失败'
}
const formatSyncRequestTrace = (result: SyncNowResult): string => {
  if (result.error !== 'server_error') return ''
  const diagnostics = result.diagnostics || {}
  const requestId = String(diagnostics.request_id || diagnostics.push?.request_id || '').trim()
  return requestId ? `请求 ${requestId.slice(0, 8)}` : ''
}

export const formatSyncFailure = (result: SyncNowResult): string =>
  [formatSyncError(result.error || '增量同步失败'), formatSyncProgress(result), formatSyncRequestTrace(result)].filter(Boolean).join(' · ')

export interface UseTimeBookReturn {
  sessions: SessionRecord[]
  selectedDate: string
  setSelectedDate: (d: string) => void
  resetToToday: () => void
  availableDates: string[]
  markedDates: Set<string>
  categories: Array<{ id: number; name: string; icon?: string; color?: string }>
  deleteSession: (id: string | number) => void
  updateSession: (id: string | number, fields: Partial<SessionRecord>) => void
  saveSession: (data: SessionEditData) => void
  todaySummary: { groupName: string; minutes: number; color: string }[]
  diary: { morning_diary?: string; evening_diary?: string; morning_diary_written_at?: string; evening_diary_written_at?: string; report_status?: number; morning_diary_reward_status?: string; morning_diary_reward_amount?: number; morning_diary_reward_reason?: string; evening_diary_reward_status?: string; evening_diary_reward_amount?: number; evening_diary_reward_reason?: string } | null
  saveDiary: (type: 'morning' | 'evening', content: string) => void
  sleepStatusMap: Record<string, number>
  syncError: string
  flashCards: FlashCard[]
  timelineEntries: TimeBookTimelineEntry[]
  flashError: string
  taskRecommendations: FlashTaskRecommendation[]
  taskSubmissions: Record<string, ChecklistTaskSubmission>
  createRecommendedTask: (recommendation: FlashTaskRecommendation) => void
  ignoreRecommendedTask: (recommendation: FlashTaskRecommendation) => Promise<void>
  submitFlashClassificationFeedback: (flashCardId: string, label: FlashClassificationLabel) => Promise<void>
  loadFlashProcessingLogs: (flashCardId: string) => Promise<FlashProcessingLog[]>
  correctFlashPolish: (data: FlashPolishCorrectionInput) => Promise<FlashCard>
  loadFlashSkillHistory: (cursor?: string | null) => Promise<FlashSkillHistoryPage>
  recordFlashCard: (text: string) => Promise<string | undefined>
  saveFlashCard: (data: FlashCardInput) => Promise<FlashCard>
  deleteFlashCard: (id: string) => Promise<void>
}

export interface FlashCard { id: string; occurred_at: string; original_text: string; polished_text?: string | null; diary_mood?: string | null; diary_content?: string | null; task_recommendations_json?: string | null; analysis_status: string; analysis_error_code?: string | null; analysis_draft_id?: string | null }
export interface FlashCardInput { id?: string; occurred_at: string; original_text: string }
export interface FlashPolishCorrectionInput { id: string; occurred_at: string; corrected_text: string }
export type FlashClassificationLabel = 'todo' | 'mood'
export interface FlashTaskRecommendation { id: string; flash_card_id: string; title: string; reason: string; status: 'pending' | 'added' | 'ignored'; creation_mode?: 'direct' | 'confirm'; local_task_id?: string | null; superseded_at?: string | null }
export interface FlashProcessingLog { id: string; input_text: string; prompt_snapshot: string; prompt_version: string; raw_output?: string | null; normalized_output?: string | null; status: string; error_code?: string | null; started_at: string; completed_at?: string | null }
export interface FlashSkillChangeEvent { id: string; version: string; parent_version?: string | null; event_type: string; rule_diff: { added?: string[]; modified?: Array<{ from: string; to: string }>; removed?: string[] }; sample_summary: { classification?: number; polish?: number }; evaluation_summary: string; candidate_status?: string | null; created_at: string }
export interface FlashSkillHistoryPage { events: FlashSkillChangeEvent[]; next_cursor?: string | null }
export type TimeBookTimelineEntry =
  | { id: string; at: string; kind: 'flash'; card: FlashCard }
  | { id: string; at: string; kind: 'diary'; diaryType: 'morning' | 'evening'; diaryContent: string }
  | { id: string; at: string; kind: 'session'; session: SessionRecord }
  | { id: string; at: string; kind: 'checkin'; checkinSource: 'habit' | 'exercise'; checkinName: string; checkinStatus: 'success' | 'failure' }

export const buildTimeBookTimeline = (selectedDate: string, sessions: SessionRecord[], flashCards: FlashCard[], diary: UseTimeBookReturn['diary'], checkins: TimeBookTimelineEntry[] = []): TimeBookTimelineEntry[] => [
  ...sessions.map(session => ({ id: `session-${session.id}`, at: session.start_time, kind: 'session' as const, session })),
  ...flashCards.map(card => ({ id: `flash-${card.id}`, at: card.occurred_at, kind: 'flash' as const, card })),
  ...(['morning', 'evening'] as const).flatMap(diaryType => {
    const diaryContent = diary?.[`${diaryType}_diary`]
    const writtenAt = diary?.[`${diaryType}_diary_written_at`]
    return diaryContent?.trim() && writtenAt ? [{ id: `diary-${diaryType}`, at: writtenAt, kind: 'diary' as const, diaryType, diaryContent }] : []
  }),
  ...checkins,
].sort((left, right) => parseBeijingDateTimeMs(left.at) - parseBeijingDateTimeMs(right.at))

const beijingDateTime = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'medium', hour12: false }).format(new Date()).replace('T', ' ')

export const useTimeBook = (isActive = true, runtime?: ManagementPlanRuntime): UseTimeBookReturn => {
  const [selectedDate, setSelectedDate] = useState(() => formatBeijingDate())
  const [sessions, setSessions] = useState<SessionRecord[]>([])
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [categories, setCategories] = useState<Array<{ id: number; name: string; icon?: string; color?: string }>>([])
  const [diary, setDiary] = useState<UseTimeBookReturn['diary']>(null)
  const [sleepStatusMap, setSleepStatusMap] = useState<Record<string, number>>({})
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [syncError, setSyncError] = useState('')
  const [flashCards, setFlashCards] = useState<FlashCard[]>([])
  const [flashError, setFlashError] = useState('')
  const [taskRecommendations, setTaskRecommendations] = useState<FlashTaskRecommendation[]>([])
  const [checkinEntries, setCheckinEntries] = useState<TimeBookTimelineEntry[]>([])
  const syncPromise = useRef<Promise<void> | null>(null)

  const loadLocal = useCallback(async () => {
    const db = await getDatabase()
    setSessions(db.getSessionsByDate(selectedDate) as any[])
    setAvailableDates(db.getAvailableDates() ?? [])
    setCategories(db.getCategories().map((c: any) => ({ id: c.id, name: c.name, icon: c.icon, color: c.color })))
    if (typeof db.getDiaryForDate === 'function') setDiary(db.getDiaryForDate(selectedDate))
    if (typeof db.getSleepStatusMap === 'function') setSleepStatusMap(db.getSleepStatusMap())

    if (typeof db.getFlashCards === 'function') {
      const nextDateObj = new Date(selectedDate)
      nextDateObj.setDate(nextDateObj.getDate() + 1)
      const nextDateStr = nextDateObj.toISOString().split('T')[0]
      const cards = (db.getFlashCards(`${selectedDate} 00:00:00`, `${nextDateStr} 00:00:00`) || []) as FlashCard[]
      setFlashCards(cards)
      setTaskRecommendations(typeof db.getFlashTaskRecommendations === 'function' ? db.getFlashTaskRecommendations(cards.map(card => card.id)) as FlashTaskRecommendation[] : [])
    }
    const toAt = (date: unknown, time: unknown) => {
      const value = String(time || '').trim()
      return /^\d{4}-\d{2}-\d{2}/.test(value) ? value : value && date ? `${date} ${value}` : ''
    }
    const habitNames = new Map((db.getHabits?.() || []).map((habit: any) => [String(habit.id), String(habit.name || '')]))
    const habitEntries = (db.getTodayCheckins?.(selectedDate) || []).flatMap((checkin: any) => {
      const status = Number(checkin.status)
      const at = toAt(checkin.checkin_date || selectedDate, status === 1 ? checkin.updated_at || checkin.checkin_time : checkin.checkin_time || checkin.updated_at)
      const name = String(checkin.habit_name || habitNames.get(String(checkin.habit_id)) || '')
      return at && name && (status === 2 || status === 1) ? [{ id: `habit-checkin-${checkin.id}`, at, kind: 'checkin' as const, checkinSource: 'habit' as const, checkinName: name, checkinStatus: status === 2 ? 'success' as const : 'failure' as const }] : []
    })
    const exerciseEntries = (db.allRaw('SELECT * FROM exercise_checkins WHERE date = ?', [selectedDate]) || []).flatMap((checkin: any) => {
      const status = Number(checkin.status), at = toAt(selectedDate, checkin.completed_time)
      const name = resolveExerciseCheckinName(checkin, db, selectedDate)
      return at && name && (status === 1 || status === -1) ? [{ id: `exercise-checkin-${checkin.id}`, at, kind: 'checkin' as const, checkinSource: 'exercise' as const, checkinName: name, checkinStatus: status === 1 ? 'success' as const : 'failure' as const }] : []
    })
    setCheckinEntries([...habitEntries, ...exerciseEntries])
  }, [selectedDate])

  const flashRequest = useCallback(async (path: string, init: RequestInit = {}) => {
    if (!runtime?.serverUrl || !runtime.authToken) throw new Error('请先连接服务端')
    const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken, ...(init.headers || {}) },
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) throw new Error(body?.detail?.message || body?.detail?.message || body?.message || '闪念操作失败')
    return body
  }, [runtime?.authToken, runtime?.serverUrl])

  const loadFlashCards = useCallback(async () => {
    await loadLocal()
  }, [loadLocal])
  const { submissions: taskSubmissions, submit: submitTask } = useChecklistTaskSubmission(runtime, loadLocal)

  useEffect(() => {
    void loadLocal()
  }, [loadLocal, refreshTrigger])

  useEffect(() => { void loadFlashCards() }, [loadFlashCards])

  const processingFlashKey = flashCards
    .filter(card => card.analysis_status === 'pending' || card.analysis_status === 'processing')
    .map(card => card.id).sort().join(',')
  useEffect(() => {
    if (!isActive || !processingFlashKey) return
    let attempts = 0
    const timer = window.setInterval(() => {
      attempts += 1
      void syncNow({ reason: 'server-change-followup' }).then(() => loadLocal()).catch(() => {})
      if (attempts >= 5) window.clearInterval(timer)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [processingFlashKey, isActive, loadLocal])

  useEffect(() => {
    if (!isActive) return
    if (!syncPromise.current) {
      syncPromise.current = runLocalFirstRefresh(loadLocal, async () => {
        const result = await pullTimeBookSessionVisibility()
        if (!result.ok) throw new Error(formatSyncFailure(result))
      }).then(setSyncError).finally(() => {
        syncPromise.current = null
      })
    }
  }, [isActive, loadLocal])

  const saveDiary = useCallback((type: 'morning' | 'evening', content: string) => {
    getDatabase().then(db => {
      if (typeof db.saveSleepData === 'function') {
        const currentDiary = db.getDiaryForDate(selectedDate) || {}
        db.saveSleepData(selectedDate, {
          ...currentDiary,
          [type === 'morning' ? 'morning_diary' : 'evening_diary']: content,
        })
        setRefreshTrigger(prev => prev + 1)
      }
    })
  }, [selectedDate])

  const markedDates = useMemo(() => new Set(availableDates), [availableDates])

  const deleteSession = useCallback((id: string | number) => {
    getDatabase().then(async db => {
      try {
        if (!await deleteServerSession(id)) throw new Error('delete_failed')
        db.deleteSession(id)
        setSyncError('')
        setRefreshTrigger(prev => prev + 1)
      } catch {
        setSyncError('删除未同步到服务端，本地记录已保留，请稍后重试')
      }
    })
  }, [])

  const updateSession = useCallback((id: string | number, fields: Partial<SessionRecord>) => {
    getDatabase().then(db => {
      db.updateSession(id, fields as any)
      setRefreshTrigger(prev => prev + 1)
    })
  }, [])

  const saveSession = useCallback((data: SessionEditData) => {
    getDatabase().then(db => {
      const businessDate = sessionBusinessDate(data.start_time, data.end_time, formatBeijingDate())
      if (data.id) {
        const durationSeconds = data.net_duration_seconds ?? resolveEditDurationSeconds(data.start_time, data.end_time)
        db.updateSession(data.id, {
          start_time: data.start_time,
          end_time: data.end_time,
          net_duration_minutes: data.net_duration_minutes,
          net_duration_seconds: durationSeconds,
          date: businessDate,
          category_id: data.category_id,
          session_summary: data.session_summary,
        } as any)
      } else {
        db.addManualSession({
          startTime: data.start_time,
          endTime: data.end_time,
          netDurationMinutes: data.net_duration_minutes,
          date: businessDate,
          categoryId: data.category_id,
          sessionSummary: data.session_summary,
        })
      }
      setSelectedDate(businessDate)
      setRefreshTrigger(prev => prev + 1)
    })
  }, [])

  const changeSelectedDate = useCallback((date: string) => {
    setSelectedDate(date)
    syncAfterDateSwitch('timebook', date)
      .then(result => {
        if (!result.ok) setSyncError(formatSyncFailure(result))
        else setSyncError('')
        setRefreshTrigger(prev => prev + 1)
      })
      .catch(error => setSyncError(formatSyncError(error?.message || String(error))))
  }, [])

  const resetToToday = useCallback(() => {
    const today = formatBeijingDate()
    if (selectedDate !== today) changeSelectedDate(today)
  }, [selectedDate, changeSelectedDate])

  const saveFlashCard = useCallback(async (data: FlashCardInput) => {
    const db = await getDatabase()
    const occurredAt = data.occurred_at || beijingDateTime()
    const id = db.saveFlashCard({
      id: data.id,
      occurred_at: occurredAt,
      original_text: data.original_text,
    })
    await loadLocal()
    flushSync()
    return { id, occurred_at: occurredAt, original_text: data.original_text, analysis_status: 'pending' } as FlashCard
  }, [loadLocal])

  const recordFlashCard = useCallback(async (text: string) => {
    const db = await getDatabase()
    const occurredAt = beijingDateTime()
    db.saveFlashCard({
      occurred_at: occurredAt,
      original_text: text,
      analysis_status: 'pending',
    })
    const occurredDate = occurredAt.slice(0, 10)
    setSelectedDate(occurredDate)
    if (occurredDate === selectedDate) await loadLocal()
    flushSync()
    return undefined
  }, [selectedDate, loadLocal])

  const createRecommendedTask = useCallback((recommendation: FlashTaskRecommendation) => {
    submitTask(`flash-${recommendation.id}`, { requestId: (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') ? globalThis.crypto.randomUUID() : `task-${Date.now()}`, dueDate: formatBeijingDate(), flashRecommendationId: recommendation.id })
  }, [submitTask])

  const ignoreRecommendedTask = useCallback(async (recommendation: FlashTaskRecommendation) => {
    await flashRequest(`/api/timebook/flash-recommendations/${encodeURIComponent(recommendation.id)}/ignore`, { method: 'POST' })
    const syncResult = await syncNow({ reason: 'flash-recommendation-ignored' })
    if (!syncResult.ok) throw new Error(formatSyncFailure(syncResult))
    await loadLocal()
  }, [flashRequest, loadLocal])

  const submitFlashClassificationFeedback = useCallback(async (flashCardId: string, label: FlashClassificationLabel) => {
    await flashRequest(`/api/timebook/flash-cards/${encodeURIComponent(flashCardId)}/classification-feedback`, { method: 'POST', body: JSON.stringify({ label }) })
    const syncResult = await syncNow({ reason: 'flash-classification-feedback' })
    if (!syncResult.ok) throw new Error(formatSyncFailure(syncResult))
    await loadLocal()
  }, [flashRequest, loadLocal])

  const correctFlashPolish = useCallback(async (data: FlashPolishCorrectionInput) => {
    const requestId = globalThis.crypto?.randomUUID?.() || `polish-${Date.now()}`
    const result = await flashRequest(`/api/timebook/flash-cards/${encodeURIComponent(data.id)}/polish-corrections`, { method: 'POST', body: JSON.stringify({ request_id: requestId, corrected_text: data.corrected_text, occurred_at: data.occurred_at }) }) as { card: FlashCard }
    const syncResult = await syncNow({ reason: 'flash-polish-correction' })
    if (!syncResult.ok) throw new Error(formatSyncFailure(syncResult))
    await loadLocal()
    return result.card
  }, [flashRequest, loadLocal])

  const loadFlashSkillHistory = useCallback(async (cursor?: string | null) => {
    const query = new URLSearchParams({ limit: '20' }); if (cursor) query.set('cursor', cursor)
    return await flashRequest(`/api/timebook/flash-skill/history?${query.toString()}`) as FlashSkillHistoryPage
  }, [flashRequest])

  const loadFlashProcessingLogs = useCallback(async (flashCardId: string) => {
    const result = await flashRequest(`/api/timebook/flash-processing-logs?flash_card_id=${encodeURIComponent(flashCardId)}`) as { logs?: FlashProcessingLog[] }
    return result.logs || []
  }, [flashRequest])

  const deleteFlashCard = useCallback(async (id: string) => {
    const db = await getDatabase()
    db.deleteFlashCard(id)
    await loadLocal()
    flushSync()
  }, [loadLocal])

  const todaySummary = useMemo(() => {
    const summaryMap: Record<string, { minutes: number; color: string }> = {}
    sessions.forEach(s => {
      const gName = (s as any).group_name || '生活'
      const color = (s as any).category_color || '#999999'
      const minutes = s.net_duration_minutes || 0
      if (!summaryMap[gName]) {
        summaryMap[gName] = { minutes: 0, color }
      }
      summaryMap[gName].minutes += minutes
    })
    return Object.entries(summaryMap).map(([groupName, item]) => ({
      groupName,
      minutes: item.minutes,
      color: item.color
    }))
  }, [sessions])
  const timelineEntries = useMemo(() => buildTimeBookTimeline(selectedDate, sessions, flashCards, diary, checkinEntries), [selectedDate, sessions, flashCards, diary, checkinEntries])

  return useMemo(
    () => ({
      sessions, selectedDate, setSelectedDate: changeSelectedDate, resetToToday, availableDates, markedDates, categories,
      deleteSession, updateSession, saveSession, todaySummary, diary, saveDiary, sleepStatusMap, syncError,
      flashCards, timelineEntries, flashError, taskRecommendations, taskSubmissions, createRecommendedTask, ignoreRecommendedTask, submitFlashClassificationFeedback, loadFlashProcessingLogs, correctFlashPolish, loadFlashSkillHistory, recordFlashCard, saveFlashCard, deleteFlashCard,
    }),
    [sessions, selectedDate, changeSelectedDate, resetToToday, availableDates, markedDates, categories, deleteSession, updateSession, saveSession, todaySummary, diary, saveDiary, sleepStatusMap, syncError, flashCards, timelineEntries, flashError, taskRecommendations, taskSubmissions, createRecommendedTask, ignoreRecommendedTask, submitFlashClassificationFeedback, loadFlashProcessingLogs, correctFlashPolish, loadFlashSkillHistory, recordFlashCard, saveFlashCard, deleteFlashCard],
  )
}
