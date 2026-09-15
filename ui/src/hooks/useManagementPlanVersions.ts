import { useCallback, useState } from 'react'
import { platformFetch } from '../platform/fetch'
import type { ManagementPlanRuntime } from './useManagementPlan'

export function useManagementPlanVersions(runtime: ManagementPlanRuntime) {
  const [revisions, setRevisions] = useState<any[]>([])
  const [error, setError] = useState('')
  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}${path}`, { ...init, headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken, 'Content-Type': 'application/json', ...(init.headers || {}) } })
    const body = await response.json().catch(() => null)
    if (!response.ok) throw new Error(body?.detail?.message || body?.detail || '方案版本请求失败')
    return body
  }, [runtime.authToken, runtime.serverUrl])
  const load = useCallback(async () => {
    try { const body = await request('/api/management-plans/revisions'); setRevisions(body.revisions || []); setError(''); return body.revisions || [] } catch (cause: any) { setError(String(cause?.message || '读取版本失败')); throw cause }
  }, [request])
  const exportRevision = useCallback((id: string) => request(`/api/management-plans/revisions/${encodeURIComponent(id)}/export`), [request])
  const importPreview = useCallback((manifest: any) => request('/api/management-plans/import/preview', { method: 'POST', body: JSON.stringify({ manifest }) }), [request])
  const patchPreview = useCallback((id: string, patch: any) => request(`/api/management-plans/revisions/${encodeURIComponent(id)}/patch/preview`, { method: 'POST', body: JSON.stringify({ patch }) }), [request])
  const compare = useCallback((left: string, right: string) => request(`/api/management-plans/revisions/compare?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`), [request])
  return { revisions, error, load, exportRevision, importPreview, patchPreview, compare }
}
