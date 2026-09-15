import type { CurrentTimerOutcome, CurrentTimerState } from '@core/ApiClient'
import {
  CurrentTimerCoordinator,
  currentTimerElapsedMs,
  currentTimerLogicSnapshot,
  type CurrentTimerReconcileContext,
} from './timerLeaseCoordinator'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const state = (revision: number, category = '输入', timerState: CurrentTimerState['state'] = 'running'): CurrentTimerState => ({
  user_id: 1, session_id: 'session', owner_device_id: 'pc', updated_by_device_id: 'pc',
  category_id: 1, category_name: category, state: timerState, active: timerState !== 'stopped',
  current_note: '任务标题',
  started_at: '2026-07-24 20:00:00+08:00', segment_started_at: '2026-07-24 20:00:05+08:00',
  active_elapsed_ms: 2000, timer_mode: 'countup', duration_ms: 0, pause_count: 0,
  revision, last_command_seq: 0, last_heartbeat_at: '2026-07-24 20:00:10+08:00',
  updated_at: '2026-07-24 20:00:10+08:00', server_time: '2026-07-24 20:00:10+08:00',
})
const accepted = (value: CurrentTimerState | null): CurrentTimerOutcome => ({
  code: 'accepted', status: 200, state: value, lease: value, revision: value?.revision,
})

assert(currentTimerElapsedMs(state(1)) === 7000, 'elapsed must use server baseline')
const imported = currentTimerLogicSnapshot(state(1), Date.parse('2030-01-01T00:00:00Z'))
assert(imported.timing.elapsedMs === 7000, 'client wall clock skew must not alter imported elapsed')
assert(imported.state === 'countup_studying' && imported.category.name === '输入', 'running state must import standard timer shape')
assert(imported.category.task === '任务标题', 'authoritative note must import into the standard timer snapshot')
const paused = currentTimerLogicSnapshot({ ...state(2), state: 'paused', active_elapsed_ms: 9000, segment_started_at: null })
assert(paused.isPaused && paused.timing.elapsedMs === 9000, 'paused elapsed must freeze')
const inputCountdown = currentTimerLogicSnapshot({ ...state(2), timer_mode: 'countdown', duration_ms: 120000 })
assert(inputCountdown.state === 'studying', 'input/output countdown must restore structured focus')
const longBreak = currentTimerLogicSnapshot({ ...state(2, '状态切换'), timer_mode: 'countdown', duration_ms: 60000 })
assert(longBreak.state === 'long_breaking', 'status-switch countdown must restore automatic long break')
const ordinaryCountdown = currentTimerLogicSnapshot({ ...state(2, '家庭'), timer_mode: 'countdown', duration_ms: 60000 })
assert(ordinaryCountdown.state === 'countup_studying' && ordinaryCountdown.timing.mode === 'countup', 'ordinary categories must remain count-up')

const reads: CurrentTimerOutcome[] = [accepted(state(1)), accepted(state(2))]
const commandCalls: Array<Record<string, unknown>> = []
const importedStates: Array<CurrentTimerState | null> = []
const reconcileContexts: CurrentTimerReconcileContext[] = []
let commandCount = 0
const coordinator = new CurrentTimerCoordinator({
  readCurrentTimer: async () => reads.shift()!,
  commandCurrentTimer: async (_operation, request) => {
    commandCalls.push(request as unknown as Record<string, unknown>)
    commandCount += 1
    return commandCount === 1
      ? { code: 'stale_revision', status: 409, state: state(2), revision: 2 }
      : accepted(state(3, '家庭'))
  },
}, 'android', (value, _outcome, context) => {
  importedStates.push(value)
  reconcileContexts.push(context)
})

const result = await coordinator.command('switch', { categoryId: 3, categoryName: '家庭', userIntentId: 'intent' })
assert(result.code === 'accepted' && result.state?.revision === 3, 'stale foreground intent must refresh and retry once')
assert(commandCalls.length === 2, 'foreground intent must retry at most once')
assert(commandCalls[0].observed_revision === 1 && commandCalls[1].observed_revision === 2, 'retry must use refreshed revision')
assert(commandCalls[0].user_intent_id === commandCalls[1].user_intent_id, 'retry must preserve user intent id')
assert(importedStates.at(-1)?.category_name === '家庭', 'accepted state must become the shared UI state')
assert(commandCalls[0].current_note === undefined, 'commands without notes must stay backward compatible')
assert(reconcileContexts.filter(item => item.source === 'refresh').length === 2, 'preflight and stale refreshes must stay passive')
const commandContext = reconcileContexts.at(-1)!
assert(commandContext.source === 'command' && commandContext.operation === 'switch' && commandContext.intent === 'intent', 'accepted command must expose operation and intent')

const responseLossKeys: string[] = []
let responseLossAttempt = 0
const responseLoss = new CurrentTimerCoordinator({
  readCurrentTimer: async () => accepted(state(3)),
  commandCurrentTimer: async (_operation, request) => {
    responseLossKeys.push(request.idempotency_key)
    responseLossAttempt += 1
    return responseLossAttempt === 1 ? { code: 'network', status: 0 } : accepted(state(4, '吃饭'))
  },
}, 'pc', () => undefined)
assert((await responseLoss.command('switch', { categoryName: '吃饭', userIntentId: 'loss' })).code === 'accepted', 'lost response must recover')
assert(responseLossKeys.length === 2 && responseLossKeys[0] === responseLossKeys[1], 'response loss retry must reuse the exact idempotency key')
console.log('current timer coordinator tests passed')
