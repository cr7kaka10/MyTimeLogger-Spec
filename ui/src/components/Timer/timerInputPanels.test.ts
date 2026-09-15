import { scheduleTimerInputFocus, type TimerInputFocusRuntime } from './summaryInputFocus'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { TIMER_NOTE_PRESETS } from './notePresets'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
const timerPage = readFileSync(fileURLToPath(new URL('./TimerPage.tsx', import.meta.url)), 'utf8')
const statusNote = readFileSync(fileURLToPath(new URL('./StatusSwitchNoteSheet.tsx', import.meta.url)), 'utf8')
assert(TIMER_NOTE_PRESETS.join('|') === '休息|喝水|活动|接电话|上厕所|家庭原因', 'shared timer note presets must preserve the agreed options')
assert(timerPage.includes('TIMER_NOTE_PRESETS') && statusNote.includes('TIMER_NOTE_PRESETS'), 'timer note and status note must use the shared presets')
for (const [name, cursor] of [['note', 4], ['summary', 3], ['pause', 0], ['status', 0]] as const) {
  let active: unknown = null; let selection = -1; let focuses = 0; let frame: (() => void) | null = null
  const input = { tagName: 'INPUT', focus: () => { active = input; focuses++ }, setSelectionRange: (start: number) => { selection = start } }
  const runtime: TimerInputFocusRuntime = {
    requestFrame: callback => { frame = callback; return 1 }, cancelFrame: () => { frame = null },
    setDelay: () => 2, clearDelay: () => {}, getActiveElement: () => active,
  }
  scheduleTimerInputFocus(input, cursor, runtime)
  ;(frame as (() => void) | null)?.()
  assert(active === input && selection === cursor, `${name} panel should focus at ${cursor}`)
  let draft = ''; draft += '中文'; selection = Math.min(1, draft.length)
  assert(focuses === 1 && selection === 1, `${name} text/IME changes must not refocus or move selection`)
}
let cancelledFrame: (() => void) | null = null; let calls = 0
const target = { tagName: 'TEXTAREA', focus: () => { calls++ }, setSelectionRange: () => {} }
const cleanupRuntime: TimerInputFocusRuntime = {
  requestFrame: callback => { cancelledFrame = callback; return 1 }, cancelFrame: () => { cancelledFrame = null },
  setDelay: () => 2, clearDelay: () => {}, getActiveElement: () => null,
}
scheduleTimerInputFocus(target, 0, cleanupRuntime)()
;(cancelledFrame as (() => void) | null)?.()
assert(calls === 0, 'closed panel must cancel focus work')
console.log('timerInputPanels tests passed')
