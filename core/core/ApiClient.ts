/** HTTP API 客户端 — 从 app/core/api_client.py 翻译 */

import { SYNC_CONFIG } from './SyncConfig'

export interface ApiResponse<T = any> {
  ok: boolean
  data?: T
  error?: string
  status: number
  /** Correlates an API result with the sync run that initiated it. */
  request_id?: string
}

export interface ApiRequesterInit extends RequestInit { timeoutMs?: number }
export interface ApiRequesterResponse {
  ok: boolean
  status: number
  text(): Promise<string>
  json?(): Promise<unknown>
}
export type ApiRequester = (url: string, init: ApiRequesterInit) => Promise<ApiRequesterResponse>
const standardRequester: ApiRequester = (url, init) => fetch(url, init)

export type CurrentTimerOutcomeCode =
  | 'accepted' | 'stale_revision' | 'invalid_state' | 'auth'
  | 'network' | 'upgrade_required' | 'error'
export interface CurrentTimerState {
  user_id: number
  session_id: string
  owner_device_id: string
  updated_by_device_id?: string
  category_id?: number | string | null
  category_name: string
  current_note?: string
  state: 'running' | 'paused' | 'stopped'
  active: boolean
  started_at: string
  segment_started_at?: string | null
  active_elapsed_ms: number
  timer_mode?: 'countup' | 'countdown'
  duration_ms?: number
  pause_count?: number
  revision: number
  last_command_seq: number
  last_user_intent_id?: string
  last_heartbeat_at: string
  updated_at: string
  server_time: string
}
export interface CurrentTimerOutcome {
  code: CurrentTimerOutcomeCode
  status: number
  state?: CurrentTimerState | null
  lease?: CurrentTimerState | null
  revision?: number
  serverTime?: string
  errorCode?: string
  operation?: CurrentTimerOperation
  completedSessionId?: string
}
export type CurrentTimerOperation = 'start' | 'switch' | 'note' | 'pause' | 'resume' | 'stop'
export interface CurrentTimerCommandRequest {
  session_id?: string
  device_id: string
  observed_revision: number
  idempotency_key: string
  user_intent_id: string
  category_id?: number | string | null
  category_name?: string
  current_note?: string
  timer_mode?: 'countup' | 'countdown'
  duration_ms?: number
  session_summary?: string
}
export type TickTickTaskOperation = 'create' | 'update' | 'delete' | 'reconcile'
export interface TickTickTaskCommand {
  request_id: string; operation: TickTickTaskOperation; task_id?: string; project_id?: string; title?: string
  due_date?: string; tags?: string[]
  patch?: { title?: string; startDate?: string | null; dueDate?: string | null }
  expected?: { title?: string; startDate?: string | null; dueDate?: string | null; isAllDay?: boolean; timeZone?: string; repeatFlag?: string }
}
export interface TickTickTaskCommandResult { request_id: string; status: 'pending' | 'confirmed' | 'failed' | 'unknown' | 'conflict'; result_task_id?: string; error_code?: string }
export type HabitCheckinStatus = 0 | 1 | 2
export interface HabitCheckinCommand { habit_id: string; date: string; desired_status: HabitCheckinStatus; idempotency_key: string }
export interface HabitCheckinCommandResult { idempotency_key: string; status: 'pending' | 'provider_confirmed' | 'confirmed' | 'retryable_failed' | 'failed'; error_code?: string }
export type TimerLeaseSnapshot = CurrentTimerState
export type TimerLeaseOutcome = CurrentTimerOutcome

export class ApiClient {
  constructor(
    private baseUrl: string,
    private authToken: string,
    private timeout: number = SYNC_CONFIG.timeout.default,
    private readonly requester: ApiRequester = standardRequester,
  ) {}

  setToken(token: string): void {
    this.authToken = token
  }

  matchesConfig(baseUrl: string, authToken: string): boolean {
    return this.baseUrl === baseUrl && this.authToken === authToken
  }

  updateConfig(baseUrl: string, authToken: string): void {
    this.baseUrl = baseUrl
    this.authToken = authToken
  }

  private headers(requestId?: string, extra?: Record<string, string>): Record<string, string> {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (this.authToken) {
      h['Authorization'] = `Bearer ${this.authToken}`
    }
    if (requestId) {
      h['X-Sync-Run-Id'] = requestId
    }
    return { ...h, ...extra }
  }

  async get<T = any>(path: string, params?: Record<string, string>, timeout?: number, requestId?: string): Promise<ApiResponse<T>> {
    const url = this.buildUrl(path, params)
    return this.request<T>('GET', url, undefined, timeout, requestId)
  }

  async post<T = any>(path: string, body?: object, timeout?: number, requestId?: string): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${path}`
    return this.request<T>('POST', url, body, timeout, requestId)
  }

  async put<T = any>(path: string, body?: object): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${path}`
    return this.request<T>('PUT', url, body)
  }

  async delete<T = any>(path: string): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${path}`
    return this.request<T>('DELETE', url)
  }

  async commandTickTickTask(command: TickTickTaskCommand): Promise<ApiResponse<TickTickTaskCommandResult>> {
    return this.post<TickTickTaskCommandResult>('/api/ticktick/tasks/commands', command, SYNC_CONFIG.timeout.refresh, command.request_id)
  }

  async commandHabitCheckin(command: HabitCheckinCommand): Promise<ApiResponse<HabitCheckinCommandResult>> {
    return this.post<HabitCheckinCommandResult>('/api/habits/checkin-commands', command, SYNC_CONFIG.timeout.refresh, command.idempotency_key)
  }

  async retryHabitCheckin(idempotencyKey: string): Promise<ApiResponse<HabitCheckinCommandResult>> {
    return this.post<HabitCheckinCommandResult>(`/api/habits/checkin-commands/${encodeURIComponent(idempotencyKey)}/retry`, {}, SYNC_CONFIG.timeout.refresh, idempotencyKey)
  }

  private buildUrl(path: string, params?: Record<string, string>): string {
    const url = new URL(`${this.baseUrl}${path}`)
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
    }
    return url.toString()
  }

  private async request<T>(method: string, url: string, body?: object, timeout?: number, requestId?: string, extraHeaders?: Record<string, string>): Promise<ApiResponse<T>> {
    const controller = new AbortController()
    const timeoutMs = timeout ?? this.timeout
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    const startedAt = Date.now()
    const parsedUrl = new URL(url)
    const path = parsedUrl.pathname
    const origin = parsedUrl.origin
    const isSyncRequest = path.startsWith('/api/sync')
    if (isSyncRequest) {
      console.info('[ApiClient] request start', {
        request_id: requestId,
        method,
        path,
        token_present: Boolean(this.authToken),
      })
    }

    try {
      const init: ApiRequesterInit = {
        method,
        headers: this.headers(requestId, extraHeaders),
        signal: controller.signal,
        timeoutMs,
      }
      if (body && method !== 'GET') {
        init.body = JSON.stringify(body)
      }

      const resp = await this.requester(url, init)

      const text = await resp.text()
      let data: unknown
      if (text) {
        try { data = JSON.parse(text) } catch { data = text }
      }
      if (resp.status === 401 || resp.status === 403) {
        if (isSyncRequest) {
          console.warn('[ApiClient] request auth failed', { request_id: requestId, method, path, status: resp.status, elapsed_ms: Date.now() - startedAt })
        }
        return { ok: false, error: 'auth_expired', status: resp.status, request_id: requestId, data: data as T }
      }

      if (!resp.ok) {
        if (isSyncRequest) {
          console.warn('[ApiClient] request failed', { request_id: requestId, method, path, status: resp.status, elapsed_ms: Date.now() - startedAt })
        }
        return { ok: false, error: 'server_error', status: resp.status, request_id: requestId, data: data as T }
      }

      if (isSyncRequest) {
        console.info('[ApiClient] request ok', { request_id: requestId, method, path, status: resp.status, elapsed_ms: Date.now() - startedAt })
      }
      return { ok: true, data: data as T, status: resp.status, request_id: requestId }
    } catch (e: any) {
      if (e?.name === 'AbortError' || controller.signal.aborted || /timeout/i.test(String(e?.message || ''))) {
        if (isSyncRequest) {
          console.warn(`[ApiClient] request timeout request_id=${requestId || ''} method=${method} url=${origin}${path} elapsed_ms=${Date.now() - startedAt}`)
        }
        return { ok: false, error: 'request_timeout', status: 0, request_id: requestId }
      }
      if (isSyncRequest) {
        console.warn(`[ApiClient] request network error request_id=${requestId || ''} method=${method} url=${origin}${path} elapsed_ms=${Date.now() - startedAt}`)
      }
      return { ok: false, error: 'server_unreachable', status: 0, request_id: requestId }
    } finally {
      clearTimeout(timer)
    }
  }

  private async currentTimerRequest<T>(method: string, path: string, body?: object, timeout?: number): Promise<ApiResponse<T>> {
    return this.request<T>(method, `${this.baseUrl}${path}`, body, timeout, undefined, {
      'X-MTL-Timer-State': 'timer-current-state-v1',
    })
  }

  private mapCurrentTimerResponse(response: ApiResponse<any>): CurrentTimerOutcome {
    const data = response.data ?? {}
    if (response.ok) {
      return {
        code: ['accepted', 'active', 'stopped'].includes(data.status) ? 'accepted' : 'error',
        status: response.status,
        state: data.state ?? null,
        lease: data.state ?? null,
        revision: data.revision ?? data.state?.revision,
        serverTime: data.server_time ?? data.state?.server_time,
        errorCode: data.error_code,
        operation: data.operation,
        completedSessionId: data.completed_session_id,
      }
    }
    if (response.status === 401 || response.status === 403) return { code: 'auth', status: response.status }
    if (response.status === 426) return { code: 'upgrade_required', status: response.status }
    const errorCode = data.error_code
    if (errorCode === 'stale_timer_revision') {
      return {
        code: 'stale_revision', status: response.status, state: data.state ?? null,
        lease: data.state ?? null, revision: data.state?.revision, errorCode,
      }
    }
    if (response.status === 409) {
      return {
        code: 'invalid_state', status: response.status, state: data.state ?? null,
        lease: data.state ?? null, revision: data.state?.revision, errorCode,
      }
    }
    if (response.status === 0) return { code: response.error === 'request_timeout' ? 'network' : 'network', status: 0 }
    return { code: 'error', status: response.status, errorCode }
  }

  async readCurrentTimer(timeout?: number): Promise<CurrentTimerOutcome> {
    return this.mapCurrentTimerResponse(
      await this.currentTimerRequest('GET', '/api/timer/current', undefined, timeout),
    )
  }

  async commandCurrentTimer(
    operation: CurrentTimerOperation,
    request: CurrentTimerCommandRequest,
    timeout?: number,
  ): Promise<CurrentTimerOutcome> {
    const body: CurrentTimerCommandRequest = {
      session_id: request.session_id,
      device_id: request.device_id,
      observed_revision: request.observed_revision,
      idempotency_key: request.idempotency_key,
      user_intent_id: request.user_intent_id,
      category_id: request.category_id,
      category_name: request.category_name,
      current_note: request.current_note,
      timer_mode: request.timer_mode,
      duration_ms: request.duration_ms,
      session_summary: request.session_summary,
    }
    return this.mapCurrentTimerResponse(
      await this.currentTimerRequest('POST', `/api/timer/current/${operation}`, body, timeout),
    )
  }
}
