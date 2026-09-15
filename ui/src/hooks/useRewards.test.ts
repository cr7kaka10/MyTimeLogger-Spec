import { REWARD_CATALOG_UPDATED, notifyRewardCatalogUpdated } from './rewardCatalogRefresh'
import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const emitted: string[] = []

Object.assign(globalThis, { window: { dispatchEvent: (event: Event) => emitted.push(event.type) } })
notifyRewardCatalogUpdated()

assert(REWARD_CATALOG_UPDATED === 'reward-catalog-updated', 'reward catalog refresh event has a stable name')
assert(emitted.length === 1 && emitted[0] === REWARD_CATALOG_UPDATED, 'successful reward saves notify the backpack exactly once')
const source = readFileSync(new URL('./useRewards.ts', import.meta.url), 'utf8')
assert(/response\.ok\) \{[\s\S]*await pullSync\(true\)[\s\S]*setRefreshTrigger/.test(source), 'reward catalog refreshes local cards after server templates are created')
assert(source.includes('amount?: number, note?: string') && source.includes('JSON.stringify(amount === undefined ? {} : { amount, note })'), 'custom purchases submit their descriptive note to the server')
console.log('useRewards refresh contracts passed')
