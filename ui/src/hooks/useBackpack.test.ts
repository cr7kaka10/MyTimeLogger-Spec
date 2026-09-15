import { BACKPACK_REFRESH_EVENTS, normalizeBackpackItems, preserveBackpackSnapshot } from './backpackRefresh'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const previous = [{ id: 'item', title: '说明已更新', icon: '🎁', description: '商品说明', created_at: '2026-08-05', is_used: false }]
const normalized = normalizeBackpackItems([{ ...previous[0], description: null as unknown as string }])

assert(BACKPACK_REFRESH_EVENTS.includes('reward-catalog-updated') && BACKPACK_REFRESH_EVENTS.includes('sync-pull-complete'), 'backpack refreshes after local catalog saves and remote sync')
assert(normalized[0].description === '' && normalized[0].is_used === false, 'backpack normalizes incomplete API payloads')
assert(preserveBackpackSnapshot(previous) === previous, 'a failed refresh keeps the last successful inventory')
console.log('useBackpack refresh contracts passed')
