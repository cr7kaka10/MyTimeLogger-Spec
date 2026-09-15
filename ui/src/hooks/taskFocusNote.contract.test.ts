import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const timer = readFileSync(new URL('./useTimer.ts', import.meta.url), 'utf8')
const learning = readFileSync(new URL('../components/Learning/LearningPage.tsx', import.meta.url), 'utf8')
const checklist = readFileSync(new URL('../pages/UnifiedChecklistPage/TaskSection.tsx', import.meta.url), 'utf8')

assert(learning.includes('onStartFocus(taskInfo.categoryId, taskInfo.title)'), 'learning focus must pass the task title')
assert(checklist.includes('timer.requestTaskFocus(category.id, task.title)'), 'checklist focus must pass the task title')
assert(timer.includes('currentNote: title, timerMode'), 'task start and switch must write the authoritative note')
assert(timer.includes("commandCurrentTimer('note', { currentNote: title })"), 'same-category retarget must update the authoritative note')
assert(timer.includes("authoritative.current_note || ''"), 'refresh must import the authoritative note')
assert(!timer.includes("setCurrentNoteState('')\n            setState"), 'current-state import must not clear a live task note')

console.log('task focus note contract passed')
