import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), 'utf8')
const page = read('./ExercisePage.tsx')
const hook = read('../hooks/useExercise.ts')
const panel = read('../components/Exercise/ExercisePanel.tsx')
const rail = read('../components/TimeBook/TimeBookScheduleRail.tsx')
const css = read('./ExercisePage.css')

assert(page.includes("x.planVersion === 'v4' ? undefined : score"), 'V4 body save must not upload a client-computed score')
assert(page.includes('projectV4Score(authoritativeV4Score)'), 'V4 score card must reject local or legacy snapshots in favor of its authoritative projection')
assert(page.includes("x.itemScores['body:weight']") && page.includes("x.itemScores['body:body_fat_rate']"), 'body metrics must read server-owned item scores')
assert(page.includes('已补录，截止后不得分'), 'late body values must remain visible without implying a late score')
assert(hook.includes('setItemScores(scores)') && hook.includes('itemScores'), 'hook must expose V4 item scores to the body metric feedback')
assert(hook.includes('getExerciseDietCheckins') && hook.includes("syncNow({reason:'exercise-diet-checkin'})"), 'diet facts must use the shared outbox sync path')
assert(panel.includes('饮食约束 · 15分') && panel.includes('当天24:00前必打卡') && panel.includes('扣20金币'), 'diet card must show all score and deadline consequences')
assert(panel.includes('运动计划 · 75分') && panel.includes('频率与渐进'), 'V4 must expose the 75-point training plan and frequency guide')
assert(panel.includes('className={`ex-box') && !panel.includes(": '○'"), 'diet check-ins must use the single-layer exercise control without a nested circle glyph')
assert(!page.includes('inner-tabs') && !panel.includes('运动指标全完成奖励'), 'the redundant tab strip and completion summary card must not render')
assert(!css.includes('.inner-tabs') && !css.includes('.diet-check-row>span'), 'removed tab and nested-circle styles must not remain')
assert(css.includes('grid-template-columns:4em minmax(0,1fr) max-content') && css.includes('white-space:nowrap'), 'V4 score labels must keep four Chinese characters on one line while the progress column flexes')
assert(rail.includes("definition.version === 'v4'") && rail.includes("!/体重|体脂/.test(row.item)"), 'TimeBook must hide legacy V4 body rows')
assert(!rail.includes('earned_points') && !rail.includes('max_points'), 'TimeBook schedule check-ins must not display score values')

console.log('exercise V4 UI and TimeBook decoupling contracts passed')
