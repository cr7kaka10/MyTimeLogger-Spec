import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8')
const hook = read('./useChecklist.ts')
const legacyPage = read('../components/Checklist/ChecklistPage.tsx')
const unifiedSection = read('../pages/UnifiedChecklistPage/TaskSection.tsx')

assert(hook.includes('completeTask: (task: TaskItem) => Promise<void>'), 'completion entry must receive the task state')
assert(hook.includes('if (task.status === 2)') && hook.includes('db.updateTaskStatus(taskId, 0)'), 'completed tasks must be restored locally instead of completing again')
assert(hook.includes("reason: 'checklist-task-uncomplete'"), 'restoring an uncompleted task must trigger the existing sync path')
assert(hook.includes('db.completeTask(taskId, task.title, coins)'), 'active tasks must retain the existing completion path')
assert(legacyPage.includes('await completeTask(task)'), 'legacy checklist must pass the full task to the shared toggle')
assert(unifiedSection.includes('await onComplete(task)'), 'unified checklist must pass the full task to the shared toggle')

console.log('checklist completion toggle contracts passed')
