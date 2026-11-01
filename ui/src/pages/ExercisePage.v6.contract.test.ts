import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const read = (relative: string) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const page = read('./ExercisePage.tsx')
const hook = read('../hooks/useExercise.ts')
const panel = read('../components/Exercise/ExercisePanel.tsx')
const history = read('../components/Exercise/ExerciseHistory.tsx')

assert(page.includes("第六版 · 纯运动评分") && page.includes("'休息'") && page.includes("'不计分'"), 'V6 score ring must name pure exercise and Monday rest')
assert(page.includes("x.planVersion !== 'v6' && <div id=\"exercise-body-metrics\""), 'V6 must hide body metric card')
assert(page.includes("if (x.planVersion !== 'v5') { setDietMigrated(false); return }"), 'V6 must skip habit-state read')
assert(page.includes("exerciseOnly={x.planVersion === 'v6'}") && history.includes("exerciseOnly ? '训练项' : '身体指标'"), 'V6 history must show training instead of body metrics')
assert(history.includes('settlement_completed_items') && history.includes('settlement_total_items'), 'V6 history must use authoritative completed item counts')
assert(panel.includes("planVersion !== 'v6' && !isRestDay") && panel.includes("planVersion === 'v6' ? 100"), 'V6 panel must omit diet and show 100 training points')
assert(hook.includes("date>=cutoff?'v6':'v5'") && hook.includes('version!==authoritativeVersion'), 'client must select authority by date and lock old-version preview')
assert(page.includes('historicalV5Score') && page.includes('projectV5ScoreView'), 'V5 historical score must retain its original projection')

console.log('exercise V6 shared PC and Android page contract passed')
