import { isTaskFocusActive } from './taskFocusState'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
const active = (id: string | null, taskId = 'a', category = 1, taskCategory = 1, note = '任务', title = '任务') => (
  isTaskFocusActive(id, taskId, 'studying', category, taskCategory, note, title)
)
assert(active('a'), 'matching identity/category/note should restore focus')
assert(!active('old'), 'stale id must not restore focus')
assert(!active('a', 'b'), 'duplicate title with another id must not restore focus')
assert(!active('a', 'a', 2, 1), 'category mismatch must clear focus')
assert(!active('a', 'a', 1, 1, '其他任务'), 'note mismatch must clear focus')
assert(!isTaskFocusActive('a', 'a', 'stopped', 1, 1, '任务', '任务'), 'stopped timer must clear focus')
console.log('taskFocusState tests passed')
