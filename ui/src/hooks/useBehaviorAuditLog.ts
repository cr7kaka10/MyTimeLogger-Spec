import { useCallback, useEffect, useRef, useState } from 'react'
import { platformFetch } from '../platform/fetch'
import type { ManagementPlanRuntime } from './useManagementPlan'

export type BehaviorEvent = { event_id: string; occurred_at: string; runtime: string; page: string; action: string; target_type?: string; target_id?: string; result: string; error_code?: string; summary: string; detail: string; page_label: string; result_label: string }
const beijingDate = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())

export function useBehaviorAuditLog(runtime: ManagementPlanRuntime, enabled: boolean) {
  const [date, setDate] = useState(beijingDate); const [events, setEvents] = useState<BehaviorEvent[]>([])
  const [cursor, setCursor] = useState(''); const [loading, setLoading] = useState(false); const [error, setError] = useState('')
  const requestSeq = useRef(0)
  const load = useCallback(async (nextCursor = '', append = false) => {
    if (!runtime.serverUrl || !runtime.authToken) return
    const seq = ++requestSeq.current; setLoading(true); setError('')
    try {
      const query = new URLSearchParams({ date, limit: '50' }); if (nextCursor) query.set('cursor', nextCursor)
      const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}/api/v1/behavior-events?${query}`, { headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken } })
      const body = await response.json(); if (!response.ok) throw new Error(String(body?.detail || '行为日志读取失败'))
      if (seq !== requestSeq.current) return
      setEvents(current => append ? [...current, ...(body.events || [])] : (body.events || [])); setCursor(body.next_cursor || '')
    } catch (cause: any) { if (seq === requestSeq.current) setError(String(cause?.message || '行为日志读取失败')) } finally { if (seq === requestSeq.current) setLoading(false) }
  }, [date, runtime.authToken, runtime.serverUrl])
  useEffect(() => { if (enabled) { setEvents([]); setCursor(''); void load() } }, [enabled, date, load])
  return { date, setDate, events, cursor, loading, error, reload: () => load(), loadMore: () => load(cursor, true) }
}
