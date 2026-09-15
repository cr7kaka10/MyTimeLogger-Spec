/**
 * 核心状态机 — 还原初始 PC 版逻辑
 *
 * 输入/输出规则：可配置总倒计时，期间按配置间隔触发 10秒短休息。
 * 普通规则：正计时，无自动短休息。
 */

import { Timer, TimerMode } from './Timer'
import { LOGIC_SNAPSHOT_VERSION, type LogicSnapshot, validateLogicSnapshot } from './LogicSnapshot'
import { beijingDayName, formatBeijingDate, formatBeijingDateTime } from './BeijingTime'

// ======================== 类型 ========================

export type TimerState =
  | 'stopped'
  | 'studying'
  | 'countup_studying'
  | 'short_breaking'
  | 'long_breaking'
  | 'long_break_finished'

export interface SessionRecord {
  startTime: string
  endTime: string
  netDurationMinutes: number
  netDurationSeconds: number
  date: string
  dayOfWeek: string
  pauseCount: number
  pauseReasons: string
  sessionSummary: string
  categoryId: number | null
  segments?: SessionSegment[]
}

export interface SessionSegment {
  localSegmentKey: string
  startTime: string
  endTime: string
  note: string
}

export interface LogicConfig {
  studyTimeMin: number          // 单轮学习下限（秒）
  studyTimeMax: number          // 单轮学习上限（秒）
  shortBreakDuration: number    // 短休息时长（秒）
  longBreakDuration?: number    // 长休息/自动休息时长（秒）
  longBreakThreshold: number    // 触发胜利的长休息阈值（秒）
}

export interface StartOptions {
  useLongBreakDuration?: boolean
  traceId?: string
}

export interface CategorySwitchResult {
  ok: boolean
  status: 'started' | 'switched' | 'recovered' | 'failed'
  errorCode?: 'missing-session-context' | 'commit-failed' | 'target-not-running'
  record?: SessionRecord | null
}

export interface SleepSwitchResult extends CategorySwitchResult {
  replayed: boolean
}

type LogicAudioCue =
  | 'start'
  | 'pause'
  | 'finish'
  | 'victory'
  | 'microBreak'
  | 'endMicroBreak'
  | 'startLongBreak'
  | 'endLongBreak'

export interface LogicCallbacks {
  onStateChange: (label: string, state: TimerState) => void
  onTick: (elapsedMs: number, remainingMs: number) => void
  onAudioCue: (cue: LogicAudioCue) => void
  onMicroBreak?: (durationSeconds: number) => void
  onSummaryRequested: (isSuccess: boolean, isEarlyEnd: boolean) => void
  onPauseReasonRequested: () => void
  onSessionCommitted: (record: SessionRecord) => void
  onTimerFlow?: (event: string, details: Record<string, any>) => void
}

const DEFAULT_CONFIG: LogicConfig = {
  studyTimeMin: 300,        // 5分钟
  studyTimeMax: 420,        // 7分钟
  shortBreakDuration: 10,   // 10秒
  longBreakDuration: 1200,  // 20分钟
  longBreakThreshold: 5400, // 90分钟
}

const normalizeConfig = (config?: Partial<LogicConfig>): LogicConfig => {
  const merged = { ...DEFAULT_CONFIG, ...config }
  merged.studyTimeMin = Math.max(0, Math.floor(merged.studyTimeMin))
  merged.studyTimeMax = Math.max(merged.studyTimeMin, Math.floor(merged.studyTimeMax))
  merged.shortBreakDuration = Math.max(1, Math.floor(merged.shortBreakDuration))
  merged.longBreakThreshold = Math.max(1, Math.floor(merged.longBreakThreshold))
  if (merged.longBreakDuration !== undefined) {
    merged.longBreakDuration = Math.max(1, Math.floor(merged.longBreakDuration))
  }
  return merged
}

export class LogicEngine {
  // 公开状态
  state: TimerState = 'stopped'
  isPaused = false
  cycleCount = 0

  // 累计
  totalStudySeconds = 0
  currentCycleStudySeconds = 0
  largeSessionNetDuration = 0

  // 当前焦点
  currentFocusTask = ''
  currentCategoryId: number | null = null
  currentCategoryName = ''

  // 挂起切换
  private _pendingSwitchCategory: { id: number, name: string, task: string } | null = null
  private _pendingEarlyEnd = false

  // 内部
  private _config: LogicConfig
  private _callbacks: LogicCallbacks | null = null
  private _timer = new Timer()
  private _sessionStart: Date | null = null
  private _sessionDuration = 0
  private _largeSessionStart: Date | null = null
  private _pauseCount = 0
  private _pauseReasons: string[] = []
  private _pauseStart: Date | null = null
  private _pendingPauseReason: string | null = null
  private _sessionSegments: SessionSegment[] = []
  private _activeSegmentStart: Date | null = null
  private _pendingPauseSegmentIndex: number | null = null
  private _microBreakTimer: ReturnType<typeof setTimeout> | null = null
  private _microBreakEndTimer: ReturnType<typeof setTimeout> | null = null
  private _activeTraceId = ''
  private _appliedSleepCommandIds = new Set<string>()

  constructor(config?: Partial<LogicConfig>) {
    this._config = normalizeConfig(config)
  }

  private _log(event: string, details: Record<string, any> = {}): void {
    const payload = {
      layer: 'LogicEngine',
      event,
      traceId: details.traceId || this._activeTraceId || undefined,
      state: this.state,
      currentCategoryId: this.currentCategoryId,
      currentCategoryName: this.currentCategoryName,
      hasCurrentFocusTask: Boolean(this.currentFocusTask.trim()),
      currentFocusTaskLength: this.currentFocusTask.length,
      currentCycleStudySeconds: this.currentCycleStudySeconds,
      totalStudySeconds: this.totalStudySeconds,
      largeSessionNetDuration: this.largeSessionNetDuration,
      hasSessionStart: Boolean(this._sessionStart),
      hasLargeSessionStart: Boolean(this._largeSessionStart),
      timerRunning: this._timer.running,
      isPaused: this.isPaused,
      hasPendingSwitch: Boolean(this._pendingSwitchCategory),
      ...details,
    }
    if (this._callbacks?.onTimerFlow) this._callbacks.onTimerFlow(event, payload)
    else console.info('[timer-flow]', payload)
  }

  setCallbacks(cbs: LogicCallbacks): void {
    this._callbacks = cbs
  }

  updateConfig(config?: Partial<LogicConfig>): void {
    this._config = normalizeConfig({ ...this._config, ...config })
  }

  exportSnapshot(): LogicSnapshot {
    const elapsedMs = this._timer.getElapsed()
    const isCountup = this.state === 'countup_studying'
    const active = this._activeSegmentStart ? [{ key: 'active', startEpochMs: this._activeSegmentStart.getTime(), endEpochMs: null, note: '' }] : []
    return {
      version: LOGIC_SNAPSHOT_VERSION, capturedAtEpochMs: Date.now(), state: this.state, isPaused: this.isPaused,
      category: { id: this.currentCategoryId, name: this.currentCategoryName, task: this.currentFocusTask },
      pause: { count: this._pauseCount, reasons: [...this._pauseReasons], startedAtEpochMs: this._pauseStart?.getTime() ?? null },
      segments: [...this._sessionSegments.map(segment => ({ key: segment.localSegmentKey, startEpochMs: new Date(segment.startTime).getTime(), endEpochMs: new Date(segment.endTime).getTime(), note: segment.note })), ...active],
      session: { startedAtEpochMs: this._sessionStart?.getTime() ?? null, largeStartedAtEpochMs: this._largeSessionStart?.getTime() ?? null, durationSeconds: this._sessionDuration, totalStudySeconds: this.totalStudySeconds, currentCycleStudySeconds: this.currentCycleStudySeconds, netDurationSeconds: this.largeSessionNetDuration },
      timing: { mode: isCountup ? 'countup' : 'countdown', elapsedMs, deadlineEpochMs: !isCountup && !this.isPaused && this._timer.running ? Date.now() + Math.max(0, (this._timer as any)._totalMs - elapsedMs) : null },
    }
  }

  restoreSnapshot(value: unknown): boolean {
    const result = validateLogicSnapshot(value)
    if (!result.ok) { this.resetCycle(); this._log('snapshot.restore.failed', { reason: result.reason }); return false }
    const snapshot = result.snapshot
    if (snapshot.state === 'stopped' || snapshot.state === 'long_break_finished') { this.resetCycle(); return true }
    const sameStructuredSession = this.state === 'studying'
      && snapshot.state === 'studying'
      && !this.isPaused
      && !snapshot.isPaused
      && this.currentCategoryId === snapshot.category.id
      && this.currentCategoryName === snapshot.category.name
      && this._largeSessionStart?.getTime() === snapshot.session.largeStartedAtEpochMs
    this._timer.stop()
    if (!sameStructuredSession) this._clearMicroBreakTimer()
    this.state = snapshot.state; this.isPaused = snapshot.isPaused; this.currentCategoryId = snapshot.category.id; this.currentCategoryName = snapshot.category.name; this.currentFocusTask = snapshot.category.task
    this._pauseCount = snapshot.pause.count; this._pauseReasons = [...snapshot.pause.reasons]; this._pauseStart = snapshot.pause.startedAtEpochMs ? new Date(snapshot.pause.startedAtEpochMs) : null
    this._sessionStart = snapshot.session.startedAtEpochMs ? new Date(snapshot.session.startedAtEpochMs) : null; this._largeSessionStart = snapshot.session.largeStartedAtEpochMs ? new Date(snapshot.session.largeStartedAtEpochMs) : null
    this._sessionDuration = snapshot.session.durationSeconds; this.totalStudySeconds = snapshot.session.totalStudySeconds; this.currentCycleStudySeconds = snapshot.session.currentCycleStudySeconds; this.largeSessionNetDuration = snapshot.session.netDurationSeconds
    this._sessionSegments = snapshot.segments.filter(segment => segment.key !== 'active').map(segment => ({ localSegmentKey: segment.key, startTime: new Date(segment.startEpochMs).toISOString(), endTime: new Date(segment.endEpochMs!).toISOString(), note: segment.note })); this._activeSegmentStart = snapshot.segments.find(segment => segment.key === 'active')?.startEpochMs ? new Date(snapshot.segments.find(segment => segment.key === 'active')!.startEpochMs) : null
    const elapsedMs = snapshot.timing.elapsedMs + (snapshot.isPaused ? 0 : Math.max(0, Date.now() - snapshot.capturedAtEpochMs)); const totalMs = snapshot.timing.mode === 'countdown' ? Math.max(elapsedMs, snapshot.session.durationSeconds * 1000) : 0
    this._timer.start(totalMs, snapshot.timing.mode, { onTick: (elapsed, remaining) => this._callbacks?.onTick(elapsed, remaining), onFinish: elapsed => { if (this.state === 'studying') this._onTimerFinish(elapsed); else if (this.state === 'long_breaking') this._finishConfiguredLongBreakCycle(elapsed) } }); (this._timer as any)._accumulatedMs = elapsedMs
    if (snapshot.isPaused) this._timer.pause()
    else if (snapshot.state === 'studying') {
      if (sameStructuredSession && (this._microBreakTimer !== null || this._microBreakEndTimer !== null)) {
        this._log('micro-break.preserved')
      } else this._scheduleMicroBreak()
    }
    this._callbacks?.onStateChange('已恢复', this.state); this._callbacks?.onTick(elapsedMs, snapshot.timing.mode === 'countdown' ? Math.max(0, totalMs - elapsedMs) : 0); return true
  }

  start(categoryId: number, categoryName: string, taskName = '', options: StartOptions = {}): void {
    if (options.traceId) this._activeTraceId = options.traceId
    this._log('target.start.before', { targetCategoryId: categoryId, targetCategoryName: categoryName, hasTaskName: Boolean(taskName.trim()), taskNameLength: taskName.length })
    if (this.state !== 'stopped' && this.state !== 'long_break_finished') {
      if (this.currentCategoryId !== categoryId) {
        this._log('start:delegate-switch', { targetCategoryId: categoryId, targetCategoryName: categoryName, hasTaskName: Boolean(taskName.trim()), taskNameLength: taskName.length })
        this.switchCategory(categoryId, categoryName, taskName)
      } else {
        this._log('start:ignored-same-running-category', { targetCategoryId: categoryId, targetCategoryName: categoryName })
      }
      return
    }

    this.isPaused = false
    if (this.state === 'long_break_finished') {
      this.resetCycle()
    }

    const isCountup = !['输入', '输出'].includes(categoryName)

    if (this.state === 'stopped' && !isCountup) {
      this._log('structured-session-boundary:before', { targetCategoryId: categoryId, targetCategoryName: categoryName })
      this.currentCycleStudySeconds = 0
      this.totalStudySeconds = 0
      this.cycleCount = 0
      this._largeSessionStart = null
      this.largeSessionNetDuration = 0
      this._pauseCount = 0
      this._pauseReasons = []
      this._sessionSegments = []
      this._activeSegmentStart = null
      this._pendingPauseSegmentIndex = null
      this._log('structured-session-boundary:after', { targetCategoryId: categoryId, targetCategoryName: categoryName, result: 'cleared' })
    }

    this.currentFocusTask = taskName
    this.currentCategoryId = categoryId
    this.currentCategoryName = categoryName

    if (options.useLongBreakDuration) {
      this._runConfiguredLongBreakCycle()
    } else if (isCountup) {
      this._runCountupCycle()
    } else if (this.currentCycleStudySeconds >= this._config.longBreakThreshold) {
      this._finishLongBreak()
    } else {
      this._runStudyCycle()
    }
    this._log('target.start.after', { targetCategoryId: categoryId, targetCategoryName: categoryName, result: 'started' })
  }

  switchCategory(categoryId: number, categoryName: string, taskName = ''): void {
    this._log('switchCategory:requested', { targetCategoryId: categoryId, targetCategoryName: categoryName, hasTaskName: Boolean(taskName.trim()), taskNameLength: taskName.length })
    if (this.state === 'stopped') {
      this.start(categoryId, categoryName, taskName)
      return
    }
    this._pendingSwitchCategory = { id: categoryId, name: categoryName, task: taskName }
    if (this.state === 'studying') {
      this.endStudyNow()
    } else if (this.state === 'countup_studying') {
      this.endCountupNow()
    } else {
      this._log('switchCategory:pending-without-immediate-end', { targetCategoryId: categoryId, targetCategoryName: categoryName })
    }
  }

  switchCategoryNow(categoryId: number, categoryName: string, taskName = '', summary = '状态切换', traceId = ''): CategorySwitchResult {
    if (traceId) this._activeTraceId = traceId
    this._log('preflight.started', { targetCategoryId: categoryId, targetCategoryName: categoryName, hasTaskName: Boolean(taskName.trim()), taskNameLength: taskName.length, hasSummary: Boolean(summary.trim()), summaryLength: summary.length })
    if (this.state === 'stopped' || this.state === 'long_break_finished') {
      this.start(categoryId, categoryName, taskName, { traceId: this._activeTraceId })
      const ok = this.currentCategoryId === categoryId && this.state !== 'stopped' && this.state !== 'long_break_finished'
      const result: CategorySwitchResult = ok
        ? { ok: true, status: 'started' }
        : { ok: false, status: 'failed', errorCode: 'target-not-running' }
      this._log('engine.switch.result', { targetCategoryId: categoryId, targetCategoryName: categoryName, result: result.status, errorCode: result.errorCode, failedStep: ok ? undefined : 'target.start' })
      return result
    }

    let recovered = false
    if (!this._largeSessionStart) {
      if (!this._sessionStart) {
        const result: CategorySwitchResult = { ok: false, status: 'failed', errorCode: 'missing-session-context' }
        this._log('preflight.failed', { targetCategoryId: categoryId, targetCategoryName: categoryName, result: 'failed', errorCode: result.errorCode, failedStep: 'preflight' })
        return result
      }
      this._largeSessionStart = new Date(this._sessionStart)
      this.currentCycleStudySeconds = 0
      this.totalStudySeconds = 0
      this.largeSessionNetDuration = 0
      recovered = true
      this._log('preflight.recovered', { targetCategoryId: categoryId, targetCategoryName: categoryName, result: 'recovered' })
    } else {
      this._log('preflight.passed', { targetCategoryId: categoryId, targetCategoryName: categoryName, result: 'passed' })
    }

    this._clearMicroBreakTimer()
    this._log('timer.stop.before', { targetCategoryId: categoryId, targetCategoryName: categoryName })
    const elapsed = this._timer.stop().elapsedMs / 1000
    this._log('timer.stop.after', { targetCategoryId: categoryId, targetCategoryName: categoryName, elapsedSeconds: elapsed, result: 'stopped' })
    if (this.state === 'studying') {
      this.totalStudySeconds += elapsed
      this.currentCycleStudySeconds += elapsed
      this._finishStructuredSegment(new Date(), '')
    }
    this.largeSessionNetDuration += elapsed
    this._sessionStart = null
    this._pendingEarlyEnd = false
    this._pendingSwitchCategory = { id: categoryId, name: categoryName, task: taskName }
    const record = this._commitLargeSession(summary)
    if (!record) {
      const result: CategorySwitchResult = { ok: false, status: 'failed', errorCode: 'commit-failed', record }
      return result
    }
    const finalState = this.state as TimerState
    const ok = this.currentCategoryId === categoryId && finalState !== 'stopped' && finalState !== 'long_break_finished'
    const result: CategorySwitchResult = ok
      ? { ok: true, status: recovered ? 'recovered' : 'switched', record }
      : { ok: false, status: 'failed', errorCode: 'target-not-running', record }
    this._log('engine.switch.result', { targetCategoryId: categoryId, targetCategoryName: categoryName, result: result.status, errorCode: result.errorCode })
    return result
  }

  applySleepSwitch(commandId: string, categoryId: number, categoryName = '睡觉'): SleepSwitchResult {
    if (this._appliedSleepCommandIds.has(commandId)) return { ok: true, status: 'started', replayed: true }
    const result = this.switchCategoryNow(categoryId, categoryName, '', '睡眠时间到', commandId)
    if (result.ok) this._appliedSleepCommandIds.add(commandId)
    return { ...result, replayed: false }
  }

  togglePause(): void {
    if (this.isPaused) {
      this._resume()
    } else if (this._timer.running) {
      this._pause()
    }
  }

  submitPauseReason(reason: string): void {
    this._pendingPauseReason = reason.trim()
    if (this._pendingPauseSegmentIndex !== null) {
      this._sessionSegments[this._pendingPauseSegmentIndex].note = this._pendingPauseReason
    }
  }

  skipPauseReason(): void {
    this._pendingPauseReason = null
    this._pendingPauseSegmentIndex = null
  }

  setCurrentFocusTask(taskName: string): void {
    this.currentFocusTask = taskName
  }

  endCountupNow(): void {
    this._log('status-switch.stop.before')
    if ((this.state !== 'countup_studying' && this.state !== 'long_breaking') || !this._sessionStart) {
      this._log('status-switch.stop.failed', { reason: 'not-countup-or-missing-session-start', result: 'failed' })
      return
    }
    // 使用 Timer 内部跟踪的净时间，暂停期间不计入 elapsed
    const stoppedCategoryName = this.currentCategoryName
    const elapsed = this._timer.stop().elapsedMs / 1000
    this.largeSessionNetDuration += elapsed
    const record = this._commitLargeSession(this.currentFocusTask)
    this._log('status-switch.stop.after', { stoppedCategoryName, elapsedSeconds: elapsed, result: record ? 'completed' : 'failed' })
    if (stoppedCategoryName === '状态切换') this._activeTraceId = ''
  }

  endStudyNow(): void {
    if (this.state !== 'studying') return
    this._clearMicroBreakTimer()
    const elapsed = this._timer.stop().elapsedMs / 1000
    this.totalStudySeconds += elapsed
    this.currentCycleStudySeconds += elapsed
    this.largeSessionNetDuration += elapsed
    this._finishStructuredSegment(new Date(), '')
    this._sessionStart = null
    this._pendingEarlyEnd = true
    this._callbacks?.onSummaryRequested(false, true)
  }

  cancelEarlyEnd(): void {
    if (!this._pendingEarlyEnd) return
    this._pendingEarlyEnd = false
    this._pendingSwitchCategory = null
    this.state = 'studying'
    this.isPaused = false
    this._sessionStart = new Date()
    this._startStructuredSegment(this._sessionStart)
    this._callbacks?.onStateChange('学习中...', 'studying')

    const remainingMs = Math.max(0, (this._config.longBreakThreshold - this.currentCycleStudySeconds) * 1000)
    this._callbacks?.onTick(0, remainingMs)
    this._timer.start(remainingMs, 'countdown', {
      onTick: (elapsed, remaining) => this._callbacks?.onTick(elapsed, remaining),
      onFinish: (elapsed) => this._onTimerFinish(elapsed),
    })
    this._scheduleMicroBreak()
  }

  resetCycle(): void {
    this._timer.stop()
    this._clearMicroBreakTimer()
    this.cycleCount = 0
    this.state = 'stopped'
    this.isPaused = false
    this._sessionStart = null
    this._sessionDuration = 0
    this._largeSessionStart = null
    this._pauseCount = 0
    this._pauseReasons = []
    this._sessionSegments = []
    this._activeSegmentStart = null
    this._pendingPauseSegmentIndex = null
    this._pendingSwitchCategory = null
    this._pendingEarlyEnd = false
    this.currentFocusTask = ''
    this.currentCategoryId = null
    this.currentCategoryName = ''
    this.currentCycleStudySeconds = 0
    this.largeSessionNetDuration = 0
    this._callbacks?.onStateChange('就绪', 'stopped')
    this._callbacks?.onTick(0, 0)
    this._log('resetCycle:completed')
  }

  private _runStudyCycle(): void {
    this.cycleCount++
    this.state = 'studying'

    if (!this._largeSessionStart) {
      this._largeSessionStart = new Date()
      this._pauseCount = 0
      this._pauseReasons = []
      this._sessionSegments = []
      this._pendingPauseSegmentIndex = null
      this.largeSessionNetDuration = 0
    }

    this._sessionStart = new Date()
    this._sessionDuration = this._config.longBreakThreshold
    this._startStructuredSegment(this._sessionStart)

    this._callbacks?.onStateChange('学习中...', 'studying')
    
    this._callbacks?.onAudioCue('start')
    this._scheduleMicroBreak()

    this._timer.start(this._config.longBreakThreshold * 1000, 'countdown', {
      onTick: (elapsed, remaining) => this._callbacks?.onTick(elapsed, remaining),
      onFinish: (elapsed) => this._onTimerFinish(elapsed),
    })
  }

  private _runCountupCycle(): void {
    this.state = 'countup_studying'
    if (!this._largeSessionStart) {
      this._largeSessionStart = new Date()
      this._pauseCount = 0
      this._pauseReasons = []
      this._sessionSegments = []
      this._pendingPauseSegmentIndex = null
      this.largeSessionNetDuration = 0
    }
    this._sessionStart = new Date()
    this._sessionDuration = 0
    this._callbacks?.onStateChange('正计时中...', 'countup_studying')
    
    this._timer.start(24 * 3600 * 1000, 'countdown', {
      onTick: (elapsed) => this._callbacks?.onTick(elapsed, 0),
      onFinish: () => {},
    })
  }

  private _runConfiguredLongBreakCycle(): void {
    this.state = 'long_breaking'
    this._largeSessionStart = new Date()
    this._pauseCount = 0
    this._pauseReasons = []
    this._sessionSegments = []
    this._pendingPauseSegmentIndex = null
    this.largeSessionNetDuration = 0
    this._sessionStart = new Date()
    this._sessionDuration = this._config.longBreakDuration || DEFAULT_CONFIG.longBreakDuration || 1200
    this._callbacks?.onStateChange('休息中...', 'long_breaking')
    this._callbacks?.onAudioCue('startLongBreak')

    this._timer.start(this._sessionDuration * 1000, 'countdown', {
      onTick: (elapsed, remaining) => this._callbacks?.onTick(elapsed, remaining),
      onFinish: (elapsed) => this._finishConfiguredLongBreakCycle(elapsed),
    })
  }

  private _finishConfiguredLongBreakCycle(elapsedMs = this._timer.getElapsed()): void {
    if (this.state !== 'long_breaking') return
    const stoppedCategoryName = this.currentCategoryName
    this._log('status-switch.stop.before', { stoppedCategoryName, automatic: true })
    const elapsed = elapsedMs / 1000
    this.largeSessionNetDuration += elapsed
    this._sessionStart = null
    this._callbacks?.onAudioCue('endLongBreak')
    const record = this._commitLargeSession(this.currentFocusTask || '休息')
    this._log('status-switch.stop.after', { stoppedCategoryName, automatic: true, result: record ? 'completed' : 'failed' })
    if (stoppedCategoryName === '状态切换') this._activeTraceId = ''
  }

  private _runShortBreakCycle(): void {
    this._scheduleMicroBreak()
  }

  private _finishLongBreak(): void {
    this._clearMicroBreakTimer()
    this.state = 'long_break_finished'
    this.currentCycleStudySeconds = 0
    this.cycleCount = 0
    this._sessionStart = null
    this._callbacks?.onStateChange('休息完成，开始下一轮', 'long_break_finished')
    this._callbacks?.onTick(0, 0)
    
    if (this._usesStructuredSegments()) {
      this._callbacks?.onAudioCue('victory')
    }
    this._callbacks?.onSummaryRequested(true, false)
  }

  private _onTimerFinish(elapsedMs = this._timer.getElapsed()): void {
    const elapsed = elapsedMs / 1000
    this.totalStudySeconds += elapsed
    this.currentCycleStudySeconds += elapsed
    this.largeSessionNetDuration += elapsed
    this._finishStructuredSegment(new Date(), '')
    this._sessionStart = null
    this._finishLongBreak()
  }

  private _pause(): void {
    if (this.state !== 'studying' && this.state !== 'countup_studying' && this.state !== 'long_breaking') return
    this.isPaused = true
    this._pauseStart = new Date()
    this._pendingPauseReason = null
    this._timer.pause()
    this._clearMicroBreakTimer()
    if (this.state === 'studying') {
      this._pendingPauseSegmentIndex = this._finishStructuredSegment(this._pauseStart, '')
    }
    this._callbacks?.onStateChange('已暂停', this.state)
    if (this.state === 'studying') {
      this._callbacks?.onPauseReasonRequested()
    }
  }

  private _resume(): void {
    if (!this.isPaused) return
    this.isPaused = false
    if (this._pauseStart) {
      const pauseSeconds = (Date.now() - this._pauseStart.getTime()) / 1000
      this._pauseCount++
      const pauseText = this._pendingPauseReason?.trim()
      this._pauseReasons.push(pauseText ? `${pauseText} (${pauseSeconds.toFixed(0)}s)` : `${pauseSeconds.toFixed(0)}s`)
      this._pauseStart = null
      this._pendingPauseReason = null
      this._pendingPauseSegmentIndex = null
    }
    this._timer.resume()
    if (this.state === 'studying') {
      this._startStructuredSegment(new Date())
      this._scheduleMicroBreak()
    }
    this._callbacks?.onStateChange(
      this.state === 'studying' ? '学习中...' : '进行中',
      this.state,
    )
    if (this.state === 'studying' && this._usesStructuredSegments()) {
      this._callbacks?.onAudioCue('start')
    }
  }

  submitSummary(summary: string): SessionRecord | null {
    this._pendingEarlyEnd = false
    if (!this._pendingSwitchCategory) {
      this.currentCycleStudySeconds = 0
      this.totalStudySeconds = 0
    }
    return this._commitLargeSession(summary)
  }

  private _commitLargeSession(summary: string): SessionRecord | null {
    this._log('commit.requested', { hasSummary: Boolean(summary.trim()), summaryLength: summary.length })
    if (!this._largeSessionStart) {
      this._log('commit.failed', { reason: 'missing-large-session-start', errorCode: 'missing-large-session-start', failedStep: 'commit', hasSummary: Boolean(summary.trim()), summaryLength: summary.length })
      return null
    }

    const now = new Date()
    const netSeconds = Math.max(0, Math.floor(this.largeSessionNetDuration))
    const netMinutes = Math.round(netSeconds / 60 * 100) / 100
    const finalSummary = summary.trim() ? summary : this.currentFocusTask
    const summaryText = finalSummary.trim()
    
    if (this._activeSegmentStart) {
      this._finishStructuredSegment(now, summaryText)
    }

    const dateStr = this._formatDate(now)
    const dayName = beijingDayName(now)

    const record: SessionRecord = {
      startTime: this._formatDt(this._largeSessionStart),
      endTime: this._formatDt(now),
      netDurationMinutes: netMinutes,
      netDurationSeconds: netSeconds,
      date: dateStr,
      dayOfWeek: dayName,
      pauseCount: this._pauseCount,
      pauseReasons: this._pauseReasons.join('; ') || '无',
      sessionSummary: finalSummary,
      categoryId: this.currentCategoryId,
      segments: this._buildStructuredSegments(summaryText),
    }

    this._log('commit.record-ready', {
      categoryId: record.categoryId,
      hasSessionSummary: Boolean(record.sessionSummary.trim()),
      sessionSummaryLength: record.sessionSummary.length,
      netDurationSeconds: record.netDurationSeconds,
      hasPendingSwitch: Boolean(this._pendingSwitchCategory),
    })
    this._callbacks?.onSessionCommitted(record)

    const nextCat = this._pendingSwitchCategory
    const committedCategoryName = this.currentCategoryName
    this._log('pending.consume', { targetCategoryId: nextCat?.id, targetCategoryName: nextCat?.name, result: nextCat ? 'consumed' : 'empty' })
    this._pendingSwitchCategory = null
    this._largeSessionStart = null
    this._pauseCount = 0
    this._pauseReasons = []
    this._sessionSegments = []
    this._activeSegmentStart = null
    this._pendingPauseSegmentIndex = null
    this.largeSessionNetDuration = 0

    if (!nextCat && committedCategoryName === '状态切换') {
      this._log('status-switch.cleanup.before')
      this.currentCycleStudySeconds = 0
      this.totalStudySeconds = 0
      this.cycleCount = 0
      this._log('status-switch.cleanup.after', { result: 'cleared' })
    }

    this.state = 'stopped'
    this._sessionStart = null
    this.currentFocusTask = ''
    this.currentCategoryId = null
    this.currentCategoryName = ''
    this._callbacks?.onStateChange('就绪', 'stopped')
    this._callbacks?.onTick(0, 0)
    this._log('commit.stopped-context-cleared', {
      committedCategoryId: record.categoryId,
      hasSessionSummary: Boolean(record.sessionSummary.trim()),
      sessionSummaryLength: record.sessionSummary.length,
      hasPendingSwitch: Boolean(nextCat),
    })
    
    if (nextCat) {
      this.start(nextCat.id, nextCat.name, nextCat.task)
    }

    this._log('commit.completed', {
      committedCategoryId: record.categoryId,
      hasSessionSummary: Boolean(record.sessionSummary.trim()),
      sessionSummaryLength: record.sessionSummary.length,
      hasPendingSwitch: Boolean(nextCat),
    })
    return record
  }

  private _randDuration(): number {
    const { studyTimeMin, studyTimeMax } = this._config
    return Math.floor(Math.random() * (studyTimeMax - studyTimeMin + 1)) + studyTimeMin
  }

  private _scheduleMicroBreak(): void {
    this._clearMicroBreakTimer()
    if (!this._usesStructuredSegments() || this.state !== 'studying' || this.isPaused) {
      this._log('micro-break.skipped', { reason: 'ineligible-state' }); return
    }
    const delaySeconds = this._randDuration()
    const remainingSeconds = (this._sessionDuration || this._config.longBreakThreshold) - this._timer.getElapsed() / 1000
    if (remainingSeconds <= delaySeconds) {
      this._log('micro-break.skipped', { reason: 'insufficient-remaining', delaySeconds }); return
    }
    this._microBreakTimer = setTimeout(() => {
      if (this.state !== 'studying' || this.isPaused) return
      this._microBreakTimer = null
      this._log('micro-break.started')
      this._callbacks?.onMicroBreak?.(this._config.shortBreakDuration)
      this._callbacks?.onAudioCue('microBreak')
      this._microBreakEndTimer = setTimeout(() => {
        this._microBreakEndTimer = null
        if (this.state !== 'studying' || this.isPaused) return
        this._log('micro-break.finished')
        this._callbacks?.onAudioCue('endMicroBreak')
      }, this._config.shortBreakDuration * 1000)
      this._scheduleNextMicroBreak()
    }, delaySeconds * 1000)
    this._log('micro-break.scheduled', { stage: 'initial', delaySeconds })
  }

  private _scheduleNextMicroBreak(): void {
    if (!this._usesStructuredSegments() || this.state !== 'studying' || this.isPaused) return
    const delaySeconds = Math.max(1, this._randDuration())
    const remainingSeconds = (this._sessionDuration || this._config.longBreakThreshold) - this._timer.getElapsed() / 1000
    if (remainingSeconds <= delaySeconds) {
      this._log('micro-break.skipped', { reason: 'insufficient-remaining', delaySeconds }); return
    }
    this._microBreakTimer = setTimeout(() => {
      if (this.state !== 'studying' || this.isPaused) return
      this._microBreakTimer = null
      this._log('micro-break.started')
      this._callbacks?.onMicroBreak?.(this._config.shortBreakDuration)
      this._callbacks?.onAudioCue('microBreak')
      this._microBreakEndTimer = setTimeout(() => {
        this._microBreakEndTimer = null
        if (this.state !== 'studying' || this.isPaused) return
        this._log('micro-break.finished')
        this._callbacks?.onAudioCue('endMicroBreak')
      }, this._config.shortBreakDuration * 1000)
      this._scheduleNextMicroBreak()
    }, delaySeconds * 1000)
    this._log('micro-break.scheduled', { stage: 'next', delaySeconds })
  }

  private _clearMicroBreakTimer(): void {
    if (this._microBreakTimer !== null) {
      clearTimeout(this._microBreakTimer)
      this._microBreakTimer = null
    }
    if (this._microBreakEndTimer !== null) {
      clearTimeout(this._microBreakEndTimer)
      this._microBreakEndTimer = null
    }
  }

  private _formatDt(d: Date): string {
    return formatBeijingDateTime(d)
  }

  private _formatDate(d: Date): string {
    return formatBeijingDate(d)
  }

  private _usesStructuredSegments(): boolean {
    return ['输入', '输出'].includes(this.currentCategoryName)
  }

  private _startStructuredSegment(startedAt: Date): void {
    if (!this._usesStructuredSegments()) return
    this._activeSegmentStart = startedAt
  }

  private _finishStructuredSegment(finishedAt: Date, note: string): number | null {
    if (!this._usesStructuredSegments() || !this._activeSegmentStart) return null
    const segment: SessionSegment = {
      localSegmentKey: `segment:${this._sessionSegments.length + 1}`,
      startTime: this._formatDt(this._activeSegmentStart),
      endTime: this._formatDt(finishedAt),
      note,
    }
    this._sessionSegments.push(segment)
    this._activeSegmentStart = null
    return this._sessionSegments.length - 1
  }

  private _buildStructuredSegments(summary: string): SessionSegment[] | undefined {
    if (!this._usesStructuredSegments()) return undefined
    const segments = this._sessionSegments
      .filter(segment => segment.startTime <= segment.endTime)
      .map(segment => ({ ...segment }))
    if (summary && segments.length > 0) {
      const emptyIndex = segments.reduce((found, segment, index) => (
        !segment.note ? index : found
      ), -1)
      if (emptyIndex >= 0) {
        segments[emptyIndex] = { ...segments[emptyIndex], note: summary }
      }
    }
    return segments
  }
}
