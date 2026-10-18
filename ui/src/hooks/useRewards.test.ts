import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const source = readFileSync(new URL('./useRewards.ts', import.meta.url), 'utf8')
const refreshSource = readFileSync(new URL('./rewardCatalogRefresh.ts', import.meta.url), 'utf8')
assert(refreshSource.includes("REWARD_CATALOG_UPDATED = 'reward-catalog-updated'"), 'reward catalog refresh event has a stable name')
assert((refreshSource.match(/dispatchEvent/g) || []).length === 1, 'the refresh helper dispatches exactly once')
assert((source.match(/notifyRewardCatalogUpdated\(\)/g) || []).length === 1, 'successful reward saves notify the backpack exactly once')
assert(/if \(!response\.ok\)[\s\S]*payload\?\.detail[\s\S]*await pullSync\(\)[\s\S]*setRefreshTrigger/.test(source), '2xx saves pull and structured 4xx details remain visible')
assert(source.includes('无法连接服务器，请检查服务是否启动及网络设置'), 'network failures must not expose raw Failed to fetch')
assert(!source.includes("inventory_mode: body.inventory_mode === 'weekly' ? 'unlimited'"), 'weekly inventory must be sent unchanged')
assert(source.includes('amount?: number, note?: string') && source.includes('JSON.stringify(amount === undefined ? {} : { amount, note })'), 'custom purchases submit their descriptive note to the server')
assert(source.includes('convertFragmentToCount ? { convert_fragment_to_count: true } : {}'), 'legacy conversion is sent only after explicit confirmation')
console.log('useRewards refresh contracts passed')
