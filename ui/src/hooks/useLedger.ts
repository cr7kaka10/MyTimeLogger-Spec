// ui/src/hooks/useLedger.ts
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { LedgerEntry, LedgerFilter } from '../types'
import { getDatabase } from '../db'
import { useEventRefresh } from './useEventRefresh'

const LEDGER_PAGE_SIZE = 100

export interface LedgerGroup {
  date: string
  items: LedgerEntry[]
  income: number
  expense: number
}

export interface UseLedgerReturn {
  entries: LedgerEntry[]
  filter: LedgerFilter
  setFilter: (f: LedgerFilter) => void
  groupedEntries: LedgerGroup[]
  summary: { balance: number; income: number; expense: number }
  hasMore: boolean
  isLoadingMore: boolean
  loadMore: () => Promise<void>
  exportEntries: (selectedFilter?: LedgerFilter) => Promise<LedgerEntry[]>
  refresh: () => Promise<void>
}

export const groupLedgerEntries = (entries: LedgerEntry[]): LedgerGroup[] => {
  const groups: Record<string, LedgerEntry[]> = {}
  for (const entry of entries) {
    const date = entry.target_date || (entry.occurred_at || '').slice(0, 10) || (entry.created_at || '').slice(0, 10) || '未知日期'
    if (!groups[date]) groups[date] = []
    groups[date].push(entry)
  }
  return Object.entries(groups)
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([date, items]) => ({
      date,
      items,
      income: items.reduce((total, item) => total + Math.max(0, Number(item.amount)), 0),
      expense: items.reduce((total, item) => total + Math.max(0, -Number(item.amount)), 0),
    }))
}

export const uniqueLedgerEntries = (entries: LedgerEntry[]) => [...new Map(entries.map(entry => [String(entry.id), entry])).values()]
export const isGoalUnlockLedgerEntry = (entry: LedgerEntry) => entry.source_type === 'reward_buy' && String(entry.source_id || '').includes(':goal:goal_')
export const coinLedgerEntries = (entries: LedgerEntry[]) => entries.filter(entry => Number.isFinite(Number(entry.amount)))

export const filterLedgerEntries = (entries: LedgerEntry[], selectedFilter: LedgerFilter) => {
  const visible = coinLedgerEntries(entries)
  if (selectedFilter === 'income') return visible.filter(entry => entry.amount > 0)
  if (selectedFilter === 'expense') return visible.filter(entry => entry.amount < 0)
  if (selectedFilter === 'reward') return visible.filter(entry => ['reward_buy', 'habit', 'task'].includes(entry.source_type))
  return visible
}

const withExerciseTitles = (db: any, entries: LedgerEntry[]) => entries.map(entry => {
  if (entry.source_type !== 'exercise_checkin') return entry
  const date = entry.target_date || (entry.created_at || '').slice(0, 10)
  const title = db.getExerciseCheckinTitle?.(date, entry.source_id)
  return title ? { ...entry, display_title: title } : entry
})

export const loadLedgerExportEntries = async (db: any, selectedFilter: LedgerFilter, pageSize = LEDGER_PAGE_SIZE) => {
  const loaded: LedgerEntry[] = []
  for (let offset = 0; ; offset += pageSize) {
    const page = db.getLedgerFull(pageSize, offset) as LedgerEntry[]
    loaded.push(...page)
    if (page.length < pageSize) break
  }
  return filterLedgerEntries(uniqueLedgerEntries(withExerciseTitles(db, loaded)), selectedFilter)
}

export const useLedger = (): UseLedgerReturn => {
  const [entries, setEntries] = useState<LedgerEntry[]>([])
  const [summary, setSummary] = useState({ balance: 0, income: 0, expense: 0 })
  const [hasMore, setHasMore] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [filter, setFilter] = useState<LedgerFilter>('all')
  const eventRefresh = useEventRefresh(['balance-updated', 'sync-pull-complete'])
  const [manualRefresh, setManualRefresh] = useState(0)

  useEffect(() => {
    getDatabase().then(db => {
      const raw = db.getLedgerFull(LEDGER_PAGE_SIZE, 0) as LedgerEntry[]
      setEntries(uniqueLedgerEntries(withExerciseTitles(db, raw)))
      setSummary(db.getLedgerSummary())
      setHasMore(raw.length === LEDGER_PAGE_SIZE)
    }).catch(() => {
      setEntries([])
      setSummary({ balance: 0, income: 0, expense: 0 })
      setHasMore(false)
    })
  }, [eventRefresh, manualRefresh])

  const filtered = useMemo(() => filterLedgerEntries(entries, filter), [entries, filter])

  const groupedEntries = useMemo(() => groupLedgerEntries(filtered), [filtered])

  const refresh = useCallback(async () => {
    setManualRefresh(prev => prev + 1)
  }, [])

  const exportEntries = useCallback(async (selectedFilter = filter) => (
    loadLedgerExportEntries(await getDatabase(), selectedFilter)
  ), [filter])

  const loadMore = useCallback(async () => {
    if (!hasMore || isLoadingMore) return
    setIsLoadingMore(true)
    try {
      const db = await getDatabase()
      const next = db.getLedgerFull(LEDGER_PAGE_SIZE, entries.length) as LedgerEntry[]
      setEntries(prev => uniqueLedgerEntries([...prev, ...withExerciseTitles(db, next)]))
      setHasMore(next.length === LEDGER_PAGE_SIZE)
      setSummary(db.getLedgerSummary())
    } catch {
      setHasMore(false)
    } finally {
      setIsLoadingMore(false)
    }
  }, [entries.length, hasMore, isLoadingMore])

  return { entries: filtered, filter, setFilter, groupedEntries, summary, hasMore, isLoadingMore, loadMore, exportEntries, refresh }
}
