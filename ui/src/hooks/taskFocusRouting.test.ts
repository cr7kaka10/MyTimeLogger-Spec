import { decideTaskFocus, formatTaskFocusBlockedMessage } from './taskFocusRouting'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
assert(decideTaskFocus('stopped', null, '', 1).status === 'started', 'stopped should start')
assert(decideTaskFocus('stopped', null, '', null).status === 'unavailable', 'missing category is unavailable')
assert(decideTaskFocus('long_break_finished', 1, '输入', 2).status === 'started', 'finished should start')
assert(decideTaskFocus('studying', 1, '输入', 1).status === 'retargeted', 'same input should retarget')
const inputBlocked = decideTaskFocus('studying', 1, '输入', 2)
const outputBlocked = decideTaskFocus('studying', 2, '输出', 1)
assert(inputBlocked.status === 'blocked', 'input cross-category should block')
assert(outputBlocked.status === 'blocked', 'output cross-category should block')
assert(decideTaskFocus('countup_studying', 8, '娱乐', 9).status === 'switched', 'normal category should switch')
assert(formatTaskFocusBlockedMessage('输入') === '当前处于输入计时状态中，不能切换，按 Alt+C 或提前结束专注才行', 'input message must be exact')
assert(formatTaskFocusBlockedMessage('输出') === '当前处于输出计时状态中，不能切换，按 Alt+C 或提前结束专注才行', 'output message must be exact')
console.log('taskFocusRouting tests passed')
