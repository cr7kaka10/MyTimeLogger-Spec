import { useCallback, useEffect, useRef, useState } from 'react'
import { platformFetch } from '../platform/fetch'
import type { ManagementPlanRuntime } from './useManagementPlan'

export type MindmapStatus = 'active' | 'inactive' | 'completed' | 'source_missing' | 'read_only'
export interface MindmapReward { coins: number | null; penalty: number | null; status: 'configured' | 'unconfigured'; editable: boolean }
export interface MindmapProduct { id: string; title: string; icon?: string | null; price: number; description?: string | null; inventory_mode?: string | null; inventory_limit?: number | null; required_count?: number; status: string; editable: boolean; source_status: string }
export interface MindmapItem { source_type: string; source_id: string; title: string; status: MindmapStatus; metadata: Record<string, unknown>; reward: MindmapReward | null; items: MindmapProduct[]; children: MindmapItem[] }
export interface MindmapDomain { key: string; title: string; items: MindmapItem[] }
export interface ManagementPlanMindmap { refreshed_at: string; domains: MindmapDomain[]; unbound_products?: MindmapProduct[] }
export interface MindmapTree {
  id: 'management-plan'
  title: '管理方案'
  domains: MindmapDomain[]
  unboundProducts: MindmapProduct[]
}

function productFingerprint(product: MindmapProduct) {
  return `product:${product.id}:${product.title}:${product.price}:${product.description || ''}`
}

function findItem(items: MindmapItem[], sourceType: string, sourceId: string): MindmapItem | null {
  for (const item of items) {
    if (item.source_type === sourceType && item.source_id === sourceId) return item
    const nested = findItem(item.children || [], sourceType, sourceId)
    if (nested) return nested
  }
  return null
}

/** Returns the server-owned value that identifies the reward leaf opened from the mind map. */
export function mindmapRewardFingerprint(snapshot: ManagementPlanMindmap, context: { sourceType: string; sourceId: string; productId?: string }) {
  if (context.productId) {
    const product = [
      ...(snapshot.unbound_products || []),
      ...snapshot.domains.flatMap(domain => domain.items.flatMap(function collect(item): MindmapProduct[] {
        return [...item.items, ...(item.children || []).flatMap(collect)]
      })),
    ].find(candidate => candidate.id === context.productId)
    return product ? productFingerprint(product) : undefined
  }

  const item = snapshot.domains
    .map(domain => findItem(domain.items, context.sourceType, context.sourceId))
    .find(Boolean)
  return item ? `coins:${item.source_type}:${item.source_id}:${item.reward?.coins ?? ''}:${item.reward?.penalty ?? ''}` : undefined
}

/** Keep the UI hierarchy deterministic while preserving server-owned facts. */
const projectItem = (item: MindmapItem): MindmapItem => ({
  ...item,
  metadata: { ...item.metadata },
  reward: item.reward ? { ...item.reward } : null,
  items: item.items.map(product => ({ ...product })),
  children: (item.children || []).map(projectItem),
})

export function projectManagementPlanMindmap(snapshot: ManagementPlanMindmap): MindmapTree {
  return {
    id: 'management-plan',
    title: '管理方案',
    unboundProducts: (snapshot.unbound_products || []).map(product => ({ ...product })),
    domains: snapshot.domains.map(domain => ({
      ...domain,
      items: domain.items.map(projectItem),
    })),
  }
}

export function useManagementPlanMindmap(runtime: ManagementPlanRuntime) {
  const [snapshot, setSnapshot] = useState<ManagementPlanMindmap | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const requestSeq = useRef(0)

  const refresh = useCallback(async () => {
    if (!runtime.serverUrl || !runtime.authToken) { setError('请先连接服务端'); return null }
    const seq = ++requestSeq.current
    setLoading(true); setError('')
    try {
      const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}/api/management-plans/mindmap`, { headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken } })
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(body?.detail?.message || body?.detail || '读取当前数据库配置失败')
      if (seq === requestSeq.current) setSnapshot(body as ManagementPlanMindmap)
      return body as ManagementPlanMindmap
    } catch (cause: any) {
      if (seq === requestSeq.current) setError(String(cause?.message || '读取当前数据库配置失败'))
      return null
    } finally { if (seq === requestSeq.current) setLoading(false) }
  }, [runtime.authToken, runtime.serverUrl])

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null
    const schedule = () => { if (timer) clearTimeout(timer); timer = setTimeout(() => void refresh(), 150) }
    const visible = () => { if (document.visibilityState === 'visible') schedule() }
    void refresh()
    window.addEventListener('sync-pull-complete', schedule)
    window.addEventListener('management-plan-applied', schedule)
    window.addEventListener('focus', schedule)
    document.addEventListener('visibilitychange', visible)
    return () => {
      if (timer) clearTimeout(timer)
      requestSeq.current += 1
      window.removeEventListener('sync-pull-complete', schedule)
      window.removeEventListener('management-plan-applied', schedule)
      window.removeEventListener('focus', schedule)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [refresh])
  return { snapshot, tree: snapshot ? projectManagementPlanMindmap(snapshot) : null, loading, error, refresh }
}
