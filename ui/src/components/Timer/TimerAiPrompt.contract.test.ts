import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8')
const page = read('./TimerPage.tsx')
const prompt = read('./TimerAiPrompt.tsx')
const sheet = read('../ManagementPlan/ManagementPlanSheet.tsx')
const app = read('../../App.tsx')

assert(!page.includes('justify-center'), 'timer content must remain top-aligned')
assert(page.indexOf('<CategoryGrid') < page.indexOf('<TimerAiPrompt'), 'AI prompt must follow category grid')
assert(page.includes('sticky bottom-[calc(5rem+env(safe-area-inset-bottom,0px))]'), 'AI prompt must stay above the bottom tab bar')
assert(page.includes('mt-auto pt-3'), 'AI prompt must use remaining vertical space before the tab bar')
assert(prompt.includes('value.trim()'), 'blank requests must be rejected')
assert(prompt.includes('event.shiftKey'), 'Shift+Enter must preserve newline behavior')
assert(prompt.includes('disabled={!canSubmit}'), 'submit must be disabled while unavailable or busy')
assert(prompt.includes('onFocusHandled?.()') && app.includes('handleTimerAiFocusHandled') && app.includes('onFocusAiHandled={handleTimerAiFocusHandled}'), 'an explicit focus request must be consumed so returning to timer cannot reopen the keyboard')
assert(prompt.includes('role="alert"'), 'generation errors must be announced')
assert(prompt.includes('rows={1}'), 'prompt should default to a compact single-line layout')
assert(prompt.includes('max-w-2xl'), 'prompt should stay visually compact on wide screens')
assert(prompt.includes('rounded-full'), 'submit action should use a compact circular button')
assert(app.includes('initialRequest={managementPlanRequest}'), 'timer requests must enter the shared plan sheet')
assert(sheet.includes('plan.generate(request)'), 'initial timer request must generate a draft')
assert(sheet.includes('if (!open) return null'), 'closing the sheet must preserve its hook state')
assert(!prompt.includes('plan.apply'), 'prompt must never apply a plan implicitly')
console.log('timer AI prompt contract passed')
