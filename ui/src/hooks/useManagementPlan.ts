import { useCallback, useState } from 'react'
import { platformFetch } from '../platform/fetch'

export type ManagementPlanState = 'idle' | 'generating' | 'editing' | 'previewing' | 'applying' | 'result' | 'error'
export type ManagementPlanMode = 'review' | 'proposal'

export interface ManagementPlanRuntime { serverUrl: string; authToken: string }
export interface ManagementPlanItem { logical_key: string; type: string; action: string; title?: string; name?: string; expected_minutes?: number; reason?: string; reward?: { coins?: number } }
export interface ManagementPlanEvidenceRule { kind: string; source_id: string; source_title: string; source_status: string; coins: number; penalty: number; period?: string }
export interface ManagementPlanEvidenceItem { title: string; price: number; source_type?: string | null; source_title: string; source_status: string; required_count: number; inventory_mode: string; inventory_limit?: number | null; status: string }
export interface ManagementPlanEvidence { reward_rules: ManagementPlanEvidenceRule[]; store_items: ManagementPlanEvidenceItem[]; summary: { reward_rule_count: number; store_item_count: number; unresolved_source_count: number; truncated: boolean; data_updated_at?: string | null } }
export interface ManagementPlanReview { strengths: string[]; risks: string[]; recommendations: string[]; evidence?: ManagementPlanEvidence }
export interface ManagementPlanPayload { mode?: ManagementPlanMode; policy_version?: string; summary?: string; review?: ManagementPlanReview; items: ManagementPlanItem[]; [key: string]: unknown }
export interface ManagementPlanDraft { draft_id: string; context_version: string; plan_digest?: string; payload: ManagementPlanPayload; expires_at?: string }
export interface ManagementPlanPreview { plan_digest?: string; payload?: ManagementPlanPayload; warnings?: string[]; impact?: Array<{ logical_key: string; type: string; action: string; record_id?: string; unlock_source_type?: string; unlock_source_id?: string; price?: number; reward_coins?: number }> }

export function useManagementPlan(runtime: ManagementPlanRuntime) {
  const [state, setState] = useState<ManagementPlanState>('idle')
  const [draft, setDraft] = useState<ManagementPlanDraft | null>(null)
  const [preview, setPreview] = useState<ManagementPlanPreview | null>(null)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')

  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    if (!runtime.serverUrl || !runtime.authToken) throw new Error('请先连接服务端')
    const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken, ...(init.headers || {}) },
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      const code = body?.detail?.error_code
      const knownMessages: Record<string, string> = {
        management_plan_non_simplified_chinese: '大模型回复不是简体中文，请重新生成方案',
        plan_stale: '方案引用的数据已变化，请重新校验或重新生成',
        draft_expired: '方案草案已过期，请重新生成',
        review_not_applicable: '总结方案仅供阅读，不能确认应用',
      }
      throw new Error(knownMessages[code] || body?.detail?.message || body?.detail || body?.message || '管理方案请求失败')
    }
    return body
  }, [runtime.authToken, runtime.serverUrl])

  const generate = useCallback(async (requestText: string) => {
    setState('generating'); setError(''); setResult(null)
    try {
      const next = await request('/api/management-plans/drafts', { method: 'POST', body: JSON.stringify({ request: requestText }) }) as ManagementPlanDraft
      setDraft(next); setPreview(null); setState('editing'); return next
    } catch (cause: any) {
      setError(String(cause?.message || '生成方案失败')); setState('error'); throw cause
    }
  }, [request])

  const previewDraft = useCallback(async (payload?: ManagementPlanPayload) => {
    if (!draft) throw new Error('没有可预览的草案')
    setState('previewing'); setError('')
    try {
      const next = await request(`/api/management-plans/drafts/${encodeURIComponent(draft.draft_id)}/preview`, { method: 'POST', body: JSON.stringify({ payload: payload || draft.payload }) }) as ManagementPlanPreview
      setPreview(next); setDraft(previous => previous ? { ...previous, ...next } : previous); setState('editing'); return next
    } catch (cause: any) {
      setError(String(cause?.message || '预览方案失败')); setState('error'); throw cause
    }
  }, [draft, request])

  const apply = useCallback(async () => {
    if (!draft?.plan_digest) throw new Error('请先预览方案')
    if (draft.payload.mode === 'review') throw new Error('方案总结仅供阅读，不能确认应用')
    setState('applying'); setError('')
    try {
      const next = await request(`/api/management-plans/drafts/${encodeURIComponent(draft.draft_id)}/apply`, { method: 'POST', body: JSON.stringify({ plan_digest: draft.plan_digest, idempotency_key: `ui-${draft.draft_id}` }) })
      setResult(next); setState('result'); window.dispatchEvent(new Event('management-plan-applied')); return next
    } catch (cause: any) {
      setError(String(cause?.message || '应用方案失败')); setState('error'); throw cause
    }
  }, [draft, request])

  const reset = useCallback(() => { setState('idle'); setDraft(null); setPreview(null); setResult(null); setError('') }, [])
  return { state, draft, preview, result, error, generate, previewDraft, apply, reset, setDraft }
}
