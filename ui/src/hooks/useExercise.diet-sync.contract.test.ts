import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const hook = readFileSync(fileURLToPath(new URL('./useExercise.ts', import.meta.url)), 'utf8')
const panel = readFileSync(fileURLToPath(new URL('../components/Exercise/ExercisePanel.tsx', import.meta.url)), 'utf8')
const start = hook.indexOf('const setDietState=')
const end = hook.indexOf('const setVariant=', start)
const diet = hook.slice(start, end)

assert(start >= 0 && end > start, 'diet check-in handler must exist as an isolated hook branch')
assert(diet.indexOf('setSyncError(null)') < diet.indexOf('setDietCheckins('), 'diet check-in must clear an old sync error before its optimistic update')
assert(diet.includes('dietProjectionRef.current[projectionKey]=fact') && diet.includes('setDietCheckins(p=>({...p,[ruleKey]:{...p[ruleKey],...fact}}))'), 'diet click must project the exact local fact before core sync')
assert(diet.indexOf('setDietCheckins(') < diet.indexOf('getDatabase()'), 'diet click must render its optimistic state before waiting for the database')
assert(diet.indexOf('setDietCheckins(') < diet.indexOf('toggleExerciseDietCheckin('), 'diet click must render before its SQLite write')
assert(hook.includes("const projectionPrefix=`${date}:${version}:`") && hook.includes('String(incoming.updated_at||\'\')<String(fact.updated_at||\'\')'), 'older same-version pull data must not overwrite an optimistic diet fact')
assert(diet.indexOf("if (!result.ok) {setSyncError(result.error||'exercise_diet_sync_failed');return}") < diet.indexOf('delete dietProjectionRef.current[projectionKey];await load()'), 'failed diet sync must retain the local projection, while successful sync may refresh the authoritative projection')
assert(diet.includes("catch (error) {setSyncError(error instanceof Error ? error.message : 'exercise_diet_sync_failed')}"), 'diet check-in must preserve optimistic state when sync throws')
assert(diet.includes("!planDefinition?.dietRulesValid||!ruleKey.trim()"), 'diet handler must reject invalid plan keys before writing a shared fact')
assert(hook.includes("type DietStatus='pending'|'completed'|'failed'") && diet.includes("failure_reason:status==='failed'?'user_marked_failed':null"), 'diet facts must model a user-controlled failed state separately from deadline failure')
assert(diet.includes('setSettlement(current=>projectDietSettlement(current,date,previous,status))'), 'diet click must project the authoritative V4 score card before core sync returns')
assert(diet.includes("db.toggleExerciseDietCheckin(date,ruleKey,status,planVersion)"), 'three-state diet fact must be persisted to the local outbox')
assert(panel.includes("const key = rule.ruleKey?.trim() || '', invalid = !planDefinition.dietRulesValid || !key"), 'diet rows must treat missing or duplicate rule keys as invalid configuration')
assert(panel.includes("completed||failed?'pending':'completed'") && panel.includes("onContextMenu={event =>"), 'left click must cancel either terminal state and right click must select failed')
assert(panel.includes("event.preventDefault();void setDietState(key,'failed')"), 'diet right click must suppress the browser context menu and immediately project failure')
assert(panel.includes("<strong className={completed ? 'struck' : ''}>{rule.content}</strong>"), 'completed diet text must reuse the exercise-item strike-through effect')

console.log('exercise diet sync feedback contract passed')
