import type { CurrentTimerOutcome, CurrentTimerState } from '@core/ApiClient'
import type { CurrentTimerReconcileContext } from './timerLeaseCoordinator'

export type AuthoritativeAudioCue = 'start' | 'startLongBreak'
export interface TimerAudioEffect {
  cue: AuthoritativeAudioCue | null
  key: string
  dispatch: boolean
  reason: 'dispatch' | 'refresh' | 'duplicate' | 'ineligible'
}

const candidateCue = (state: CurrentTimerState | null): AuthoritativeAudioCue | null => {
  if (!state?.active || state.timer_mode !== 'countdown') return null
  if (['输入', '输出'].includes(state.category_name)) return 'start'
  if (state.category_name === '状态切换') return 'startLongBreak'
  return null
}

export const decideTimerAudioEffect = (
  state: CurrentTimerState | null,
  outcome: CurrentTimerOutcome,
  context: CurrentTimerReconcileContext,
  previousKey = '',
): TimerAudioEffect => {
  const cue = candidateCue(state)
  if (!cue) return { cue: null, key: '', dispatch: false, reason: 'ineligible' }
  if (context.source === 'refresh') return { cue, key: '', dispatch: false, reason: 'refresh' }
  const operation = context.operation
  const eligible = operation === 'start' || operation === 'switch'
    || (operation === 'resume' && cue === 'start')
  if (outcome.code !== 'accepted' || !eligible) return { cue: null, key: '', dispatch: false, reason: 'ineligible' }
  const key = `${state!.session_id}:${state!.revision}:${context.intent || ''}:${cue}`
  return { cue, key, dispatch: key !== previousKey, reason: key === previousKey ? 'duplicate' : 'dispatch' }
}

export const automaticLongBreakStopIntent = (sessionId: string): string =>
  `long-break-complete:${sessionId}`
