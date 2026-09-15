import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LogicEngine, type LogicConfig, type TimerState } from '@core/LogicEngine'
import type { CurrentTimerOperation, CurrentTimerOutcome, CurrentTimerState } from '@core/ApiClient'
import { getCurrentTimerClient, getDatabase, isSleepTimerCommandExecuted, markSleepTimerCommandExecuted, pendingSleepTimerCommands, subscribeCurrentTimerClient } from '../db'
import { formatBeijingDate, formatBeijingDateTime } from '@core/BeijingTime'
import type { Category } from '../types'
import { audioConfigFromSettings, playAudioCue, syncAudioConfig } from '../utils/audio'
import { useTimerEvents } from './useTimerEvents'
import { resolveInputOutputCountdownSeconds, resolveLongBreakSeconds, resolveStudyReminderRangeSeconds } from '@core/TimerSettings'
import { emitTimerAudioFlow, emitTimerFlow } from '../utils/timerFlow'
import { applyStatusSwitchNote, canRequestStatusSwitch, formatStatusSwitchSourceSummary, requiresStatusSwitchNote, statusSwitchSourcePolicy, type StatusSwitchLifecycle } from './statusSwitchFlow'
import { shouldBlockTimerCategoryAction } from './timerFocusGuard'
import { decideTaskFocus, executeTaskFocus, type TaskFocusResult } from './taskFocusRouting'
import type { DeviceRuntimeStateService } from '../platform'
import { reconcileTimerReminder } from '../platform/timerReminders'
import { refreshTimerWidget, registerTimerWidgetCommandListener, type TimerWidgetCommandResult } from '../platform/timerWidget'
import { CurrentTimerCoordinator, currentTimerLogicSnapshot, type CurrentTimerReconcileContext } from './timerLeaseCoordinator'
import { loadTimerLeaseJournal, persistTimerLeaseJournal } from '../platform/timerLease'
import { automaticLongBreakStopIntent, decideTimerAudioEffect } from './timerAudioEffects'
import { isTimerCommandReady, timerReadinessFromOutcome, type TimerReadiness } from './timerReadiness'
import { resolveCurrentTimerCategory } from './currentTimerCategory'
import { detectPlatformRuntime } from '../platform/runtime'

const TIMER_RUNTIME_KEY = 'timer.logic.snapshot.v1'
let timerRuntimeState: DeviceRuntimeStateService | null = null
export const setTimerDeviceRuntimeState = (service: DeviceRuntimeStateService | null) => { timerRuntimeState = service }
export const persistTimerSnapshot = async (engine: LogicEngine, service = timerRuntimeState, refresh = refreshTimerWidget) => {
  if (!service?.available) return false
  const snapshot = engine.exportSnapshot()
  await service.set(TIMER_RUNTIME_KEY, JSON.stringify(snapshot))
  refresh()
  await reconcileTimerReminder(snapshot)
  return true
}
export const restoreTimerSnapshot = async (engine: LogicEngine, service = timerRuntimeState) => {
  if (!service?.available) return false
  try {
    const raw = await service.get(TIMER_RUNTIME_KEY)
    const restored = raw ? engine.restoreSnapshot(JSON.parse(raw)) : false
    await reconcileTimerReminder(restored ? engine.exportSnapshot() : null)
    return restored
  } catch { return false }
}
export interface UseTimerReturn {
  state: TimerState
  isPaused: boolean
  cycleCount: number
  totalTodayMinutes: number
  elapsedMs: number
  remainingMs: number
  microBreakRemainingSeconds: number
  showPauseReason: boolean
  showSummary: boolean
  showStatusSwitchNote: boolean
  isEarlyEnd: boolean
  currentCategory: Category | null
  currentNote: string
  categories: Category[]
  balance: number
  currentTimer: CurrentTimerState | null
  timerSyncStatus: TimerReadiness | 'syncing' | 'switching' | 'stopping'
  lastTimerSyncAt: string
  start: (categoryId: number, topic?: string) => void
  requestTaskFocus: (categoryId: number, title: string) => Promise<TaskFocusResult>
  setCurrentNote: (note: string) => void
  togglePause: () => void
  endSession: () => void
  switchCategory: (categoryId: number) => void
  requestStatusSwitch: (traceId?: string) => boolean
  submitStatusSwitchNote: (note: string) => void
  cancelStatusSwitchNote: () => void
  submitSummary: (text: string) => void
  cancelSummary: () => void
  submitPauseReason: (reason: string) => void
  skipPauseReason: () => void
  closeSummary: () => void
}

export const buildLogicConfigFromSettings = (cfg: Record<string, any>): Partial<LogicConfig> => {
  // 数据库存的 study_time_min/max 已经是秒（设置页保存时已乘60），不再重复转换
  const reminderRange = resolveStudyReminderRangeSeconds(cfg.study_time_min, cfg.study_time_max)
  const shortBreakDuration = 10
  const longBreakThreshold = resolveInputOutputCountdownSeconds(cfg.input_output_countdown_min)
  const longBreakDuration = resolveLongBreakSeconds(cfg.long_break_duration)

  return {
    studyTimeMin: reminderRange.min,
    studyTimeMax: reminderRange.max,
    shortBreakDuration,
    longBreakDuration,
    longBreakThreshold,
  }
}

const STATUS_SWITCH_CATEGORY_NAME = '状态切换'
const AUTO_REST_NOTE = '休息'
const DEFAULT_STATUS_SWITCH_NOTE = '状态切换'
const SLEEP_CATEGORY_NAME = '睡觉'
export const findStatusSwitchCategory = (categories: Category[]): Category | null => (
  categories.find(category => category.name === STATUS_SWITCH_CATEGORY_NAME) || null
)

const logTimerFlow = (event: string, details: Record<string, any> = {}) => {
  emitTimerFlow('useTimer', event, details)
}

const warnTimerFlow = (event: string, details: Record<string, any> = {}) => {
  emitTimerFlow('useTimer', event, { result: 'gated', ...details })
}

const errorTimerFlow = (event: string, details: Record<string, any> = {}) => {
  emitTimerFlow('useTimer', event, { result: 'failed', ...details })
}

export function useTimer(): UseTimerReturn {
  const engineRef = useRef<LogicEngine | null>(null)
  const currentTimerCoordinatorRef = useRef<CurrentTimerCoordinator | null>(null)
  const currentTimerClientRef = useRef<any>(null)
  const timerReadinessRef = useRef<TimerReadiness>('initializing')
  const coordinatorEpochRef = useRef(0)
  const coordinatorInitPromiseRef = useRef<Promise<CurrentTimerCoordinator | null> | null>(null)
  const ensureCoordinatorRef = useRef<() => Promise<CurrentTimerCoordinator | null>>(async () => null)
  const refreshCurrentTimerRef = useRef<() => Promise<CurrentTimerOutcome | null>>(async () => null)
  const importWidgetSnapshotRef = useRef<() => Promise<boolean>>(async () => false)
  const timerActionQueueRef = useRef<Promise<void>>(Promise.resolve())
  const timerActionSeqRef = useRef(0)
  const pendingStatusSwitchHandoffRef = useRef<{ sourceSessionId: number | string | null, traceId: string } | null>(null)
  const statusSwitchLifecycleRef = useRef<StatusSwitchLifecycle>('idle')
  const activeStatusSwitchTraceRef = useRef('')
  const lastTimerAudioEffectKeyRef = useRef('')
  const runtimeCueKeysRef = useRef(new Set<string>())
  const longBreakStopIntentsRef = useRef(new Set<string>())
  const [state, setState] = useState<TimerState>('stopped')
  const [isPaused, setIsPaused] = useState(false)
  const [cycleCount, setCycleCount] = useState(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [remainingMs, setRemainingMs] = useState(0)
  const [microBreakRemainingSeconds, setMicroBreakRemainingSeconds] = useState(0)
  const [showPauseReason, setShowPauseReason] = useState(false)
  const [showSummary, setShowSummary] = useState(false)
  const [showStatusSwitchNote, setShowStatusSwitchNote] = useState(false)
  const [isEarlyEnd, setIsEarlyEnd] = useState(false)
  const [currentCategory, setCurrentCategory] = useState<Category | null>(null)
  const [currentNote, setCurrentNoteState] = useState('')
  const [categories, setCategories] = useState<Category[]>([])
  const categoriesRef = useRef<Category[]>([])
  categoriesRef.current = categories
  const [totalTodayMinutes, setTotalTodayMinutes] = useState(0)
  const [balance, setBalance] = useState(0)
  const [currentTimer, setCurrentTimer] = useState<CurrentTimerState | null>(null)
  const [timerSyncStatus, setTimerSyncStatus] = useState<UseTimerReturn['timerSyncStatus']>('initializing')
  const [lastTimerSyncAt, setLastTimerSyncAt] = useState('')
  const applyTimerReadiness = useCallback((readiness: TimerReadiness) => {
    timerReadinessRef.current = readiness
    setTimerSyncStatus(readiness)
  }, [])

  // 初始化：加载数据库 + 创建引擎
  useEffect(() => {
    let engine: LogicEngine | null = null
    let tickTimer: ReturnType<typeof setInterval> | null = null
    let disposed = false
    let unsubscribeCurrentTimerClient = () => {}

    getDatabase().then(async db => {
      const cats = db.getCategories()
      setCategories(cats as Category[])
      setBalance(db.getBalance())

      const allCfg = db.getAllConfig()
      syncAudioConfig(audioConfigFromSettings(allCfg))
      engine = new LogicEngine(buildLogicConfigFromSettings(allCfg))
      engineRef.current = engine

      engine.setCallbacks({
        onTimerFlow: (event, details) => {
          emitTimerFlow('LogicEngine', event, details)
          if (event === 'status-switch.stop.after' && details.automatic === true) {
            const coordinator = currentTimerCoordinatorRef.current
            const active = coordinator?.snapshot()
            if (coordinator && active?.active && active.timer_mode === 'countdown'
              && active.category_name === STATUS_SWITCH_CATEGORY_NAME) {
              const intent = automaticLongBreakStopIntent(active.session_id)
              if (!longBreakStopIntentsRef.current.has(intent)) {
                longBreakStopIntentsRef.current.add(intent)
                void coordinator.command('stop', { userIntentId: intent }).then(outcome => {
                  const accepted = outcome.code === 'accepted'
                  emitTimerFlow('useTimer', 'long-break.authoritative-stop', { result: accepted ? 'completed' : 'failed' })
                  if (!accepted) longBreakStopIntentsRef.current.delete(intent)
                }).catch(() => {
                  longBreakStopIntentsRef.current.delete(intent)
                  emitTimerFlow('useTimer', 'long-break.authoritative-stop', { result: 'failed' })
                })
              }
            }
          }
          if (event === 'status-switch.stop.after' && details.stoppedCategoryName === STATUS_SWITCH_CATEGORY_NAME) {
            emitTimerFlow('useTimer', details.result === 'completed' ? 'flow.completed' : 'flow.failed', {
              traceId: details.traceId,
              result: details.result,
              errorCode: details.result === 'completed' ? undefined : 'status-switch-stop-failed',
              failedStep: details.result === 'completed' ? undefined : 'status-switch.stop',
            })
            activeStatusSwitchTraceRef.current = ''
          }
        },
        onStateChange: (_label: string, newState: TimerState) => {
          logTimerFlow('engine:on-state-change', {
            label: _label,
            newState,
            engineState: engine!.state,
            currentCategoryId: engine!.currentCategoryId,
            currentCategoryName: engine!.currentCategoryName,
          })
          setState(newState)
          setIsPaused(engine!.isPaused)
          setCycleCount(engine!.cycleCount)
          void persistTimerSnapshot(engine!)
        },
        onTick: (elapsed: number, remaining: number) => {
          setElapsedMs(elapsed)
          setRemainingMs(remaining)
        },
        onAudioCue: (cue: string) => {
          const sessionId = currentTimerCoordinatorRef.current?.snapshot()?.session_id
          const key = sessionId && ['victory', 'endLongBreak'].includes(cue) ? `${sessionId}:${cue}` : ''
          if (key && runtimeCueKeysRef.current.has(key)) {
            emitTimerAudioFlow('deduplicated', { cue, source: 'engine', result: 'duplicate' })
            return
          }
          if (key) runtimeCueKeysRef.current.add(key)
          emitTimerAudioFlow('dispatched', { cue, source: 'engine', result: 'dispatch' })
          try { navigator.vibrate?.(20) } catch {}
          playAudioCue(cue as any)
        },
        onMicroBreak: (durationSeconds: number) => {
          setMicroBreakRemainingSeconds(durationSeconds)
        },
        onSummaryRequested: (isSuccess: boolean, earlyEnd: boolean) => {
          setIsEarlyEnd(earlyEnd)
          setShowSummary(true)
        },
        onPauseReasonRequested: () => {
          setShowPauseReason(true)
        },
        onSessionCommitted: record => {
          const traceId = activeStatusSwitchTraceRef.current || undefined
          logTimerFlow('commit.local.skipped', {
            traceId,
            categoryId: record.categoryId,
            hasSessionSummary: Boolean(record.sessionSummary.trim()),
            sessionSummaryLength: record.sessionSummary.length,
            netDurationSeconds: record.netDurationSeconds,
            result: 'skipped',
            reason: 'server-authoritative-history',
          })
        },
      })

      const importRuntimeSnapshot = async (): Promise<boolean> => {
        const activeEngine = engine
        if (!activeEngine) return false
        const restored = await restoreTimerSnapshot(activeEngine)
        if (!restored || disposed) return false
        const snapshot = activeEngine.exportSnapshot()
        setState(activeEngine.state)
        setIsPaused(activeEngine.isPaused)
        setElapsedMs(snapshot.timing.elapsedMs)
        setRemainingMs(snapshot.timing.mode === 'countdown' ? Math.max(0, snapshot.session.durationSeconds * 1000 - snapshot.timing.elapsedMs) : 0)
        setCurrentCategory(snapshot.category.id === null
          ? null
          : categoriesRef.current.find(category => Number(category.id) === Number(snapshot.category.id))
            || { id: Number(snapshot.category.id), name: snapshot.category.name } as Category)
        setCurrentNoteState(snapshot.category.task)
        return true
      }
      await importRuntimeSnapshot()
      const runtime = timerRuntimeState || {
        available: false,
        get: async () => null,
        set: async () => undefined,
        remove: async () => undefined,
      }
      const oldJournal = await loadTimerLeaseJournal(runtime)
      if (runtime.available && oldJournal.expired().length) {
        await persistTimerLeaseJournal(runtime, oldJournal)
      }
      const ensureCoordinator = async (): Promise<CurrentTimerCoordinator | null> => {
        if (coordinatorInitPromiseRef.current) return coordinatorInitPromiseRef.current
        const epoch = coordinatorEpochRef.current
        const promise = (async () => {
          const timerClient = getCurrentTimerClient()
          const deviceId = String(db.ensureDeviceId?.() || db.getConfig('device_id') || '')
          if (!timerClient || !deviceId) {
            if (!disposed && epoch === coordinatorEpochRef.current) applyTimerReadiness('unavailable')
            return null
          }
          if (!currentTimerCoordinatorRef.current || currentTimerClientRef.current !== timerClient) {
            currentTimerClientRef.current = timerClient
            currentTimerCoordinatorRef.current = new CurrentTimerCoordinator(
              timerClient,
              deviceId,
              (authoritative: CurrentTimerState | null, outcome: CurrentTimerOutcome, context: CurrentTimerReconcileContext) => {
                if (disposed || epoch !== coordinatorEpochRef.current) return
            const snapshot = currentTimerLogicSnapshot(authoritative)
            engine!.restoreSnapshot(snapshot)
            const effect = decideTimerAudioEffect(authoritative, outcome, context, lastTimerAudioEffectKeyRef.current)
            if (effect.cue) {
              emitTimerAudioFlow(effect.dispatch ? 'dispatched' : 'deduplicated', {
                cue: effect.cue, source: context.source, operation: context.operation,
                revision: authoritative?.revision, hasIntent: Boolean(context.intent),
                intentLength: context.intent?.length, result: effect.reason,
              })
              if (effect.dispatch) {
                lastTimerAudioEffectKeyRef.current = effect.key
                try { navigator.vibrate?.(20) } catch {}
                playAudioCue(effect.cue)
              }
            }
            setCurrentTimer(authoritative)
            setCurrentCategory(authoritative?.active
              ? resolveCurrentTimerCategory(categoriesRef.current, authoritative.category_id, authoritative.category_name)
              : null)
            setCurrentNoteState(authoritative?.active ? (authoritative.current_note || '') : '')
            setState(engine!.state)
            setIsPaused(engine!.isPaused)
            setElapsedMs(snapshot.timing.elapsedMs)
            setRemainingMs(snapshot.timing.mode === 'countdown'
              ? Math.max(0, snapshot.session.durationSeconds * 1000 - snapshot.timing.elapsedMs)
              : 0)
            applyTimerReadiness(timerReadinessFromOutcome(outcome))
            if (outcome.code === 'accepted') setLastTimerSyncAt(formatBeijingDateTime())
            void persistTimerSnapshot(engine!)
          },
            )
          }
          const coordinator = currentTimerCoordinatorRef.current
          const initial = await coordinator.refresh()
          if (!disposed && epoch === coordinatorEpochRef.current) {
            applyTimerReadiness(timerReadinessFromOutcome(initial))
            if (initial.code === 'accepted') setLastTimerSyncAt(formatBeijingDateTime())
          }
          return coordinator
        })()
        coordinatorInitPromiseRef.current = promise
        return promise.finally(() => {
          if (coordinatorInitPromiseRef.current === promise) coordinatorInitPromiseRef.current = null
        })
      }
      const refreshCurrentTimer = async (): Promise<CurrentTimerOutcome | null> => {
        const coordinator = await ensureCoordinator()
        if (!coordinator) return null
        const outcome = await coordinator.refresh()
        if (!disposed) applyTimerReadiness(timerReadinessFromOutcome(outcome))
        return outcome
      }
      const importWidgetSnapshot = importRuntimeSnapshot
      ensureCoordinatorRef.current = ensureCoordinator
      refreshCurrentTimerRef.current = refreshCurrentTimer
      importWidgetSnapshotRef.current = importWidgetSnapshot
      unsubscribeCurrentTimerClient = subscribeCurrentTimerClient(client => {
        coordinatorEpochRef.current += 1
        currentTimerCoordinatorRef.current = null
        currentTimerClientRef.current = null
        coordinatorInitPromiseRef.current = null
        applyTimerReadiness(client ? 'initializing' : 'unavailable')
        if (client) void ensureCoordinator()
      })
      void ensureCoordinator()

      // 心跳定时器：每 200ms 同步引擎状态到 UI
      tickTimer = setInterval(() => {
        if (!engine) return
        setState(engine.state)
        setIsPaused(engine.isPaused)
        setCycleCount(engine.cycleCount)
        if (engine.state !== 'stopped') {
          setElapsedMs(engine['_timer']?.getElapsed() ?? 0)
        }
        
        // 当因为挂起切换而使得 engine currentCategory 变动时，同步 UI
        const activeEngine = engine
        if (activeEngine.state === 'stopped' && !activeEngine.currentCategoryId) {
          setCurrentNoteState('')
          setCurrentCategory(prev => (prev === null ? prev : null))
        } else if (activeEngine.state !== 'stopped' && activeEngine.currentCategoryId) {
           setCurrentNoteState(activeEngine.currentFocusTask)
           setCurrentCategory(prev => {
             if (prev?.id !== activeEngine.currentCategoryId) {
               return resolveCurrentTimerCategory(categoriesRef.current, activeEngine.currentCategoryId, activeEngine.currentCategoryName)
             }
             return prev
           })
        }
      }, 200)

      const today = formatBeijingDate()
      const sessions = db.getSessionsByDate(today)
      setTotalTodayMinutes(
        sessions.reduce((s: number, r: any) => s + (r.net_duration_minutes || 0), 0)
      )
    })

    return () => {
      disposed = true
      coordinatorEpochRef.current += 1
      unsubscribeCurrentTimerClient()
      if (tickTimer) clearInterval(tickTimer)
      if (engine) void persistTimerSnapshot(engine)
      currentTimerCoordinatorRef.current = null
      currentTimerClientRef.current = null
      coordinatorInitPromiseRef.current = null
      ensureCoordinatorRef.current = async () => null
      refreshCurrentTimerRef.current = async () => null
      importWidgetSnapshotRef.current = async () => false
    }
  }, [])

  useTimerEvents(setCategories, setBalance)

  useEffect(() => {
    const authoritative = currentTimerCoordinatorRef.current?.snapshot()
    setCurrentCategory(authoritative?.active
      ? resolveCurrentTimerCategory(categories, authoritative.category_id, authoritative.category_name)
      : null)
  }, [categories])

  useEffect(() => {
    if (microBreakRemainingSeconds <= 0) return
    const timer = setInterval(() => {
      setMicroBreakRemainingSeconds(prev => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [microBreakRemainingSeconds])

  const enqueueTimerAction = useCallback(<T,>(
    action: string,
    run: (ctx: { actionId: string, traceId: string, db: any, engine: LogicEngine }) => Promise<T> | T,
    traceId?: string,
  ) => {
    const effectiveTraceId = traceId || `${action}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const actionId = `${action}-${Date.now()}-${++timerActionSeqRef.current}`
    logTimerFlow('action.queued', { traceId: effectiveTraceId, actionId, action })

    const result = timerActionQueueRef.current.then(async (): Promise<T | undefined> => {
      const engine = engineRef.current
      if (!engine) {
        warnTimerFlow('action.skipped', { traceId: effectiveTraceId, actionId, action, reason: 'missing-engine' })
        return
      }
      logTimerFlow('action.started', {
        traceId: effectiveTraceId,
        actionId,
        action,
        engineState: engine.state,
        currentCategoryId: engine.currentCategoryId,
        currentCategoryName: engine.currentCategoryName,
      })
      try {
        const db = await getDatabase()
        engine.updateConfig(buildLogicConfigFromSettings(db.getAllConfig()))
        logTimerFlow('action.config-refreshed', {
          traceId: effectiveTraceId,
          actionId,
          action,
          engineState: engine.state,
          currentCategoryId: engine.currentCategoryId,
          currentCategoryName: engine.currentCategoryName,
        })
        const value = await run({ actionId, traceId: effectiveTraceId, db, engine })
        void persistTimerSnapshot(engine)
        logTimerFlow('action.completed', {
          traceId: effectiveTraceId,
          actionId,
          action,
          engineState: engine.state,
          currentCategoryId: engine.currentCategoryId,
          currentCategoryName: engine.currentCategoryName,
        })
        return value
      } catch (err: any) {
        errorTimerFlow('action.failed', {
          traceId: effectiveTraceId,
          actionId,
          action,
          errorCode: 'timer-action-failed',
          failedStep: action,
        })
        if (action === 'status-switch-request') {
          pendingStatusSwitchHandoffRef.current = null
          statusSwitchLifecycleRef.current = 'idle'
          activeStatusSwitchTraceRef.current = ''
          errorTimerFlow('flow.local.failed', {
            traceId: effectiveTraceId,
            actionId,
            errorCode: 'status-switch-request-failed',
            failedStep: 'status-switch-request',
            lifecycleAfter: 'idle',
          })
        } else if (action === 'status-switch-note') {
          statusSwitchLifecycleRef.current = 'awaiting-note'
          setShowStatusSwitchNote(true)
        }
      }
    })
    timerActionQueueRef.current = result.then(() => undefined)

    return result
  }, [])

  const commandCurrentTimer = useCallback(async (
    operation: CurrentTimerOperation,
    input: Parameters<CurrentTimerCoordinator['command']>[1] = {},
  ): Promise<CurrentTimerOutcome> => {
    const coordinator = await ensureCoordinatorRef.current()
    if (!coordinator || !isTimerCommandReady(timerReadinessRef.current)) {
      return {
        code: timerReadinessRef.current === 'network_failed' ? 'network'
          : timerReadinessRef.current === 'auth_failed' ? 'auth'
            : timerReadinessRef.current === 'upgrade_required' ? 'upgrade_required' : 'error',
        status: 0,
        errorCode: timerReadinessRef.current === 'initializing' ? 'timer_initializing' : 'timer_not_ready',
      }
    }
    setTimerSyncStatus(operation === 'switch' || operation === 'start'
      ? 'switching'
      : operation === 'stop' ? 'stopping' : 'syncing')
    const outcome = await coordinator.command(operation, input)
    if (outcome.code !== 'accepted') applyTimerReadiness(timerReadinessFromOutcome(outcome))
    return outcome
  }, [applyTimerReadiness])

  const consumeSleepSwitchCommands = useCallback(async () => {
    const db = await getDatabase(); const category = categories.find(item => item.name === SLEEP_CATEGORY_NAME)
    if (!category) return
    for (const command of pendingSleepTimerCommands(db)) {
      if (isSleepTimerCommandExecuted(db, command.id)) continue
      await enqueueTimerAction(`sleep-command-${command.id}`, async () => {
        const coordinator = await ensureCoordinatorRef.current()
        const refreshed = await coordinator?.refresh()
        if (refreshed?.code !== 'accepted') return
        // 22:30 自动切换由服务端权威计时服务完成；客户端只刷新并确认命令，禁止二次切换。
        markSleepTimerCommandExecuted(db, command.id)
      }, command.id)
    }
  }, [categories, commandCurrentTimer, enqueueTimerAction])

  useEffect(() => {
    const consume = () => { void consumeSleepSwitchCommands() }
    consume(); window.addEventListener('sync-pull-complete', consume); window.addEventListener('online', consume)
    return () => { window.removeEventListener('sync-pull-complete', consume); window.removeEventListener('online', consume) }
  }, [consumeSleepSwitchCommands])

  useEffect(() => {
    if (!engineRef.current || categories.length === 0) return
    return registerTimerWidgetCommandListener(command => {
      const widgetEventAt = new Date(command.eventEpochMs)
      if (!Number.isFinite(widgetEventAt.getTime())) return Promise.resolve('requires_app')
      const cat = categories.find(item => item.id === command.categoryId)
      if (!cat || ['输入', '输出'].includes(cat.name)) return Promise.resolve('requires_app')
      return enqueueTimerAction(`widget-${command.action}`, async ({ engine }) => {
        const coordinator = await ensureCoordinatorRef.current()
        if (!coordinator || !isTimerCommandReady(timerReadinessRef.current)) return 'requires_app'
        const operation = command.action === 'stop'
          ? 'stop'
          : (coordinator.snapshot()?.active ? 'switch' : 'start')
        const outcome = await commandCurrentTimer(operation, operation === 'stop'
          ? { userIntentId: command.commandId }
          : {
              categoryId: cat.id, categoryName: cat.name, timerMode: 'countup',
              sessionId: operation === 'start' ? `widget-${command.commandId}` : undefined,
              userIntentId: command.commandId,
            })
        if (outcome?.code !== 'accepted') return 'requires_app'
        return 'applied'
      }).then(result => (result ?? 'failed') as TimerWidgetCommandResult)
    })
  }, [categories, commandCurrentTimer, enqueueTimerAction])

  useEffect(() => {
    if (!engineRef.current) return
    const refresh = () => { void refreshCurrentTimerRef.current() }
    window.addEventListener('mtl:timer-widget-snapshot-changed', refresh)
    return () => window.removeEventListener('mtl:timer-widget-snapshot-changed', refresh)
  }, [categories, enqueueTimerAction])

  const start = useCallback((categoryId: number, topic?: string) => {
    const cat = categories.find(c => c.id === categoryId)
    if (!cat || !engineRef.current) return
    enqueueTimerAction('start', async ({ actionId, engine, db }) => {
      if (shouldBlockTimerCategoryAction('start', engine.currentCategoryName, engine.state)) {
        warnTimerFlow('focus-lock.category-blocked', { actionId, action: 'start', sourceCategoryId: engine.currentCategoryId, sourceCategoryName: engine.currentCategoryName, targetCategoryId: cat.id, targetCategoryName: cat.name, engineState: engine.state, result: 'gated', reason: 'structured-focus-active' })
        return
      }
      const sessionId = `timer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const timerMode = ['输入', '输出'].includes(cat.name) ? 'countdown' : 'countup'
      const durationMs = timerMode === 'countdown'
        ? resolveInputOutputCountdownSeconds(db.getConfig('input_output_countdown_min')) * 1000
        : 0
      const outcome = await commandCurrentTimer('start', {
        sessionId, categoryId: cat.id, categoryName: cat.name, currentNote: topic ?? '', timerMode, durationMs,
      })
      if (outcome?.code !== 'accepted' || !outcome.state) {
        warnTimerFlow('timer.start.rejected', {
          actionId, categoryId, categoryName: cat.name,
          errorCode: outcome?.errorCode || outcome?.code || 'timer_unavailable',
        })
        return
      }
      const note = topic ?? ''
      setCurrentNoteState(note)
    })
  }, [categories, commandCurrentTimer, enqueueTimerAction])

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const refresh = async () => {
      if (stopped) return
      await refreshCurrentTimerRef.current().catch(() => null)
    }
    const schedule = () => {
      if (stopped) return
      if (timer) clearTimeout(timer)
      timer = setTimeout(async () => {
        const active = currentTimerCoordinatorRef.current?.snapshot()?.active
        if (active && document.visibilityState === 'visible') await refresh()
        schedule()
      }, 15_000)
    }
    const importWidgetSnapshot = () => importWidgetSnapshotRef.current()
    const onForeground = () => {
      if (document.visibilityState === 'visible') void importWidgetSnapshot().finally(() => { void refresh() })
    }
    const onWidgetSnapshotChanged = () => { void importWidgetSnapshot() }
    const onSynced = () => { void refresh() }
    void refresh()
    schedule()
    window.addEventListener('online', refresh)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', onForeground)
    window.addEventListener('mtl:timer-widget-snapshot-changed', onWidgetSnapshotChanged)
    window.addEventListener('mtl:timer-state-changed', onSynced)
    window.addEventListener('mtl:current-timer-state', onSynced)
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      window.removeEventListener('online', refresh)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', onForeground)
      window.removeEventListener('mtl:timer-widget-snapshot-changed', onWidgetSnapshotChanged)
      window.removeEventListener('mtl:timer-state-changed', onSynced)
      window.removeEventListener('mtl:current-timer-state', onSynced)
    }
  }, [])

  const requestTaskFocus = useCallback(async (categoryId: number, title: string): Promise<TaskFocusResult> => {
    const cat = categories.find(c => c.id === categoryId)
    if (!cat) return { status: 'unavailable', reason: 'missing-category' }
    const result = await enqueueTimerAction('task-focus', async ({ actionId, engine }) => {
      const decision = decideTaskFocus(engine.state, engine.currentCategoryId, engine.currentCategoryName, cat.id)
      logTimerFlow('task-focus.decided', { actionId, sourceCategoryId: engine.currentCategoryId, sourceCategoryName: engine.currentCategoryName, targetCategoryId: cat.id, targetCategoryName: cat.name, engineState: engine.state, result: decision.status, hasTitle: Boolean(title.trim()), titleLength: title.length })
      return executeTaskFocus(decision, {
        started: async () => {
          const outcome = await commandCurrentTimer('start', {
            sessionId: `task-${Date.now()}`, categoryId: cat.id, categoryName: cat.name, currentNote: title, timerMode: 'countup',
          })
          if (outcome?.code !== 'accepted') throw new Error('current-timer-start-failed')
          setCurrentNoteState(title)
        },
        retargeted: async () => {
          const outcome = await commandCurrentTimer('note', { currentNote: title })
          if (outcome?.code !== 'accepted') throw new Error('current-timer-note-failed')
        },
        switched: async () => {
          const outcome = await commandCurrentTimer('switch', {
            categoryId: cat.id, categoryName: cat.name, currentNote: title, timerMode: 'countup',
          })
          if (outcome?.code !== 'accepted') throw new Error('current-timer-switch-failed')
          setCurrentNoteState(title)
        },
      })
    })
    return result ?? { status: 'unavailable', reason: engineRef.current ? 'action-failed' : 'missing-engine' }
  }, [categories, commandCurrentTimer, enqueueTimerAction])

  const startStatusSwitch = useCallback((note: string, useLongBreakDuration = false) => {
    const cat = findStatusSwitchCategory(categories)
    const engine = engineRef.current
    if (!cat || !engine) {
      console.warn('[timer] 状态切换分类不存在，无法自动切换')
      return false
    }
    enqueueTimerAction('start-status-switch', async ({ actionId, db }) => {
      const active = currentTimerCoordinatorRef.current?.snapshot()?.active
      const operation = active ? 'switch' : 'start'
      const durationMs = useLongBreakDuration
        ? resolveLongBreakSeconds(db.getConfig('long_break_duration')) * 1000
        : 0
      const outcome = await commandCurrentTimer(operation, {
        sessionId: operation === 'start' ? `status-switch-${Date.now()}` : undefined,
        categoryId: cat.id, categoryName: cat.name,
        timerMode: useLongBreakDuration ? 'countdown' : 'countup', durationMs,
      })
      if (outcome?.code !== 'accepted' || !outcome.state) return
      setCurrentNoteState(note)
      logTimerFlow('current-state.status-switch.accepted', {
        actionId, categoryId: cat.id, categoryName: cat.name,
        revision: outcome.state.revision, useLongBreakDuration, result: 'completed',
      })
    })
    return true
  }, [categories, commandCurrentTimer, enqueueTimerAction])

  const requestStatusSwitch = useCallback((traceId?: string) => {
    const effectiveTraceId = traceId || `status-switch-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const lifecycleBefore = statusSwitchLifecycleRef.current
    if (!canRequestStatusSwitch(lifecycleBefore)) {
      logTimerFlow('shortcut.gated', {
        traceId: effectiveTraceId,
        lifecycleBefore,
        lifecycleAfter: lifecycleBefore,
        result: 'gated',
        errorCode: 'status-switch-in-flight',
      })
      logTimerFlow('flow.completed', { traceId: effectiveTraceId, result: 'gated' })
      return false
    }
    const cat = findStatusSwitchCategory(categories)
    const engine = engineRef.current
    if (!cat || !engine) {
      console.warn('[timer] 状态切换分类不存在，无法响应快捷键')
      errorTimerFlow('flow.failed', { traceId: effectiveTraceId, hasCategory: Boolean(cat), hasEngine: Boolean(engine), errorCode: 'missing-category-or-engine', failedStep: 'request.preflight' })
      return false
    }
    if (engine.currentCategoryId === cat.id && engine.state !== 'stopped' && engine.state !== 'long_break_finished') {
      logTimerFlow('shortcut.ignored', { traceId: effectiveTraceId, result: 'ignored', reason: 'already-status-switch' })
      logTimerFlow('flow.completed', { traceId: effectiveTraceId, result: 'ignored' })
      return false
    }

    statusSwitchLifecycleRef.current = 'queued'
    activeStatusSwitchTraceRef.current = effectiveTraceId
    logTimerFlow('lifecycle.changed', { traceId: effectiveTraceId, lifecycleBefore, lifecycleAfter: 'queued', result: 'queued' })
    enqueueTimerAction('status-switch-request', async ({ actionId, traceId: queuedTraceId, engine }) => {
      statusSwitchLifecycleRef.current = 'switching'
      logTimerFlow('lifecycle.changed', { traceId: queuedTraceId, actionId, lifecycleBefore: 'queued', lifecycleAfter: 'switching', result: 'switching' })
      const sourceCategoryId = engine.currentCategoryId
      const sourceCategoryName = engine.currentCategoryName
      const sourcePolicy = statusSwitchSourcePolicy(sourceCategoryName)
      const requiresNote = sourcePolicy.requiresNote && requiresStatusSwitchNote(detectPlatformRuntime())
      logTimerFlow('source.classified', { traceId: queuedTraceId, actionId, sourceCategoryId, sourceCategoryName, targetCategoryId: cat.id, targetCategoryName: cat.name, sourceKind: sourcePolicy.kind, requiresNote, result: 'completed' })
      pendingStatusSwitchHandoffRef.current = null
      if (!requiresNote) logTimerFlow('handoff.source-captured/skipped', { traceId: queuedTraceId, actionId, sourceCategoryId, sourceCategoryName, result: 'skipped', reason: 'source-note-not-required' })
      try {
        const operation = currentTimerCoordinatorRef.current?.snapshot()?.active ? 'switch' : 'start'
        const outcome = await commandCurrentTimer(operation, {
          sessionId: operation === 'start' ? `status-switch-${Date.now()}` : undefined,
          categoryId: cat.id, categoryName: cat.name, timerMode: 'countup',
          userIntentId: queuedTraceId,
        })
        if (outcome?.code !== 'accepted' || !outcome.state) throw new Error('current-state-switch-failed')

        setCurrentNoteState('')
        setShowStatusSwitchNote(requiresNote)
        statusSwitchLifecycleRef.current = requiresNote ? 'awaiting-note' : 'idle'
        logTimerFlow('ui.category.result', { traceId: queuedTraceId, actionId, sourceCategoryId, sourceCategoryName, currentCategoryId: cat.id, currentCategoryName: cat.name, result: 'completed' })
        logTimerFlow(requiresNote ? 'sheet.opened' : 'sheet.opened/skipped', { traceId: queuedTraceId, actionId, sourceCategoryId, sourceCategoryName, lifecycleBefore: 'switching', lifecycleAfter: statusSwitchLifecycleRef.current, result: requiresNote ? 'completed' : 'skipped', reason: requiresNote ? undefined : 'source-note-not-required' })
        logTimerFlow('flow.local.completed', { traceId: queuedTraceId, actionId, sourceCategoryId, sourceCategoryName, targetCategoryId: cat.id, targetCategoryName: cat.name, result: 'completed' })

        if (!requiresNote) activeStatusSwitchTraceRef.current = ''
      } catch {
        pendingStatusSwitchHandoffRef.current = null
        statusSwitchLifecycleRef.current = 'idle'
        activeStatusSwitchTraceRef.current = ''
        throw new Error('current-state-switch-failed')
      }
    }, effectiveTraceId)
    return true
  }, [categories, commandCurrentTimer, enqueueTimerAction])

  const submitStatusSwitchNote = useCallback((note: string) => {
    const traceId = activeStatusSwitchTraceRef.current || `status-switch-note-${Date.now()}`
    if (statusSwitchLifecycleRef.current !== 'awaiting-note') {
      warnTimerFlow('note.submit.gated', { traceId, lifecycleBefore: statusSwitchLifecycleRef.current, result: 'gated' })
      return
    }
    const finalNote = note.trim() || DEFAULT_STATUS_SWITCH_NOTE
    const handoff = pendingStatusSwitchHandoffRef.current
    const cat = findStatusSwitchCategory(categories)
    statusSwitchLifecycleRef.current = 'note-submitting'
    logTimerFlow('note.confirmed', {
      traceId,
      hasNote: Boolean(finalNote),
      noteLength: finalNote.length,
      sourceSessionId: handoff?.sourceSessionId,
      hasStatusSwitchCategory: Boolean(cat),
      lifecycleBefore: 'awaiting-note',
      lifecycleAfter: 'note-submitting',
    })
    enqueueTimerAction('status-switch-note', async ({ actionId, traceId: noteTraceId, db, engine }) => {
      try {
        if (!cat) throw new Error('missing-status-switch-category')
        if (engine.currentCategoryId !== cat.id || engine.state !== 'countup_studying') {
          const refreshed = await currentTimerCoordinatorRef.current?.refresh()
          if (refreshed?.code !== 'accepted'
            || Number(refreshed.state?.category_id) !== Number(cat.id)
            || refreshed.state?.state === 'stopped') throw new Error('status-switch-restore-failed')
        }
        logTimerFlow('note.validated', { traceId: noteTraceId, actionId, currentCategoryId: engine.currentCategoryId, currentCategoryName: engine.currentCategoryName, result: 'completed' })

        const sourceSessionId = handoff?.sourceSessionId
        const noteApplied = applyStatusSwitchNote({
          engine,
          categoryId: cat.id,
          note: finalNote,
          sourceSessionId,
          updateSource: (id, value) => {
            const sourceSummary = formatStatusSwitchSourceSummary(value)
            db.updateSession(id, { session_summary: sourceSummary } as any)
            const savedSource = db.getSessionById?.(id)
            if (savedSource && savedSource.session_summary !== sourceSummary) throw new Error('source-session-update-failed')
            logTimerFlow('note.source-saved', { traceId: noteTraceId, actionId, sourceSessionId: id, hasNote: true, noteLength: sourceSummary.length, result: 'completed' })
          },
        })
        if (!noteApplied) throw new Error('note-validation-failed')
        setCurrentCategory(cat)
        setCurrentNoteState(finalNote)
        logTimerFlow('note.current-saved', { traceId: noteTraceId, actionId, currentCategoryId: cat.id, currentCategoryName: cat.name, hasNote: true, noteLength: finalNote.length, result: 'completed' })

        const today = formatBeijingDate()
        const sessions = db.getSessionsByDate(today)
        setTotalTodayMinutes(sessions.reduce((s: number, r: any) => s + (r.net_duration_minutes || 0), 0))
        pendingStatusSwitchHandoffRef.current = null
        setShowStatusSwitchNote(false)
        statusSwitchLifecycleRef.current = 'idle'
        logTimerFlow('note.completed', { traceId: noteTraceId, actionId, result: 'completed', lifecycleBefore: 'note-submitting', lifecycleAfter: 'idle' })
      } catch {
        statusSwitchLifecycleRef.current = 'awaiting-note'
        setShowStatusSwitchNote(true)
        errorTimerFlow('note.failed', { traceId: noteTraceId, actionId, errorCode: 'status-switch-note-save-failed', failedStep: 'note.submit', lifecycleBefore: 'note-submitting', lifecycleAfter: 'awaiting-note' })
      }
    }, traceId)
  }, [categories, enqueueTimerAction])

  const cancelStatusSwitchNote = useCallback(() => {
    const traceId = activeStatusSwitchTraceRef.current || `status-switch-cancel-${Date.now()}`
    logTimerFlow('note.cancelled', {
      traceId,
      sourceSessionId: pendingStatusSwitchHandoffRef.current?.sourceSessionId,
      lifecycleBefore: statusSwitchLifecycleRef.current,
      lifecycleAfter: 'idle',
    })
    pendingStatusSwitchHandoffRef.current = null
    statusSwitchLifecycleRef.current = 'idle'
    setShowStatusSwitchNote(false)
    logTimerFlow('note.cancelled-completed', { traceId, result: 'cancelled' })
  }, [])

  const setCurrentNote = useCallback((note: string) => {
    logTimerFlow('note:set-current', {
      note,
      engineState: engineRef.current?.state,
      currentCategoryId: engineRef.current?.currentCategoryId,
    })
    setCurrentNoteState(note)
    engineRef.current?.setCurrentFocusTask(note)
    void enqueueTimerAction('update-note', async () => {
      const outcome = await commandCurrentTimer('note', { currentNote: note })
      if (outcome?.code === 'accepted') return
      await refreshCurrentTimerRef.current()
    })
  }, [commandCurrentTimer, enqueueTimerAction])

  const togglePause = useCallback(() => {
    const engine = engineRef.current
    if (!engine) return
    const wasPaused = engine.isPaused
    logTimerFlow('pause:toggle', {
      wasPaused,
      engineState: engine.state,
      currentCategoryId: engine.currentCategoryId,
      currentCategoryName: engine.currentCategoryName,
    })
    void enqueueTimerAction('toggle-pause', async () => {
      const outcome = await commandCurrentTimer(wasPaused ? 'resume' : 'pause')
      if (outcome?.code !== 'accepted' || !outcome.state) return
    })
  }, [commandCurrentTimer, enqueueTimerAction])

  const endSession = useCallback(() => {
    const engine = engineRef.current
    if (!engine) return
    logTimerFlow('session:end-requested', {
      engineState: engine.state,
      currentCategoryId: engine.currentCategoryId,
      currentCategoryName: engine.currentCategoryName,
      currentUiCategoryId: currentCategory?.id,
      currentUiCategoryName: currentCategory?.name,
    })
    if (engine.state === 'studying') {
      void enqueueTimerAction('request-summary', async ({ engine: activeEngine }) => {
        const outcome = await commandCurrentTimer('pause')
        if (outcome?.code !== 'accepted' || !outcome.state) return
        activeEngine.endStudyNow()
      })
    } else {
      void enqueueTimerAction('stop', async () => {
        const outcome = await commandCurrentTimer('stop')
        if (outcome?.code !== 'accepted' || !outcome.state) return
      })
    }
  }, [commandCurrentTimer, currentCategory, enqueueTimerAction])

  const submitSummary = useCallback((text: string) => {
    if (isEarlyEnd && !text.trim()) return
    const shouldAutoRest = !isEarlyEnd
    setShowSummary(false)
    void enqueueTimerAction('submit-summary', async ({ engine }) => {
      logTimerFlow('summary:submit', {
        isEarlyEnd, shouldAutoRest, textLength: text.length,
        engineState: engine.state, currentCategoryId: engine.currentCategoryId,
        currentCategoryName: engine.currentCategoryName,
      })
      const outcome = await commandCurrentTimer('stop', { sessionSummary: text })
      if (outcome?.code !== 'accepted' || !outcome.state) {
        setShowSummary(true)
        return
      }
      setCurrentNoteState('')
      setIsEarlyEnd(false)
      if (shouldAutoRest) startStatusSwitch(AUTO_REST_NOTE, true)
    })
  }, [commandCurrentTimer, enqueueTimerAction, isEarlyEnd, startStatusSwitch])

  const closeSummary = useCallback(() => {
    if (isEarlyEnd) {
      setShowSummary(false)
      setIsEarlyEnd(false)
      void enqueueTimerAction('cancel-summary', async ({ engine }) => {
        const outcome = await commandCurrentTimer('resume')
        if (outcome?.code !== 'accepted' || !outcome.state) return
        engine.cancelEarlyEnd()
      })
      return
    }
    submitSummary('')
  }, [commandCurrentTimer, enqueueTimerAction, isEarlyEnd, submitSummary])

  const submitPauseReason = useCallback((reason: string) => {
    engineRef.current?.submitPauseReason(reason)
    setShowPauseReason(false)
  }, [])

  const skipPauseReason = useCallback(() => {
    engineRef.current?.skipPauseReason()
    setShowPauseReason(false)
  }, [])

  const switchCategory = useCallback((categoryId: number) => {
    const cat = categories.find(c => c.id === categoryId)
    const engine = engineRef.current
    if (!cat || !engine) return
    if (cat.name === STATUS_SWITCH_CATEGORY_NAME) {
      requestStatusSwitch()
      return
    }
    if (shouldBlockTimerCategoryAction('switchCategory', engine.currentCategoryName, engine.state)) {
      warnTimerFlow('focus-lock.category-blocked', { action: 'switchCategory', sourceCategoryId: engine.currentCategoryId, sourceCategoryName: engine.currentCategoryName, targetCategoryId: cat.id, targetCategoryName: cat.name, engineState: engine.state, result: 'gated', reason: 'structured-focus-active' })
      return
    }
    logTimerFlow('category:switch-requested', {
      targetCategoryId: categoryId,
      targetCategoryName: cat.name,
      engineState: engine.state,
      currentCategoryId: engine.currentCategoryId,
      currentCategoryName: engine.currentCategoryName,
    })
    void enqueueTimerAction('switch-category', async ({ db }) => {
      const timerMode = ['输入', '输出'].includes(cat.name) ? 'countdown' : 'countup'
      const durationMs = timerMode === 'countdown'
        ? resolveInputOutputCountdownSeconds(db.getConfig('input_output_countdown_min')) * 1000
        : 0
      const outcome = await commandCurrentTimer('switch', {
        categoryId: cat.id, categoryName: cat.name, timerMode, durationMs,
      })
      if (outcome?.code !== 'accepted' || !outcome.state) {
        warnTimerFlow('current-state.switch.rejected', { errorCode: outcome?.errorCode || outcome?.code })
        return
      }
      setCurrentNoteState('')
    })
  }, [categories, commandCurrentTimer, enqueueTimerAction, requestStatusSwitch])

  return useMemo(() => ({
    state, isPaused, cycleCount, totalTodayMinutes, elapsedMs, remainingMs, microBreakRemainingSeconds,
    showPauseReason, showSummary, showStatusSwitchNote, isEarlyEnd,
    currentCategory, currentNote, categories, balance: Math.round(balance * 100) / 100,
    currentTimer, timerSyncStatus, lastTimerSyncAt,
    start, requestTaskFocus, setCurrentNote, togglePause, endSession, switchCategory, requestStatusSwitch, submitStatusSwitchNote, cancelStatusSwitchNote, submitSummary, cancelSummary: closeSummary, submitPauseReason, skipPauseReason, closeSummary,
  }), [state, isPaused, cycleCount, totalTodayMinutes, elapsedMs, remainingMs, microBreakRemainingSeconds,
      showPauseReason, showSummary, showStatusSwitchNote, isEarlyEnd,
      currentCategory, currentNote, categories, balance, currentTimer, timerSyncStatus, lastTimerSyncAt,
      start, requestTaskFocus, setCurrentNote, togglePause, endSession, switchCategory, requestStatusSwitch, submitStatusSwitchNote, cancelStatusSwitchNote, submitSummary, submitPauseReason, skipPauseReason, closeSummary])
}
