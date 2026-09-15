import { getLedgerOccurredTime } from './LedgerSheet'
import { groupLedgerEntries } from '../../hooks/useLedger'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

const actual = { id: 'actual', amount: 1, source_type: 'habit_checkin', occurred_at: '2026-08-22 07:15:00', created_at: '2026-08-24 00:58:00' }
const unknown = { id: 'unknown', amount: 1, source_type: 'habit_checkin', occurred_at: undefined, created_at: '2026-08-24 00:58:00' }

assert(getLedgerOccurredTime(actual) === '07:15', 'habit ledger renders the TickTick operation time')
assert(getLedgerOccurredTime(unknown) === '', 'missing operation time does not fall back to sync time')
assert(groupLedgerEntries([{ ...actual, target_date: '' }])[0].date === '2026-08-22', 'ledger groups by actual occurrence date before write time')
console.log('Ledger occurred-at contract tests passed')
