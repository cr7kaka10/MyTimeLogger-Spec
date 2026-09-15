import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const page = readFileSync(fileURLToPath(new URL('./ExercisePage.tsx', import.meta.url)), 'utf8')
const hook = readFileSync(fileURLToPath(new URL('../hooks/useExercise.ts', import.meta.url)), 'utf8')
const database = readFileSync(fileURLToPath(new URL('../../../core/models/Database.ts', import.meta.url)), 'utf8')

assert(hook.includes("exercise_plan_version_incomplete") && hook.includes('`${version} 计划数据同步中，计划内容尚未完整。`'), 'incomplete versions must name the target version in the synchronization message')
assert(hook.includes('return false') && hook.includes('await load();return true'), 'version selection must report failure without reloading a fallback version')
assert(page.includes('x.planVersions.map'), 'version menu must render every enabled plan version, including V2')
assert(page.includes('if (await x.setActivePlanVersion(version.version)) setShowVersions(false)'), 'version menu must close only after a successful switch')
assert(page.includes('x.versionError'), 'version menu must render a failed-switch message')
assert(hook.includes('db.getActiveExercisePlanVersion()'), 'exercise must select its active version from exercise plan storage')
assert(hook.includes('db.getExercisePlanDefinition(version)') && hook.includes('db.getExerciseCheckins(date,version)'), 'exercise items and scores must come only from versioned exercise tables')
assert(hook.includes('getExerciseDailyLog(date,version)') && hook.includes('getExerciseDietCheckins(date,version)') && hook.includes('getExerciseDeadlineFacts(date,version)'), 'body, diet, deadline and daily states must use the selected plan version')
assert(!database.includes('SELECT weight FROM exercise_daily_logs WHERE date = ? AND weight IS NOT NULL'), 'daily log reads must not pull weight across plan versions')
assert(!hook.includes('getHabits(') && !hook.includes('habit_checkins'), 'daily habits must never change exercise plan items or scoring')

console.log('exercise plan version and habit isolation contract passed')
