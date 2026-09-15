export interface TimerInputFocusRuntime {
  requestFrame: (callback: () => void) => number; cancelFrame: (id: number) => void
  setDelay: (callback: () => void, ms: number) => number; clearDelay: (id: number) => void
  getActiveElement: () => unknown
}
export interface TimerInputFocusObserver { now?: () => number; report: (event: 'focus.attempted' | 'focus.verified' | 'focus.retry' | 'focus.lost', details?: Record<string, unknown>) => void; timeoutMs?: number }
type FocusTarget = { tagName?: string; isContentEditable?: boolean; focus: (options?: FocusOptions) => void; setSelectionRange: (start: number, end: number) => void }
const isEditable = (element: any): boolean => Boolean(element?.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(element?.tagName))
export const scheduleTimerInputFocus = (
  target: FocusTarget,
  cursor: number,
  provided?: TimerInputFocusRuntime,
  observer?: TimerInputFocusObserver,
): (() => void) => {
  const runtime = provided ?? {
    requestFrame: (callback: () => void) => window.requestAnimationFrame(callback),
    cancelFrame: (id: number) => window.cancelAnimationFrame(id),
    setDelay: (callback: () => void, ms: number) => window.setTimeout(callback, ms),
    clearDelay: (id: number) => window.clearTimeout(id),
    getActiveElement: () => document.activeElement,
  }
  let cancelled = false
  let retryId: number | null = null
  let timeoutId: number | null = null
  const now = observer?.now || (() => performance.now())
  const startedAt = now()
  const tag = () => String((runtime.getActiveElement() as any)?.tagName || 'NONE')
  const focus = () => {
    if (cancelled) return
    observer?.report('focus.attempted', { activeElementTag: tag() })
    target.focus({ preventScroll: true })
    target.setSelectionRange(cursor, cursor)
    if (runtime.getActiveElement() === target) observer?.report('focus.verified', { activeElementTag: tag() })
  }
  const retry = () => {
    if (runtime.getActiveElement() !== target && !isEditable(runtime.getActiveElement())) {
      observer?.report('focus.retry', { activeElementTag: tag() }); focus()
    }
    if (runtime.getActiveElement() !== target) timeoutId = runtime.setDelay(() => {
      if (!cancelled && runtime.getActiveElement() !== target) observer?.report('focus.lost', { activeElementTag: tag(), reason: isEditable(runtime.getActiveElement()) ? 'other-editable' : 'timeout' })
    }, Math.max(0, (observer?.timeoutMs ?? 500) - (now() - startedAt)))
  }
  const frameId = runtime.requestFrame(() => {
    focus()
    const active = runtime.getActiveElement()
    if (active !== target && !isEditable(active)) retryId = runtime.setDelay(retry, 50)
    else if (active !== target) observer?.report('focus.lost', { activeElementTag: tag(), reason: 'other-editable' })
  })
  return () => {
    cancelled = true
    runtime.cancelFrame(frameId)
    if (retryId !== null) runtime.clearDelay(retryId)
    if (timeoutId !== null) runtime.clearDelay(timeoutId)
  }
}

export type SummaryFocusRuntime = TimerInputFocusRuntime
export const scheduleSummaryInputFocus = scheduleTimerInputFocus
