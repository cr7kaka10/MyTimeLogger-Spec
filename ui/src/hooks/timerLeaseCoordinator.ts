import type {
  CurrentTimerCommandRequest,
  CurrentTimerOperation,
  CurrentTimerOutcome,
  CurrentTimerState,
} from '@core/ApiClient'
import { LOGIC_SNAPSHOT_VERSION, type LogicSnapshot } from '@core/LogicSnapshot'

export interface CurrentTimerClient {
  readCurrentTimer(timeout?: number): Promise<CurrentTimerOutcome>
  commandCurrentTimer(
    operation: CurrentTimerOperation,
    request: CurrentTimerCommandRequest,
    timeout?: number,
  ): Promise<CurrentTimerOutcome>
}

export interface CurrentTimerCommandInput {
  sessionId?: string
  categoryId?: number | string | null
  categoryName?: string
  currentNote?: string
  timerMode?: 'countup' | 'countdown'
  durationMs?: number
  sessionSummary?: string
  userIntentId?: string
}

export interface CurrentTimerReconcileContext {
  source: 'refresh' | 'command'
  operation?: CurrentTimerOperation
  intent?: string
}

export const currentTimerElapsedMs = (state: CurrentTimerState): number => {
  if (state.state !== 'running' || !state.segment_started_at) return Math.max(0, state.active_elapsed_ms)
  const serverNow = Date.parse(state.server_time)
  const segmentStarted = Date.parse(state.segment_started_at)
  if (!Number.isFinite(serverNow) || !Number.isFinite(segmentStarted)) return Math.max(0, state.active_elapsed_ms)
  return Math.max(0, state.active_elapsed_ms + serverNow - segmentStarted)
}

export function currentTimerLogicSnapshot(state: CurrentTimerState | null, localNowMs = Date.now()): LogicSnapshot {
  if (!state || state.state === 'stopped') {
    return {
      version: LOGIC_SNAPSHOT_VERSION, capturedAtEpochMs: localNowMs, state: 'stopped', isPaused: false,
      category: { id: null, name: '', task: '' },
      pause: { count: 0, reasons: [], startedAtEpochMs: null },
      segments: [],
      session: { startedAtEpochMs: null, largeStartedAtEpochMs: null, durationSeconds: 0, totalStudySeconds: 0, currentCycleStudySeconds: 0, netDurationSeconds: 0 },
      timing: { mode: 'countup', elapsedMs: 0, deadlineEpochMs: null },
    }
  }
  const elapsedMs = currentTimerElapsedMs(state)
  const countdown = state.timer_mode === 'countdown'
  const structured = ['输入', '输出'].includes(state.category_name)
  const longBreak = countdown && state.category_name === '状态切换'
  const effectiveCountdown = countdown && (structured || longBreak)
  const startedAt = Date.parse(state.started_at)
  const segmentStarted = state.segment_started_at ? Date.parse(state.segment_started_at) : startedAt
  return {
    version: LOGIC_SNAPSHOT_VERSION,
    capturedAtEpochMs: localNowMs,
    state: longBreak ? 'long_breaking' : effectiveCountdown ? 'studying' : 'countup_studying',
    isPaused: state.state === 'paused',
    category: { id: Number.isFinite(Number(state.category_id)) ? Number(state.category_id) : null, name: state.category_name, task: state.current_note || '' },
    pause: { count: state.pause_count || 0, reasons: [], startedAtEpochMs: state.state === 'paused' ? localNowMs : null },
    segments: [{ key: 'active', startEpochMs: Number.isFinite(segmentStarted) ? segmentStarted : localNowMs, endEpochMs: null, note: state.current_note || '' }],
    session: {
      startedAtEpochMs: Number.isFinite(startedAt) ? startedAt : localNowMs,
      largeStartedAtEpochMs: Number.isFinite(startedAt) ? startedAt : localNowMs,
      durationSeconds: Math.max(0, Math.floor((state.duration_ms || 0) / 1000)),
      totalStudySeconds: Math.floor(elapsedMs / 1000),
      currentCycleStudySeconds: Math.floor(elapsedMs / 1000),
      netDurationSeconds: Math.floor(elapsedMs / 1000),
    },
    timing: {
      mode: effectiveCountdown ? 'countdown' : 'countup',
      elapsedMs,
      deadlineEpochMs: effectiveCountdown && state.state === 'running'
        ? localNowMs + Math.max(0, (state.duration_ms || 0) - elapsedMs)
        : null,
    },
  }
}

export class CurrentTimerCoordinator {
  private current: CurrentTimerState | null = null
  private refreshPromise: Promise<CurrentTimerOutcome> | null = null

  constructor(
    private readonly client: CurrentTimerClient,
    private readonly deviceId: string,
    private readonly onState: (state: CurrentTimerState | null, outcome: CurrentTimerOutcome, context: CurrentTimerReconcileContext) => void,
  ) {}

  snapshot(): CurrentTimerState | null {
    return this.current
  }

  async refresh(): Promise<CurrentTimerOutcome> {
    if (this.refreshPromise) return this.refreshPromise
    this.refreshPromise = this.client.readCurrentTimer().then(outcome => {
      if (outcome.code === 'accepted') {
        this.current = outcome.state || null
        this.onState(this.current, outcome, { source: 'refresh' })
      }
      return outcome
    }).finally(() => { this.refreshPromise = null })
    return this.refreshPromise
  }

  async command(operation: CurrentTimerOperation, input: CurrentTimerCommandInput = {}): Promise<CurrentTimerOutcome> {
    const synced = await this.refresh()
    if (synced.code !== 'accepted') return synced
    const intent = input.userIntentId || `${operation}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const execute = async (attempt: number): Promise<CurrentTimerOutcome> => {
      const request: CurrentTimerCommandRequest = {
        session_id: input.sessionId,
        device_id: this.deviceId,
        observed_revision: this.current?.revision || 0,
        idempotency_key: `${intent}:${attempt}`,
        user_intent_id: intent,
        category_id: input.categoryId,
        category_name: input.categoryName,
        current_note: input.currentNote,
        timer_mode: input.timerMode,
        duration_ms: input.durationMs,
        session_summary: input.sessionSummary,
      }
      return this.client.commandCurrentTimer(operation, request)
    }
    let outcome = await execute(1)
    if (outcome.code === 'network') {
      // 响应可能在服务端已提交后丢失；原幂等键重发只能得到原结果。
      outcome = await execute(1)
    }
    if (outcome.code === 'stale_revision') {
      const latest = await this.refresh()
      if (latest.code !== 'accepted') return latest
      outcome = await execute(2)
    }
    if (outcome.code === 'accepted') {
      this.current = outcome.state || null
      this.onState(this.current, outcome, { source: 'command', operation, intent })
    } else if (outcome.state) {
      this.current = outcome.state
      this.onState(this.current, outcome, { source: 'command', operation, intent })
    }
    return outcome
  }
}
