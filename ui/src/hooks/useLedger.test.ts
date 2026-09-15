import { coinLedgerEntries, groupLedgerEntries, isGoalUnlockLedgerEntry, loadLedgerExportEntries, uniqueLedgerEntries } from './useLedger'
import type { LedgerEntry } from '../types'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const entry = (date: string, amount: number): LedgerEntry => ({ id: `${date}-${amount}`, amount, source_type: 'task', target_date: date })

const entries = [entry('2026-07-01', 3), entry('2026-07-01', 0.1), entry('2026-07-01', -1), entry('2026-07-01', -2), entry('2026-06-30', 0)]
const groups = groupLedgerEntries(entries)
const mixed = groups.find(group => group.date === '2026-07-01')!
assert(mixed.income === 3.1 && mixed.expense === 3, 'mixed group separates income from absolute expense')
assert(groups.find(group => group.date === '2026-06-30')!.income === 0 && groups.find(group => group.date === '2026-06-30')!.expense === 0, 'zero amount leaves daily totals unchanged')

const incomeGroups = groupLedgerEntries(entries.filter(item => item.amount > 0))
assert(incomeGroups[0].income === 3.1 && incomeGroups[0].expense === 0, 'income filter only sums visible income')

const loadedGroups = groupLedgerEntries([...entries, entry('2026-07-01', -4)])
assert(loadedGroups.find(group => group.date === '2026-07-01')!.expense === 7, 'loading another page recomputes the day expense')

const repeated = { ...entry('2026-07-02', 8), id: 'immutable-ledger-id', created_at: '2026-08-04 10:00:00' }
const merged = uniqueLedgerEntries([repeated, { ...repeated, target_date: '2026-07-01' }])
assert(merged.length === 1 && groupLedgerEntries(merged)[0].date === '2026-07-01', 'immutable IDs dedupe before grouping by business date')

const backpackUse = { ...entry('2026-07-02', 0), id: 'backpack-use', source_type: 'backpack_use' }
const goalUnlock = { ...entry('2026-07-02', 0), id: 'goal-unlock', source_type: 'reward_buy', source_id: 'reward:goal:goal_daily_20260702' }
const visible = coinLedgerEntries([...entries, backpackUse, goalUnlock])
assert(visible.some(item => item.id === 'backpack-use'), 'zero amount ledger facts remain visible in the coin ledger view')
assert(isGoalUnlockLedgerEntry(goalUnlock) && visible.some(item => item.id === 'goal-unlock'), 'zero amount goal unlock remains visible as a settlement fact')
assert(groupLedgerEntries(visible).find(group => group.date === '2026-07-01')!.expense === 3, 'visible coin groups preserve non-zero daily totals')

const calls: number[] = []
const exportRows = Array.from({ length: 191 }, (_, index) => ({
  id: `export-${index}`, amount: index % 2 ? 1 : -1, source_type: index % 3 ? 'task' : 'reward_buy', target_date: '2026-08-24',
}))
const db = { getLedgerFull: (limit: number, offset: number) => { calls.push(offset); return exportRows.slice(offset, offset + limit) } }
const income = await loadLedgerExportEntries(db, 'income', 100)
assert(calls.join(',') === '0,100' && income.length === 95, 'export must read all pages and apply the frozen income filter')
calls.length = 0
const rewards = await loadLedgerExportEntries(db, 'reward', 100)
assert(calls.join(',') === '0,100' && rewards.length === 191, 'reward export must not depend on visible list pagination')
const habitExport = await loadLedgerExportEntries({ getLedgerFull: (_limit: number, offset: number) => offset ? [] : [{ id: 'habit-cn', amount: 1, source_type: 'habit_checkin', target_date: '2026-09-06', description: '√ 习惯 慎独' }] }, 'all', 100)
assert(habitExport.length === 1 && habitExport[0].description === '√ 习惯 慎独' && habitExport[0].amount === 1, 'export preserves the authoritative Chinese habit title and configured amount')
let failed = false
try { await loadLedgerExportEntries({ getLedgerFull: () => { throw new Error('read failed') } }, 'all') } catch { failed = true }
assert(failed, 'export read failures must remain observable to the sheet')
console.log('useLedger daily summary tests passed')
