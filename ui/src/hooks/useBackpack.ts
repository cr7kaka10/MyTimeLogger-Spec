// ui/src/hooks/useBackpack.ts
import { useCallback, useEffect, useState } from 'react'
import { requireActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import type { BackpackEvent, BackpackFragment, BackpackItem } from '../types'
import { getDatabase, pullSync } from '../db'
import { useEventRefresh } from './useEventRefresh'
import { BACKPACK_REFRESH_EVENTS, normalizeBackpackItems, preserveBackpackSnapshot } from './backpackRefresh'

export interface UseBackpackReturn {
  items: BackpackItem[]
  fragments: BackpackFragment[]
  events: BackpackEvent[]
  isLoading: boolean
  hasMoreEvents: boolean
  isLoadingMoreEvents: boolean
  useItem: (id: number | string) => Promise<void>
  discardItem: (id: number | string) => Promise<void>
  loadMoreEvents: () => Promise<void>
  refresh: () => Promise<void>
}

export const useBackpack = (): UseBackpackReturn => {
  const [items, setItems] = useState<BackpackItem[]>([])
  const [fragments, setFragments] = useState<BackpackFragment[]>([])
  const [events, setEvents] = useState<BackpackEvent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [hasMoreEvents, setHasMoreEvents] = useState(false)
  const [isLoadingMoreEvents, setIsLoadingMoreEvents] = useState(false)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const eventRefresh = useEventRefresh(BACKPACK_REFRESH_EVENTS)

  const load = useCallback(async () => {
    try {
      setIsLoading(true)
      const db = await getDatabase()
      const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'backpack.list')
      const response = await fetch(`${runtime.serverUrl}/api/rewards/backpack`, { headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken } })
      if (!response.ok) throw new Error('背包读取失败')
      const payload = await response.json()
      const eventResponse = await fetch(`${runtime.serverUrl}/api/rewards/backpack/events`, { headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken } })
      setItems(normalizeBackpackItems(payload.backpack || []))
      setFragments(payload.fragments || [])
      const nextEvents = eventResponse.ok ? (await eventResponse.json()).events || [] : []
      setEvents(nextEvents)
      setHasMoreEvents(nextEvents.length === 50)
    } catch {
      // A failed refresh must not discard the last successful inventory view.
      setItems(preserveBackpackSnapshot)
      setFragments(preserveBackpackSnapshot)
      setEvents(preserveBackpackSnapshot)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshTrigger, eventRefresh])

  const useItem = useCallback(async (id: number | string) => {
    const db = await getDatabase()
    const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'backpack.use')
    const response = await fetch(`${runtime.serverUrl}/api/rewards/use_item/${encodeURIComponent(String(id))}`, {
      method: 'POST', headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken },
    })
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
    const response = await fetch(`${runtime.serverUrl}/api/rewards/backpack/${encodeURIComponent(String(id))}/discard`, { method: 'POST', headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken } })
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
      const response = await fetch(`${runtime.serverUrl}/api/rewards/backpack/events?offset=${events.length}`, { headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken } })
      const next = response.ok ? (await response.json()).events || [] : []
      setEvents(previous => [...new Map([...previous, ...next].map(event => [event.id, event])).values()])
      setHasMoreEvents(next.length === 50)
    } finally { setIsLoadingMoreEvents(false) }
  }, [events.length, hasMoreEvents, isLoadingMoreEvents])

  return { items, fragments, events, isLoading, hasMoreEvents, isLoadingMoreEvents, useItem, discardItem, loadMoreEvents, refresh }
}
