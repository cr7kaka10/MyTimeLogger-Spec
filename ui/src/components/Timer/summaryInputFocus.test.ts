import { scheduleTimerInputFocus, type TimerInputFocusRuntime } from './summaryInputFocus'
const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }

const harness = (failedFocusCalls = 0) => {
  let active: unknown = null
  let focusCalls = 0
  let selection = -1
  const frames = new Map<number, () => void>()
  const delays = new Map<number, () => void>()
  let nextDelayId = 2
  const textarea = {
    tagName: 'TEXTAREA',
    focus: () => { focusCalls++; if (focusCalls > failedFocusCalls) active = textarea },
    setSelectionRange: (start: number) => { selection = start },
  }
  const runtime: TimerInputFocusRuntime = {
    requestFrame: callback => { frames.set(1, callback); return 1 },
    cancelFrame: id => { frames.delete(id) },
    setDelay: callback => { const id = nextDelayId++; delays.set(id, callback); return id },
    clearDelay: id => { delays.delete(id) },
    getActiveElement: () => active,
  }
  return {
    textarea, runtime,
    setActive: (element: unknown) => { active = element },
    runFrame: () => { const callback = frames.get(1); frames.delete(1); callback?.() },
    runRetry: () => { const id = [...delays.keys()][0]; const callback = delays.get(id); delays.delete(id); callback?.() },
    state: () => ({ active, focusCalls, selection, delays: delays.size }),
  }
}

const success = harness()
scheduleTimerInputFocus(success.textarea, 3, success.runtime)
success.runFrame()
assert(success.state().active === success.textarea && success.state().selection === 3 && success.state().delays === 0, 'first focus should succeed without retry')

const retry = harness(1)
const retryEvents: string[] = []
scheduleTimerInputFocus(retry.textarea, 3, retry.runtime, { report: event => retryEvents.push(event) })
retry.runFrame(); retry.runRetry()
assert(retry.state().active === retry.textarea && retry.state().focusCalls === 2, 'one retry should recover focus')
assert(retryEvents.join(',') === 'focus.attempted,focus.retry,focus.attempted,focus.verified', 'focus lifecycle must be observable')

const limited = harness(2)
scheduleTimerInputFocus(limited.textarea, 3, limited.runtime)
limited.runFrame(); limited.runRetry(); limited.runRetry()
assert(limited.state().focusCalls === 2 && limited.state().delays === 0, 'focus retries must stop after one retry')

const cleaned = harness()
const cleanup = scheduleTimerInputFocus(cleaned.textarea, 3, cleaned.runtime)
cleanup(); cleaned.runFrame(); cleaned.runRetry()
assert(cleaned.state().focusCalls === 0, 'cleanup should cancel pending focus work')

const lifecycle = harness()
const unmount = scheduleTimerInputFocus(lifecycle.textarea, 3, lifecycle.runtime)
lifecycle.runFrame()
let text = '1. '; text += '中文输入'
assert(text.length > 3 && lifecycle.state().focusCalls === 1, 'text changes must not reschedule focus')
unmount()
const reopened = harness()
scheduleTimerInputFocus(reopened.textarea, 3, reopened.runtime); reopened.runFrame()
assert(reopened.state().focusCalls === 1, 'a reopened sheet should own a fresh focus lifecycle')

const protectedInput = harness(1)
const protectedEvents: string[] = []
scheduleTimerInputFocus(protectedInput.textarea, 3, protectedInput.runtime, { report: event => protectedEvents.push(event) })
protectedInput.runFrame(); protectedInput.setActive({ tagName: 'INPUT' }); protectedInput.runRetry(); protectedInput.runRetry()
assert(protectedInput.state().focusCalls === 1, 'retry must not steal focus from another editable control')
assert(!protectedEvents.includes('focus.verified'), 'focus must not be falsely verified when another input owns it')
assert(protectedEvents.includes('focus.lost'), 'focus transfer must be observable without stealing focus')

const lost = harness(2); const lostEvents: string[] = []
scheduleTimerInputFocus(lost.textarea, 3, lost.runtime, { now: () => 0, timeoutMs: 500, report: event => lostEvents.push(event) })
lost.runFrame(); lost.runRetry(); lost.runRetry()
assert(lostEvents.includes('focus.lost'), 'failed focus must report a bounded timeout')

console.log('summaryInputFocus tests passed')
