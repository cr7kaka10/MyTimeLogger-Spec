import type { CurrentTimerState } from '@core/ApiClient'
import { automaticLongBreakStopIntent, decideTimerAudioEffect } from './timerAudioEffects'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const state = (category: string, revision = 1): CurrentTimerState => ({
  user_id: 1, session_id: `session-${category}`, owner_device_id: 'pc',
  category_id: 1, category_name: category, state: 'running', active: true,
  started_at: '2026-07-26 01:00:00+08:00', segment_started_at: '2026-07-26 01:00:00+08:00',
  active_elapsed_ms: 0, timer_mode: 'countdown', duration_ms: 120000, revision,
  last_command_seq: 0, last_heartbeat_at: '', updated_at: '', server_time: '2026-07-26 01:00:00+08:00',
})
const accepted = { code: 'accepted', status: 200 } as const

const passive = decideTimerAudioEffect(state('输入'), accepted, { source: 'refresh' })
assert(!passive.dispatch && passive.cue === 'start', 'passive refresh must stay silent')
const started = decideTimerAudioEffect(state('输入'), accepted, { source: 'command', operation: 'start', intent: 'start-1' })
assert(started.dispatch && started.cue === 'start', 'local structured start must play start cue')
const duplicate = decideTimerAudioEffect(state('输入'), accepted, { source: 'command', operation: 'start', intent: 'start-1' }, started.key)
assert(!duplicate.dispatch && duplicate.reason === 'duplicate', 'same revision and intent must deduplicate')
const resumed = decideTimerAudioEffect(state('输出', 2), accepted, { source: 'command', operation: 'resume', intent: 'resume-1' })
assert(resumed.dispatch && resumed.cue === 'start', 'structured resume must play start cue')
const longBreak = decideTimerAudioEffect(state('状态切换'), accepted, { source: 'command', operation: 'switch', intent: 'rest-1' })
assert(longBreak.dispatch && longBreak.cue === 'startLongBreak', 'automatic rest must use long-break cue')
assert(!decideTimerAudioEffect(state('家庭'), accepted, { source: 'command', operation: 'start' }).dispatch, 'ordinary timer must stay silent')
assert(automaticLongBreakStopIntent('same') === automaticLongBreakStopIntent('same'), 'same session stop intent must be stable')
assert(automaticLongBreakStopIntent('same') !== automaticLongBreakStopIntent('other'), 'different sessions need different stop intents')
console.log('timer audio effects tests passed')
