import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = relative => readFileSync(new URL(relative, import.meta.url), 'utf8')
const editor = source('../src/components/Goals/GoalEditSheet.tsx')
const goalsPage = source('../src/components/Goals/GoalsPage.tsx')
const database = source('../../core/models/Database.ts')
const assertIncludes = (value, expected, message) => {
  if (!value.includes(expected)) throw new Error(message)
}

assertIncludes(editor, 'value="custom_weekdays"', 'custom weekday period option is missing')
assertIncludes(editor, 'period === \'custom_weekdays\' && weekdays.length === 0', 'empty weekday selection is not rejected')
assertIncludes(editor, 'period, weekdays, operator', 'selected weekdays are not included in saved goal data')
assertIncludes(goalsPage, '自定义星期：', 'custom weekdays are not shown on goal cards')
assertIncludes(goalsPage, 'progress.isRestDay', 'goal card does not consume the rest-day progress state')
assertIncludes(database, 'period === \'custom_weekdays\' && !(goal.weekdays ?? []).includes(weekday)', 'local progress does not identify unselected weekdays')
console.log('custom weekday goal UI contract checks passed')
