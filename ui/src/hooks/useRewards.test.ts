import { REWARD_CATALOG_UPDATED, notifyRewardCatalogUpdated } from './rewardCatalogRefresh'
import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const emitted: string[] = []

Object.assign(globalThis, { window: { dispatchEvent: (event: Event) => emitted.push(event.type) } })
notifyRewardCatalogUpdated()

assert(REWARD_CATALOG_UPDATED === 'reward-catalog-updated', 'reward catalog refresh event has a stable name')
assert(emitted.length === 1 && emitted[0] === REWARD_CATALOG_UPDATED, 'successful reward saves notify the backpack exactly once')
const source = readFileSync(new URL('./useRewards.ts', import.meta.url), 'utf8')
assert(/if \(!response\.ok\)[\s\S]*payload\?\.detail[\s\S]*await pullSync\(\)[\s\S]*setRefreshTrigger/.test(source), '2xx saves pull and structured 4xx details remain visible')
assert(source.includes('无法连接服务器，请检查服务是否启动及网络设置'), 'network failures must not expose raw Failed to fetch')
assert(!source.includes("inventory_mode: body.inventory_mode === 'weekly' ? 'unlimited'"), 'weekly inventory must be sent unchanged')
assert(source.includes('amount?: number, note?: string') && source.includes('JSON.stringify(amount === undefined ? {} : { amount, note })'), 'custom purchases submit their descriptive note to the server')
console.log('useRewards refresh contracts passed')
