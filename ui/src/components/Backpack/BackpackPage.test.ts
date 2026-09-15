import { BACKPACK_MINIMUM_SLOTS, backpackFilters, canUseBackpackItem, DEFAULT_BACKPACK_FILTER, formatBackpackEvent, getBackpackItemDescription, groupBackpackItems } from './BackpackPage'
import type { BackpackItem } from '../../types'
import { readFileSync } from 'node:fs'
import { BACKPACK_REFRESH_EVENTS } from '../../hooks/backpackRefresh'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const items: BackpackItem[] = [
  { id: 'a', title: '物品', icon: '🎁', created_at: '2026-08-04', is_used: false },
  { id: 'b', title: '物品', icon: '🎁', created_at: '2026-08-04', is_used: false },
  { id: 'c', title: '物品', icon: '🎁', created_at: '2026-08-04', is_used: true, used_at: '2026-08-04 12:00:00' },
]

const available = groupBackpackItems(items, 'available')
assert(available.length === 1 && available[0].quantity === 2, 'available items share one grid slot')
const used = groupBackpackItems(items, 'used')
assert(used.length === 1 && used[0].item.id === 'c', 'used filter excludes available inventory')
assert(DEFAULT_BACKPACK_FILTER === 'available' && !backpackFilters.flat().join('|').includes('all') && !backpackFilters.flat().join('|').includes('全部'), 'backpack defaults to available and hides all')
assert(canUseBackpackItem(items[0]) && !canUseBackpackItem(items[2]), 'used inventory cannot be used again')
assert(getBackpackItemDescription({ ...items[0], description: '创建时填写的说明' }) === '创建时填写的说明', 'backpack detail preserves a reward description')
assert(getBackpackItemDescription(items[0]) === '暂无物品说明', 'backpack detail only uses the empty-description placeholder when the source is empty')
assert(BACKPACK_MINIMUM_SLOTS === 14, 'backpack reserves room for the event panel')
assert(formatBackpackEvent({ id: 'event', ledger_id: 'private', event_type: 'used', created_at: '2026-08-04 23:16:25', item_title: '解锁手机*1', quantity: 1 }) === '[2026-08-04 23:16:25]使用解锁手机*1*1', 'backpack event hides internal ledger identifiers')
assert(formatBackpackEvent({ id: 'fragment-event', ledger_id: 'fragment:private', event_type: 'fragment_expired', created_at: '2026-08-10 00:00:00', item_title: '解锁手机', quantity: 1, detail: '碎片已过期' }) === '[2026-08-10 00:00:00]碎片过期解锁手机*1（碎片已过期）', 'fragment events have readable lifecycle text')
assert(BACKPACK_REFRESH_EVENTS.includes('sync-pull-complete'), 'a completed fragment synthesis refreshes the backpack after sync')
const source = readFileSync(new URL('./BackpackPage.tsx', import.meta.url), 'utf8')
assert(source.includes('theme-page') && source.includes('theme-surface') && source.includes('dark:bg-slate-950'), 'backpack must use shared page/card theme surfaces and a dark event ledger')
assert(source.includes('selectedFragment') && source.includes('current_count') && source.includes('未合成，暂不可使用'), 'unfinished fragments are shown as unavailable backpack entries')
assert(source.includes('progress_percent') && source.includes('本月已满'), 'fragment cards use percentage progress and show a full monthly limit')
console.log('Backpack page contracts passed')
