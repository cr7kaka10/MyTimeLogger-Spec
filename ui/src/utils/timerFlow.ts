import { getElectronApi } from '../platform/electron'

export type TimerFlowResult = 'started' | 'completed' | 'failed' | 'ignored' | 'deduped' | 'gated' | string

export interface TimerFlowEvent extends Record<string, any> {
  beijingTime: string
  traceId: string
  step: number
  layer: string
  event: string
  result?: TimerFlowResult
  durationMs?: number
}

const traceState = new Map<string, { step: number, startedAt: number, terminal: boolean }>()
const blockedKey = /(note|summary|task|token|password|api.?key|authorization|cookie|headers?|secret|currentfocustask|error)$/i

const beijingTimestamp = (): string => {
  const text = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date()).replace(' ', 'T')
  return `${text}+08:00`
}

export const sanitizeTimerFlowDetails = (value: Record<string, any>): Record<string, any> => {
  const safe: Record<string, any> = {}
  for (const [key, raw] of Object.entries(value || {})) {
    if (blockedKey.test(key) && !/^(has|.*Length$|errorCode$)/i.test(key)) continue
    if (raw === undefined) continue
    if (raw === null || ['string', 'number', 'boolean'].includes(typeof raw)) safe[key] = raw
    else if (Array.isArray(raw)) safe[key] = raw.slice(0, 20).map(item => (
      item && typeof item === 'object' ? sanitizeTimerFlowDetails(item) : item
    ))
    else if (typeof raw === 'object') safe[key] = sanitizeTimerFlowDetails(raw)
  }
  return safe
}

export const emitTimerFlow = (
  layer: string,
  event: string,
  details: Record<string, any> = {},
): TimerFlowEvent => {
  const traceId = String(details.traceId || `timer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`)
  const current = traceState.get(traceId) || { step: Number(details.traceStep || 0), startedAt: Date.now(), terminal: false }
  const terminal = event === 'flow.completed' || event === 'flow.failed'
  const payload: TimerFlowEvent = {
    beijingTime: beijingTimestamp(),
    traceId,
    step: current.step + 1,
    layer,
    event,
    durationMs: Date.now() - current.startedAt,
    ...sanitizeTimerFlowDetails(details),
  }
  current.step = payload.step
  current.terminal = current.terminal || terminal
  traceState.set(traceId, current)
  const method = event === 'flow.failed' || payload.result === 'failed' ? 'error' : payload.result === 'gated' ? 'warn' : 'info'
  console[method]('[timer-flow]', payload)
  try { getElectronApi()?.writeTimerFlow?.(payload) } catch {}
  if (terminal) traceState.delete(traceId)
  return payload
}

export interface TimerAudioFlowDetails {
  cue: string
  source: 'refresh' | 'command' | 'engine'
  operation?: string
  revision?: number
  hasIntent?: boolean
  intentLength?: number
  result: string
}

export const emitTimerAudioFlow = (
  event: 'dispatched' | 'deduplicated',
  details: TimerAudioFlowDetails,
): TimerFlowEvent => emitTimerFlow('useTimer', `audio-cue.${event}`, {
  cue: details.cue,
  source: details.source,
  operation: details.operation,
  revision: details.revision,
  hasIntent: Boolean(details.hasIntent),
  intentLength: Math.max(0, Number(details.intentLength || 0)),
  result: details.result,
})

export const __resetTimerFlowForTests = (): void => traceState.clear()
