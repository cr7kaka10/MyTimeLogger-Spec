import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const page = readFileSync(fileURLToPath(new URL('./ExercisePage.tsx', import.meta.url)), 'utf8')
const hook = readFileSync(fileURLToPath(new URL('../hooks/useExercise.ts', import.meta.url)), 'utf8')
const panel = readFileSync(fileURLToPath(new URL('../components/Exercise/ExercisePanel.tsx', import.meta.url)), 'utf8')
const schedule = readFileSync(fileURLToPath(new URL('../components/Exercise/SchedulePanel.tsx', import.meta.url)), 'utf8')
const item = readFileSync(fileURLToPath(new URL('../components/Exercise/ExerciseItem.tsx', import.meta.url)), 'utf8')

assert(page.includes('const canEditWeight = isBeijingToday && !x.locked'), 'today weight input must remain editable after 09:00')
assert(page.includes('inputMode="decimal"'), 'Android weight input must request a decimal keypad')
assert((page.match(/onPointerDown=\{event => requestCapacitorInputFocus\(event\.currentTarget\)\}/g) || []).length === 2, 'both body-metric inputs must explicitly request Android IME focus')
assert(page.includes('numericWeight < 30 || numericWeight > 200'), 'weight range validation must remain active')
assert(page.includes('numericBodyFat < 3 || numericBodyFat > 75'), 'body fat range validation must remain active')
assert(page.includes('className="body-metrics"') && page.includes('className="body-metric"'), 'body metrics must be rendered as aligned columns')
assert(page.includes("x.deadlineFacts.find((fact: any) => fact.fact_type === 'body_metrics')"), 'body deadline state must come from the server-owned V4 fact rather than a removed schedule row')
assert(page.includes('可补录体重和体脂率；-50 金币处罚不变。'), 'late entry must clearly preserve the server penalty')
assert(!page.includes('&& !isBodyMetricLocked'), 'body metric lock must not disable raw data inputs')
assert(page.includes('isBodyMetricLocked || log?.weight == null'), 'locked dates must retain the backfill explanation after values are saved')
assert(!page.includes('体重只能在北京时间每天 06:00-09:00 之间录入'), 'time window must not block data entry')
assert(hook.includes('setDeadlineFacts(db.getExerciseDeadlineFacts(date,version))') && hook.includes("syncNow({reason:'exercise-body-metrics'})"), 'body saves must sync before reading the server-owned deadline and score facts')
assert(panel.includes('authoritative = Boolean(state?.score_rule_version)') && schedule.includes('locked ? Boolean(st?.score_rule_version)'), 'locked dates must keep any saved score fact instead of applying the current preview rule')
assert(!schedule.includes('本项') && !item.includes('本项'), 'exercise metadata must not use 本项 label')
assert(schedule.includes('ex-score-meta') && item.includes('ex-score-meta'), 'schedule and exercise items must share aligned score metadata row')
assert((page.match(/className="body-metric-meta"/g) || []).length === 2, 'weight and body fat must each show the shared score metadata')

console.log('exercise weight input contract passed')
