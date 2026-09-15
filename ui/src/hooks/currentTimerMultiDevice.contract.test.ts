import type {
  CurrentTimerCommandRequest,
  CurrentTimerOperation,
  CurrentTimerOutcome,
  CurrentTimerState,
} from '@core/ApiClient'
import {
  CurrentTimerCoordinator,
  currentTimerLogicSnapshot,
  type CurrentTimerReconcileContext,
} from './timerLeaseCoordinator'
import { decideTimerAudioEffect } from './timerAudioEffects'
import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const timerHook = readFileSync(new URL('./useTimer.ts', import.meta.url), 'utf8')
assert(!timerHook.includes('db.logSession('), 'current-state mirrors must never write a local completed session')
assert(timerHook.includes("reason: 'server-authoritative-history'"), 'completed history must be reserved for stable server pull')

class Authority {
  current: CurrentTimerState | null = null
  private results = new Map<string, CurrentTimerOutcome>()

  read = async (): Promise<CurrentTimerOutcome> => ({
    code: 'accepted', status: 200, state: this.current, revision: this.current?.revision,
  })

  command = async (operation: CurrentTimerOperation, request: CurrentTimerCommandRequest): Promise<CurrentTimerOutcome> => {
    const replay = this.results.get(request.idempotency_key)
    if (replay) return replay
    const revision = this.current?.revision || 0
    if (request.observed_revision !== revision) {
      return { code: 'stale_revision', status: 409, state: this.current, revision, errorCode: 'stale_timer_revision' }
    }
    const nextRevision = revision + 1
    const running = operation !== 'stop'
    this.current = {
      user_id: 1,
      session_id: this.current?.session_id || request.session_id || 'session',
      owner_device_id: request.device_id,
      updated_by_device_id: request.device_id,
      category_id: request.category_id ?? this.current?.category_id ?? null,
      category_name: request.category_name || this.current?.category_name || '',
      current_note: request.current_note ?? this.current?.current_note ?? '',
      state: running ? (operation === 'pause' ? 'paused' : 'running') : 'stopped',
      active: running,
      started_at: this.current?.started_at || '2026-07-24 20:00:00+08:00',
      segment_started_at: running ? '2026-07-24 20:00:00+08:00' : null,
      active_elapsed_ms: operation === 'switch' ? 0 : (this.current?.active_elapsed_ms || 0),
      timer_mode: request.timer_mode || this.current?.timer_mode || 'countup',
      duration_ms: request.duration_ms || this.current?.duration_ms || 0,
      pause_count: this.current?.pause_count || 0,
      revision: nextRevision,
      last_command_seq: 0,
      last_user_intent_id: request.user_intent_id,
      last_heartbeat_at: '2026-07-24 20:00:00+08:00',
      updated_at: '2026-07-24 20:00:00+08:00',
      server_time: '2026-07-24 20:00:00+08:00',
    }
    const outcome = { code: 'accepted', status: 200, state: this.current, revision: nextRevision } as CurrentTimerOutcome
    this.results.set(request.idempotency_key, outcome)
    return outcome
  }
}

const authority = new Authority()
const pcImports: CurrentTimerState[] = []
const androidImports: CurrentTimerState[] = []
const pcContexts: CurrentTimerReconcileContext[] = []
const androidContexts: CurrentTimerReconcileContext[] = []
let androidATimeLoggerCalls = 0
const client = { readCurrentTimer: authority.read, commandCurrentTimer: authority.command }
const pc = new CurrentTimerCoordinator(client, 'pc', (state, _outcome, context) => {
  if (state) pcImports.push(state)
  pcContexts.push(context)
})
const android = new CurrentTimerCoordinator(client, 'android', (state, _outcome, context) => {
  if (state) androidImports.push(state)
  androidContexts.push(context)
})

await pc.command('start', { sessionId: 'shared', categoryId: 1, categoryName: '状态切换', currentNote: '学习任务', userIntentId: 'pc-start' })
await android.refresh()
assert(androidImports.at(-1)?.category_name === '状态切换', 'PC start must appear as the same Android timer after refresh')
assert(androidImports.at(-1)?.current_note === '学习任务', 'PC task note must appear on Android after refresh')
assert(currentTimerLogicSnapshot(androidImports.at(-1)!).category.name === '状态切换', 'Android must render the standard timer shape')
assert(androidContexts.at(-1)?.source === 'refresh', 'Android observer must classify the PC start as passive refresh')
assert(!decideTimerAudioEffect(androidImports.at(-1)!, {
  code: 'accepted', status: 200, state: androidImports.at(-1),
}, androidContexts.at(-1)!).dispatch, 'Android passive refresh must not become a local audio action')
assert(androidATimeLoggerCalls === 0, 'observing a remote revision must not call aTimeLogger')

const androidSwitch = await android.command('switch', { categoryId: 2, categoryName: '吃饭', userIntentId: 'android-switch' })
if (androidSwitch.code === 'accepted') androidATimeLoggerCalls += 1
await pc.refresh()
assert(pcImports.at(-1)?.category_name === '吃饭', 'Android switch must replace the PC category after refresh')
assert(pcImports.at(-1)?.revision === androidSwitch.revision, 'both devices must converge on the same revision')
assert(pcContexts.at(-1)?.source === 'refresh', 'PC observer must classify the Android switch as passive refresh')
assert(androidATimeLoggerCalls === 1, 'only the action initiator may call aTimeLogger once')
await android.command('note', { currentNote: '午饭', userIntentId: 'android-note' })
await pc.refresh()
assert(pcImports.at(-1)?.current_note === '午饭', 'later authoritative note edit must converge on PC')

const beforeRace = authority.current!.revision
const pcRace = pc.command('switch', { categoryId: 3, categoryName: '家庭', userIntentId: 'pc-race' })
const androidRace = android.command('switch', { categoryId: 4, categoryName: '娱乐', userIntentId: 'android-race' })
await Promise.all([pcRace, androidRace])
assert(authority.current!.revision >= beforeRace + 2, 'the later stale foreground intent must refresh and become a higher revision')
console.log('current timer multi-device contract passed')
