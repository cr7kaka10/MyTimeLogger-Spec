import { BACKPACK_REFRESH_EVENTS, normalizeBackpackItems, preserveBackpackSnapshot } from './backpackRefresh'
import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const previous = [{ id: 'item', title: '说明已更新', icon: '🎁', description: '商品说明', created_at: '2026-08-05', is_used: false }]
const normalized = normalizeBackpackItems([{ ...previous[0], description: null as unknown as string, is_expired: 1 as unknown as boolean }])

assert(BACKPACK_REFRESH_EVENTS.includes('reward-catalog-updated') && BACKPACK_REFRESH_EVENTS.includes('sync-pull-complete') && BACKPACK_REFRESH_EVENTS.includes('balance-updated'), 'backpack refreshes after reward settlement, local catalog saves and remote sync')
assert(normalized[0].description === '' && normalized[0].is_used === false && normalized[0].is_expired === true, 'backpack normalizes availability and expiry payloads')
assert(preserveBackpackSnapshot(previous) === previous, 'a failed refresh keeps the last successful inventory')
const source = readFileSync(new URL('./useBackpack.ts', import.meta.url), 'utf8')
assert(source.includes('protectedPlatformFetch(runtime'), 'PC and Android backpack requests share the protected transport')
assert(source.includes('String(payload.userId) !== String(verifiedUserId)') && source.includes('背包账号与当前环境不一致'), 'a mismatched account cannot replace the previous backpack snapshot')
assert(source.includes('if (hasAttemptedLoad.current) setIsRefreshing(true)'), 'retries after success or failure do not replace the entire page with a skeleton')
assert(source.includes('hasAttemptedLoad.current = true'), 'initial loading state ends after the first attempt')
assert(source.indexOf('setItems(normalizeBackpackItems(') < source.indexOf("protectedPlatformFetch(runtime, '/api/rewards/backpack/events')"), 'inventory is applied before the optional events request can fail')
console.log('useBackpack refresh contracts passed')
