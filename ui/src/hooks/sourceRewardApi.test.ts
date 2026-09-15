import { createLatestRequestGate, SOURCE_COIN_TYPE } from './sourceRewardApi'
import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
assert(SOURCE_COIN_TYPE.checklist_task === 'task' && SOURCE_COIN_TYPE.habit === 'habit' && SOURCE_COIN_TYPE.learning_task === 'learning', 'source mappings stay isolated')
const gate = createLatestRequestGate(); const old = gate.next(); const current = gate.next()
assert(!gate.isCurrent(old) && gate.isCurrent(current), 'late responses cannot replace the current source')
const hook = readFileSync(new URL('./useSourceRewards.ts', import.meta.url), 'utf8')
const api = readFileSync(new URL('./sourceRewardApi.ts', import.meta.url), 'utf8')
assert(hook.includes('await saveSourceCoins(summary, coins)') && hook.includes('return refresh()'), 'successful coin saves always read back the server summary')
assert(!/saveCoins[\s\S]*setSummary\(/.test(hook), 'failed coin saves never overwrite the visible summary optimistically')
assert(hook.includes("throw new Error('金币奖励必须是非负数字')"), 'invalid coin input stays available for correction')
assert(/saveSourceCoins[\s\S]*await request\([\s\S]*notifyRewardCatalogUpdated\(\)/.test(api), 'successful coin saves notify every visible source summary after persistence')
console.log('source reward api contracts passed')
