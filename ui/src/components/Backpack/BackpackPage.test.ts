import { BackpackPage, BACKPACK_MINIMUM_SLOTS, backpackFilters, canUseBackpackItem, DEFAULT_BACKPACK_FILTER, formatBackpackEvent, getBackpackItemDescription, groupBackpackItems } from './BackpackPage'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { BackpackItem } from '../../types'
import { readFileSync } from 'node:fs'
import { BACKPACK_REFRESH_EVENTS } from '../../hooks/backpackRefresh'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const items: BackpackItem[] = [
  { id: 'a', title: '物品', icon: '🎁', created_at: '2026-08-04', is_used: false },
  { id: 'b', title: '物品', icon: '🎁', created_at: '2026-08-04', is_used: false },
  { id: 'c', title: '物品', icon: '🎁', created_at: '2026-08-04', is_used: true, used_at: '2026-08-04 12:00:00' },
  { id: 'd', title: '月卡', icon: '📱', created_at: '2026-08-04', is_used: false, is_expired: true, expires_at: '2026-09-01 00:00:00' },
]

const available = groupBackpackItems(items, 'available')
assert(available.length === 1 && available[0].quantity === 2, 'available items share one grid slot')
const used = groupBackpackItems(items, 'used')
assert(used.length === 1 && used[0].item.id === 'c', 'used filter excludes available inventory')
assert(groupBackpackItems(items, 'expired')[0].item.id === 'd', 'expired complete items remain historical but leave available inventory')
assert(DEFAULT_BACKPACK_FILTER === 'available' && !backpackFilters.flat().join('|').includes('all') && !backpackFilters.flat().join('|').includes('全部'), 'backpack defaults to available and hides all')
assert(backpackFilters.some(([key, label]) => key === 'expired' && label === '已过期'), 'backpack exposes a recent expired tab')
assert(canUseBackpackItem(items[0]) && !canUseBackpackItem(items[2]), 'used inventory cannot be used again')
assert(!canUseBackpackItem(items[3]), 'expired inventory cannot expose a use action')
assert(getBackpackItemDescription({ ...items[0], description: '创建时填写的说明' }) === '创建时填写的说明', 'backpack detail preserves a reward description')
assert(getBackpackItemDescription(items[0]) === '暂无物品说明', 'backpack detail only uses the empty-description placeholder when the source is empty')
assert(BACKPACK_MINIMUM_SLOTS === 14, 'backpack reserves room for the event panel')
assert(formatBackpackEvent({ id: 'event', ledger_id: 'private', event_type: 'used', created_at: '2026-08-04 23:16:25', item_title: '解锁手机*1', quantity: 1 }) === '[2026-08-04 23:16:25]使用解锁手机*1*1', 'backpack event hides internal ledger identifiers')
assert(formatBackpackEvent({ id: 'fragment-event', ledger_id: 'fragment:private', event_type: 'fragment_expired', created_at: '2026-08-10 00:00:00', item_title: '解锁手机', quantity: 1, detail: '碎片已过期' }) === '[2026-08-10 00:00:00]碎片过期解锁手机*1（碎片已过期）', 'fragment events have readable lifecycle text')
assert(BACKPACK_REFRESH_EVENTS.includes('sync-pull-complete'), 'a completed fragment synthesis refreshes the backpack after sync')
const source = readFileSync(new URL('./BackpackPage.tsx', import.meta.url), 'utf8')
assert(source.includes('theme-page') && source.includes('theme-surface') && source.includes('dark:bg-slate-950'), 'backpack must use shared page/card theme surfaces and a dark event ledger')
assert(source.includes('selectedFragment') && source.includes('current_count') && source.includes('未合成，暂不可使用'), 'unfinished fragments are shown as unavailable backpack entries')
assert(source.includes('target_count') && source.includes('本周期已满'), 'count fragments show exact pieces and a generic period limit')
assert(source.includes('selected.is_expired') && source.includes('到期：'), 'complete item expiry remains visible in history')
assert(source.includes('isRefreshing &&') && source.includes('正在刷新'), 'background refresh shows a small status instead of a full-page skeleton')
assert(source.includes('最近没有过期物品') && source.includes('已过期，仅供查看'), 'expired fragments are read-only and have an empty state')
const props: any = { items: [items[0]], fragments: [], expiredFragments: [], events: [], isLoading: false, isRefreshing: true, hasMoreEvents: false, isLoadingMoreEvents: false, syncState: 'fresh', errorMessage: '', lastSuccessfulAt: null, serverUrl: '', useItem: async () => {}, loadMoreEvents: async () => {} }
const refreshing = renderToStaticMarkup(createElement(BackpackPage, props))
assert(refreshing.includes('正在刷新') && refreshing.includes('物品') && !refreshing.includes('animate-pulse'), 'refresh keeps inventory visible without a full-page skeleton')
assert(renderToStaticMarkup(createElement(BackpackPage, { ...props, isLoading: true })).includes('animate-pulse'), 'first load still shows a placeholder')
console.log('Backpack page contracts passed')
