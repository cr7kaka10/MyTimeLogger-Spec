import { useCallback, useEffect, useRef, useState } from 'react'
import { syncNow } from '../db'
import { platformFetch } from '../platform/fetch'

export type ChecklistTaskSubmission = { status: 'optimistic' | 'confirmed' | 'failed'; error?: string }
export type ChecklistTaskInput = { requestId: string; title?: string; dueDate: string; tags?: string[]; flashRecommendationId?: string; learningTaskId?: string; onConfirmed?: () => void; onFailed?: (error: Error) => void }
type Runtime = { serverUrl: string; authToken: string }
const retryDelays = [5_000, 20_000, 60_000, 300_000]

export function useChecklistTaskSubmission(runtime: Runtime | undefined, refresh?: () => Promise<void>) {
  const [submissions, setSubmissions] = useState<Record<string, ChecklistTaskSubmission>>({})
  const timers = useRef(new Map<string, number>())
  const confirmedKeys = useRef(new Set<string>())
  const submissionRequestIds = useRef(new Map<string, string>())
  useEffect(() => () => timers.current.forEach(timer => window.clearTimeout(timer)), [])
  const request = useCallback(async (body: Record<string, unknown>) => {
    if (!runtime?.serverUrl || !runtime.authToken) throw new Error('请先连接服务端')
    const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}/api/ticktick/tasks/commands`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken }, body: JSON.stringify(body) })
    const result = await response.json().catch(() => null)
    if (!response.ok) { const error = Object.assign(new Error(result?.detail?.message || result?.message || '任务操作失败'), { httpStatus: response.status }); throw error }
    return result as { status?: string; error_code?: string }
  }, [runtime?.authToken, runtime?.serverUrl])
  const stop = useCallback((key: string) => { const timer = timers.current.get(key); if (timer) window.clearTimeout(timer); timers.current.delete(key) }, [])
  const confirmed = useCallback((key: string, input: ChecklistTaskInput) => {
    stop(key); setSubmissions(current => ({ ...current, [key]: { status: 'confirmed' } }))
    if (!confirmedKeys.current.has(input.requestId)) {
      confirmedKeys.current.add(input.requestId)
      input.onConfirmed?.()
    }
    void syncNow({ reason: 'checklist-task-confirmed' }).then(() => refresh?.()).catch(() => {})
  }, [refresh, stop])
  const failed = useCallback((key: string, input: ChecklistTaskInput, error: unknown) => {
    const reason = error instanceof Error ? error : new Error(String((error as Error)?.message || '加入清单失败'))
    stop(key)
    setSubmissions(current => ({ ...current, [key]: { status: 'failed', error: reason.message } }))
    input.onFailed?.(reason)
  }, [stop])
  const reconcile = useCallback((key: string, input: ChecklistTaskInput, attempt: number) => {
    const schedule = (nextAttempt: number) => {
      const delay = retryDelays[Math.min(nextAttempt, retryDelays.length - 1)]
      timers.current.set(key, window.setTimeout(async () => {
        try {
          const result = await request({ request_id: input.requestId, operation: 'reconcile' })
          if (result.status === 'confirmed') confirmed(key, input)
          else if (result.status === 'unknown') schedule(nextAttempt + 1)
          else failed(key, input, new Error(result.error_code || '加入清单失败'))
        } catch (error: any) {
          if (error?.httpStatus === 404) failed(key, input, error)
          else schedule(nextAttempt + 1)
        }
      }, delay))
    }
    schedule(attempt)
  }, [confirmed, failed, request])
  const submit = useCallback((key: string, input: ChecklistTaskInput) => {
    if (submissions[key]?.status === 'optimistic') return
    submissionRequestIds.current.set(key, input.requestId)
    setSubmissions(current => ({ ...current, [key]: { status: 'optimistic' } }))
    void request({ request_id: input.requestId, operation: 'create', title: input.title, due_date: input.dueDate, tags: input.tags, flash_recommendation_id: input.flashRecommendationId, learning_task_id: input.learningTaskId }).then(result => {
      if (result.status === 'confirmed') confirmed(key, input)
      else if (result.status === 'unknown') reconcile(key, input, 0)
      else failed(key, input, new Error(result.error_code || '加入清单失败'))
    }).catch((error: any) => String(error?.message || '').includes('请先连接服务端') ? failed(key, input, error) : reconcile(key, input, 0))
  }, [confirmed, failed, reconcile, request, submissions])
  const clear = useCallback((key: string) => {
    stop(key)
    const requestId = submissionRequestIds.current.get(key)
    if (requestId) confirmedKeys.current.delete(requestId)
    submissionRequestIds.current.delete(key)
    setSubmissions(current => {
      const next = { ...current }
      delete next[key]
      return next
    })
  }, [stop])
  return { submissions, submit, clear }
}
