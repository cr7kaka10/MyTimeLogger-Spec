import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const taskSection = readFileSync(fileURLToPath(new URL('./TaskSection.tsx', import.meta.url)), 'utf8')
const page = readFileSync(fileURLToPath(new URL('./index.tsx', import.meta.url)), 'utf8')

if (!taskSection.includes("mode === 'incomplete' ? incompleteTasks : completedTasks")) {
  throw new Error('selected-date task region must render only incomplete tasks')
}
if (!taskSection.includes("mode === 'completed' && completedTasks.length === 0")) {
  throw new Error('completed task region must hide only when the selected date has no completed task')
}
if ((page.match(/<TaskSection/g) ?? []).length !== 2) {
  throw new Error('page must render separate incomplete and completed task regions')
}
const completedTask = page.indexOf('mode="completed"')
const completedHabit = page.indexOf('<HabitSection', completedTask)
if (completedTask < 0 || completedHabit < 0 || completedTask > completedHabit) {
  throw new Error('selected-date completed tasks must appear before completed habits')
}

console.log('selected-date completed task visibility contracts passed')
