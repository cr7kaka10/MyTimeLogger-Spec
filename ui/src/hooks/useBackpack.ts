// ui/src/hooks/useBackpack.ts
import { useCallback, useEffect, useRef, useState } from 'react'
import { environmentKey, requireActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import type { BackpackEvent, BackpackFragment, BackpackItem, ExpiredBackpackFragment } from '../types'
import { getDatabase, pullSync } from '../db'
import { useEventRefresh } from './useEventRefresh'
import { BACKPACK_REFRESH_EVENTS, normalizeBackpackItems, preserveBackpackSnapshot } from './backpackRefresh'
import { protectedPlatformFetch } from '../platform/protectedRequest'

export interface UseBackpackReturn {
  items: BackpackItem[]
  fragments: BackpackFragment[]
  expiredFragments: ExpiredBackpackFragment[]
  events: BackpackEvent[]
  isLoading: boolean
  isRefreshing: boolean
  hasMoreEvents: boolean
  isLoadingMoreEvents: boolean
  syncState: 'fresh' | 'stale' | 'error'
  errorMessage: string
  lastSuccessfulAt: string | null
  serverUrl: string
  useItem: (id: number | string) => Promise<void>
  discardItem: (id: number | string) => Promise<void>
  loadMoreEvents: () => Promise<void>
  refresh: () => Promise<void>
}

export const useBackpack = (): UseBackpackReturn => {
  const [items, setItems] = useState<BackpackItem[]>([])
  const [fragments, setFragments] = useState<BackpackFragment[]>([])
  const [expiredFragments, setExpiredFragments] = useState<ExpiredBackpackFragment[]>([])
  const [events, setEvents] = useState<BackpackEvent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [hasMoreEvents, setHasMoreEvents] = useState(false)
  const [isLoadingMoreEvents, setIsLoadingMoreEvents] = useState(false)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [syncState, setSyncState] = useState<'fresh' | 'stale' | 'error'>('error')
  const [errorMessage, setErrorMessage] = useState('')
  const [lastSuccessfulAt, setLastSuccessfulAt] = useState<string | null>(null)
  const [serverUrl, setServerUrl] = useState('')
  const requestSequence = useRef(0)
  const acceptedDataVersion = useRef(-1)
  const hasSuccessfulSnapshot = useRef(false)
  const hasAttemptedLoad = useRef(false)
  const eventRefresh = useEventRefresh(BACKPACK_REFRESH_EVENTS)

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current
    try {
      if (hasAttemptedLoad.current) setIsRefreshing(true)
      else setIsLoading(true)
      const db = await getDatabase()
      const config = db.getAllConfig()
      const runtime = requireActiveEnvironmentRuntimeConfig(config, 'backpack.list')
      const verifiedUserId = config[environmentKey(runtime.environment, 'verified_user_id')]
      setServerUrl(runtime.serverUrl)
      const response = await protectedPlatformFetch(runtime, '/api/rewards/backpack')
      if (response.status === 401) {
        throw new Error('认证失败，请重新登录当前环境')
      }
      if (!response.ok) throw new Error(`背包读取失败（HTTP ${response.status}）`)
      const payload = await response.json()
      if (verifiedUserId && String(payload.userId) !== String(verifiedUserId)) {
        throw new Error('背包账号与当前环境不一致，已保留上次成功数据')
      }
      const dataVersion = Number(payload.dataVersion ?? 0)
      if (dataVersion < acceptedDataVersion.current) return
      if (sequence !== requestSequence.current) return
      acceptedDataVersion.current = dataVersion
      setItems(normalizeBackpackItems(payload.backpack || []))
      setFragments(payload.fragments || [])
      setExpiredFragments(payload.expired_fragments || [])
      hasSuccessfulSnapshot.current = true
      setLastSuccessfulAt(new Date().toLocaleString('zh-CN', { hour12: false }))
      const eventResponse = await protectedPlatformFetch(runtime, '/api/rewards/backpack/events')
      if (eventResponse.status === 401) {
        throw new Error('认证失败，请重新登录当前环境')
      }
      if (!eventResponse.ok) throw new Error(`物品流水读取失败（HTTP ${eventResponse.status}），库存已保留`)
      if (sequence !== requestSequence.current) return
      const nextEvents = (await eventResponse.json()).events || []
      setEvents(nextEvents)
      setHasMoreEvents(nextEvents.length === 50)
      setSyncState('fresh')
      setErrorMessage('')
    } catch (reason) {
      if (sequence !== requestSequence.current) return
      // A failed refresh must not discard the last successful inventory view.
      setItems(preserveBackpackSnapshot)
      setFragments(preserveBackpackSnapshot)
      setExpiredFragments(preserveBackpackSnapshot)
      setEvents(preserveBackpackSnapshot)
      setSyncState(hasSuccessfulSnapshot.current ? 'stale' : 'error')
      setErrorMessage(reason instanceof Error ? reason.message : '背包读取失败，数据可能过期')
    } finally {
      hasAttemptedLoad.current = true
      if (sequence === requestSequence.current) { setIsLoading(false); setIsRefreshing(false) }
    }
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshTrigger, eventRefresh])

  const useItem = useCallback(async (id: number | string) => {
    const db = await getDatabase()
    const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'backpack.use')
    const response = await protectedPlatformFetch(runtime, `/api/rewards/use_item/${encodeURIComponent(String(id))}`, { method: 'POST' })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail || '使用物品失败')
    }
    await pullSync()
    setRefreshTrigger(prev => prev + 1)
  }, [])

  const discardItem = useCallback(async (id: number | string) => {
    const db = await getDatabase()
    const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'backpack.discard')
    const response = await protectedPlatformFetch(runtime, `/api/rewards/backpack/${encodeURIComponent(String(id))}/discard`, { method: 'POST' })
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || '丢弃物品失败')
    setRefreshTrigger(prev => prev + 1)
  }, [])

  const refresh = useCallback(async () => {
    setRefreshTrigger(prev => prev + 1)
  }, [])

  const loadMoreEvents = useCallback(async () => {
    if (isLoadingMoreEvents || !hasMoreEvents) return
    setIsLoadingMoreEvents(true)
    try {
      const db = await getDatabase()
      const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'backpack.events')
      const response = await protectedPlatformFetch(runtime, `/api/rewards/backpack/events?offset=${events.length}`)
      const next = response.ok ? (await response.json()).events || [] : []
      setEvents(previous => [...new Map([...previous, ...next].map(event => [event.id, event])).values()])
      setHasMoreEvents(next.length === 50)
    } finally { setIsLoadingMoreEvents(false) }
  }, [events.length, hasMoreEvents, isLoadingMoreEvents])

  return { items, fragments, expiredFragments, events, isLoading, isRefreshing, hasMoreEvents, isLoadingMoreEvents, syncState, errorMessage, lastSuccessfulAt, serverUrl, useItem, discardItem, loadMoreEvents, refresh }
}
