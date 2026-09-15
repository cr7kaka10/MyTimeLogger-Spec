import type { CurrentTimerOutcome } from '@core/ApiClient'

export type TimerReadiness = 'initializing' | 'ready' | 'network_failed' | 'auth_failed' | 'upgrade_required' | 'unavailable'

export const timerReadinessFromOutcome = (outcome: CurrentTimerOutcome | null | undefined): TimerReadiness => {
  switch (outcome?.code) {
    case 'accepted': return 'ready'
    case 'network': return 'network_failed'
    case 'auth': return 'auth_failed'
    case 'upgrade_required': return 'upgrade_required'
    default: return 'unavailable'
  }
}

export const isTimerCommandReady = (readiness: TimerReadiness): boolean => readiness === 'ready'
