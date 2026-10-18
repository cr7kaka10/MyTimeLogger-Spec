import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { projectAuthoritativeScore } from '../utils/exerciseAuthoritativeScore'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), 'utf8')
const page = read('./ExercisePage.tsx')
const panel = read('../components/Exercise/ExercisePanel.tsx')
const hook = read('../hooks/useExercise.ts')
const authority = read('../utils/exerciseAuthoritativeScore.ts')
const reference = read('../components/Exercise/ExerciseReferencePanels.tsx')
const data = JSON.parse(read('../../../server/domain/exercise_plan_sample_data.json')).v5

assert(authority.includes("version === 'v4' || version === 'v5'"), 'V5 must use the server-authoritative score capability')
assert(page.includes('projectAuthoritativeScore(authoritativeScore'), 'V5 must render the server score projection')
assert(hook.includes('projectDietSettlement(current,date,previous,status,planVersion)'), 'V5 diet clicks must optimistically project their own version')
assert(panel.includes("'今日休息 · 不计训练分'") && panel.includes('const sections: string[]'), 'Monday rest and V5 dynamic sections must render')
assert(panel.includes('本项不得分（不扣金币）') && panel.includes("planVersion === 'v4' ? '已过24:00，扣20金币'"), 'V4 and V5 diet consequences must stay distinct')
assert(reference.includes('planDefinition.progress.map'), 'progress and five eating-out templates must render in the reference panel')
assert(data.exercisePlan['周一'].gym.length === 0, 'Monday must be a no-training travel rest day')
assert(['周二','周三','周四','周五','六','日'].every(day => data.exercisePlan[day].gym.reduce((sum: number, item: any) => sum + item.durationMinutes, 0) === 90), 'six training days must each total 90 minutes')
assert(data.progress.filter((item: any) => item.when.includes('外食')).length === 5, 'five common eating-out templates must ship')
const monday = projectAuthoritativeScore({ total: 25, plan_version: 'v5', cats: { 运动训练: { s: 0, m: 0 }, 饮食约束: { s: 15, m: 15 }, 身体记录: { s: 10, m: 10 } } }, 'v5')
assert(monday.total === 25 && monday.cats['运动训练'].m === 0, 'Monday rest must preserve a zero training maximum')

console.log('exercise V5 UI contracts passed')
