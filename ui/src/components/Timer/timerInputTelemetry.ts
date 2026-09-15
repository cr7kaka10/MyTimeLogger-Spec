import { emitTimerFlow } from '../../utils/timerFlow'

export type TimerInputPanel = 'note' | 'summary' | 'pause' | 'status'
export type TimerInputEvent = 'sheet.mount.requested' | 'sheet.mount.completed' | 'focus.attempted' | 'focus.verified' | 'focus.retry' | 'focus.lost' | 'event-loop.lag'
type Sink = (event: string, details: Record<string, unknown>) => unknown

export interface TimerInputTrace {
  traceId: string
  panel: TimerInputPanel
  mark: (event: TimerInputEvent, details?: Record<string, unknown>) => void
}

const safeDetails = (details: Record<string, unknown>) => ({
  activeElementTag: typeof details.activeElementTag === 'string' ? details.activeElementTag : undefined,
  eventLoopLagMs: typeof details.eventLoopLagMs === 'number' ? details.eventLoopLagMs : undefined,
  reason: typeof details.reason === 'string' ? details.reason : undefined,
})

export const createTimerInputTrace = (panel: TimerInputPanel, options: { now?: () => number; sink?: Sink; traceId?: string } = {}): TimerInputTrace => {
  const now = options.now || (() => performance.now())
  const startedAt = now()
  const traceId = options.traceId || `timer-input-${panel}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const sink = options.sink || ((event, details) => emitTimerFlow('TimerInput', event, details))
  return { traceId, panel, mark: (event, details = {}) => sink(event, { traceId, panel, durationMs: Math.max(0, now() - startedAt), ...safeDetails(details) }) }
}

export const activeElementTag = (element: any): string => String(element?.tagName || (element?.isContentEditable ? 'CONTENTEDITABLE' : 'NONE'))

export const observeEventLoopLag = (trace: TimerInputTrace, delayMs = 50): (() => void) => {
  const startedAt = performance.now()
  const id = window.setTimeout(() => trace.mark('event-loop.lag', { eventLoopLagMs: Math.max(0, performance.now() - startedAt - delayMs) }), delayMs)
  return () => window.clearTimeout(id)
}
