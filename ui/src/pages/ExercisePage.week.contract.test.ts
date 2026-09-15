import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const page = readFileSync(fileURLToPath(new URL('./ExercisePage.tsx', import.meta.url)), 'utf8')
const history = readFileSync(fileURLToPath(new URL('../components/Exercise/ExerciseHistory.tsx', import.meta.url)), 'utf8')
assert(page.includes('weekOfYear(date)'), 'header must calculate the selected Beijing date week')
assert(history.includes('weekOfYear(x.date)') && !history.includes('x.week_num'), 'history must calculate each row week instead of rendering the legacy field')
assert(history.includes('readablePlan') && history.includes('未记录训练安排'), 'history must not expose internal exercise schedule keys')
assert(history.includes('训练安排') && history.includes('完成率'), 'history columns must explain each historical value')
console.log('exercise week display contract passed')
