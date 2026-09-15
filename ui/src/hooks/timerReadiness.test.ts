import type { CurrentTimerOutcome } from '@core/ApiClient'
import { isTimerCommandReady, timerReadinessFromOutcome } from './timerReadiness'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const outcome = (code: CurrentTimerOutcome['code']): CurrentTimerOutcome => ({ code, status: code === 'accepted' ? 200 : 0 })

assert(timerReadinessFromOutcome({ ...outcome('accepted'), state: null }) === 'ready', 'accepted stopped state must be ready')
assert(timerReadinessFromOutcome(outcome('network')) === 'network_failed', 'network must stay distinct')
assert(timerReadinessFromOutcome(outcome('auth')) === 'auth_failed', 'auth must stay distinct')
assert(timerReadinessFromOutcome(outcome('upgrade_required')) === 'upgrade_required', 'upgrade must stay distinct')
assert(timerReadinessFromOutcome(outcome('error')) === 'unavailable', 'unknown failures must be unavailable')
assert(timerReadinessFromOutcome(null) === 'unavailable', 'missing client outcome must be unavailable')
assert(isTimerCommandReady('ready') && !isTimerCommandReady('initializing'), 'only ready may send commands')
console.log('timer readiness tests passed')
