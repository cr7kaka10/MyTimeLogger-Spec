import { activeElementTag, createTimerInputTrace } from './timerInputTelemetry'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
let time = 100
const events: Array<{ event: string; details: Record<string, any> }> = []
const trace = createTimerInputTrace('summary', {
  now: () => time,
  traceId: 'focus-trace',
  sink: (event, details) => events.push({ event, details }),
})
trace.mark('sheet.mount.requested', { note: 'secret', token: 'secret' })
time = 123
trace.mark('sheet.mount.completed')
time = 145
trace.mark('focus.verified', { activeElementTag: activeElementTag({ tagName: 'TEXTAREA' }) })
time = 180
trace.mark('event-loop.lag', { eventLoopLagMs: 30 })

assert(events.every(item => item.details.traceId === 'focus-trace'), 'events must share one trace')
assert(events.map(item => item.details.durationMs).join(',') === '0,23,45,80', 'duration must use one start time')
assert(events[2].details.activeElementTag === 'TEXTAREA', 'active element tag must be preserved')
assert(events[3].details.eventLoopLagMs === 30, 'event-loop lag must be preserved')
assert(events.every(item => !('note' in item.details) && !('token' in item.details)), 'sensitive fields must be dropped')
console.log('timerInputTelemetry tests passed')
