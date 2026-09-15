import { isDirectTimerCategoryActionBlocked, isStructuredFocusLocked, isTimerCategoryGridBlocked, shouldBlockTimerCategoryAction } from './timerFocusGuard'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }

assert(isStructuredFocusLocked('输入', 'studying'), 'input studying should lock')
assert(isStructuredFocusLocked('输出', 'short_breaking'), 'output short break should stay locked')
assert(isDirectTimerCategoryActionBlocked('输入', 'studying'), 'direct start/switch should be blocked while input is active')
assert(!isStructuredFocusLocked('输入', 'stopped'), 'stopped input should unlock')
assert(!isStructuredFocusLocked('输出', 'long_break_finished'), 'finished output should unlock')
assert(!isStructuredFocusLocked('娱乐', 'countup_studying'), 'normal category should not lock')
assert(!isTimerCategoryGridBlocked(2, 2, '输入', 'studying'), 'current input card should remain visually enabled')
assert(isTimerCategoryGridBlocked(2, 8, '输入', 'studying'), 'other card should be blocked during input')
assert(isTimerCategoryGridBlocked(1, 2, '输出', 'studying'), 'other card should be blocked during output')
assert(shouldBlockTimerCategoryAction('start', '输入', 'studying'), 'direct start should be guarded')
assert(shouldBlockTimerCategoryAction('switchCategory', '输出', 'studying'), 'direct switch should be guarded')
assert(!shouldBlockTimerCategoryAction('requestStatusSwitch', '输入', 'studying'), 'Alt+C path should remain allowed')
assert(!shouldBlockTimerCategoryAction('endSession', '输出', 'studying'), 'red end action should remain allowed')
assert(!shouldBlockTimerCategoryAction('start', '娱乐', 'countup_studying'), 'normal category start should remain allowed')

let sideEffects = 0
const simulate = (action: 'start' | 'switchCategory' | 'requestStatusSwitch' | 'endSession', source: string, state: any) => {
  if (!shouldBlockTimerCategoryAction(action, source, state)) sideEffects++
}
simulate('start', '输入', 'studying')
simulate('switchCategory', '输出', 'studying')
assert(sideEffects === 0, 'locked direct actions should have zero side effects')
simulate('requestStatusSwitch', '输入', 'studying')
simulate('endSession', '输出', 'studying')
simulate('switchCategory', '娱乐', 'countup_studying')
assert(sideEffects === 3, 'Alt+C, red end, and normal switching should remain allowed')

console.log('timerFocusGuard tests passed')
