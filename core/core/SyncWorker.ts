/**
 * 后台同步引擎 — 从 app/core/sync_worker.py 翻译
 *
 * 职责：
 * - Push 队列：enqueue() → 事件驱动 POST SYNC_CONFIG.api.push
 * - Pull：GET SYNC_CONFIG.api.pull → LWW 合并
 * - 重试：指数退避 (1s→2s→4s→30s，最多 5 次)
 */

import { ApiClient } from './ApiClient'
import { resolve, SyncAction } from './SyncResolver'
import { applyBulkWithIsolation, planBulkMerge, type SafeBulkFailure } from './SyncBulkMerge'
import { pullCursorDecision, SyncFailureGate } from './SyncFailureGate'
import { filterMergePayload, validateMergeSchema } from './SyncMergeSchema'
import { SYNC_CONFIG } from './SyncConfig'
import { isServerOwnedTable, localLookupKeyForTable, naturalKeyForRecord, naturalKeysForTable, primaryKeyForTable, SYNC_ENTITY_NAMES } from './SyncEntities'
import type { Database } from '../models/Database'
import { normalizeTaskTimeFields, nowShanghaiDateTimeString } from '../utils/time'

/** 参与 Pull 的表由共享同步实体注册表唯一确定。 */
export const SYNC_TABLES = SYNC_ENTITY_NAMES

const SERVER_INTERNAL_SYNC_COLUMNS: Record<string, readonly string[]> = {
  exercise_checkins: ['log_id'],
}
const CATEGORY_NAME_ALIASES: Record<string, string> = { 家庭: '带娃', 车: '交通', 生活杂事: '个人杂事' }

export interface SyncRunResult {
  ok: boolean
  merged: number
  diagnostics?: Record<string, any>
  error?: string
}

export type SyncScope = 'core' | 'checklist'

export interface LedgerExpectation {
  sourceType: string
  targetDate: string
  exists: boolean
}

export interface SyncRunContext {
  syncRunId?: string
  reason?: string
  page?: number
  scope?: SyncScope
  ledgerExpectation?: LedgerExpectation
  ledgerConfirmationAttempt?: number
  walletReconcileAttempt?: number
}

export interface SyncOperationResult {
  change_id: string
  status: 'accepted' | 'duplicate' | 'skipped' | 'rejected'
  reason?: string
  table?: string
  record_id?: string | number
}

interface PushResult {
  ok: boolean
  statsStr?: string
  error?: string
  operationResults?: SyncOperationResult[]
  diagnostics?: Record<string, any>
}

export interface SyncWorkerOptions { enableSSE?: boolean; identityKey?: string }

type AndroidBulkOperation = { sql: string; params?: any[]; table?: string; recordId?: string; internal?: boolean }
type AndroidBulkCapability = {
  query(sql: string, params?: any[]): Record<string, any>[]
  transaction(operations: AndroidBulkOperation[]): void
  yieldToUi(): Promise<void>
}
type BulkMergeSummary = {
  merged: number; walletChanged: boolean
  errors: string[]; skipped: string[]; conflicts: string[]; failures: SafeBulkFailure[]
}

const BLOCKED_SYNC_CONFIG_KEYS = new Set([
  'account_identity_key', 'auth_token', 'ticktick_config', 'atimelogger_config', 'ai_model_config', 's3_backup_config',
])
const isBlockedSyncConfig = (table: string, payload: Record<string, any>) => table === 'system_config' && (
  BLOCKED_SYNC_CONFIG_KEYS.has(String(payload.key || '')) || /^env_(development|testing|production)_(auth_token|verified_user_id)$/.test(String(payload.key || ''))
)

export class SyncWorker {
  private _api: ApiClient | null = null
  private _db: Database | null = null
  private _queue = new Map<string, Set<number>>()
  private _retryCount = 0
  private _running = false
  private _pausedForReset = false
  private _eventSource: EventSource | null = null
  private _sseEnabled = false
  private _syncInFlight: Promise<SyncRunResult> | null = null
  private _syncRerunRequested = false
  private _syncRerunActionRequested = false
  private _pullInFlight: Promise<SyncRunResult> | null = null
  private _sessionVisibilityPullInFlight: Promise<SyncRunResult> | null = null
  private _sseVersionPullInFlight: Promise<void> | null = null
  private _latestSseVersion = 0
  private _lastPassivePullAt = 0
  private _recoveredInterruptedSending = false
  private _bulkColumns = new Map<string, Set<string>>()
  private _localColumns = new Map<string, Set<string>>()
  private _bulkFailureGate = new SyncFailureGate()
  private _lastBulkFailure: { fingerprint: string; version: number } | null = null
  private readonly _allowSSE: boolean
  private readonly _identityKey: string

  constructor(options: SyncWorkerOptions = {}) {
    this._allowSSE = options.enableSSE !== false
    this._identityKey = options.identityKey || ''
  }

  private _identityReady(): boolean { return Boolean(this._api && this._db) }

  private _syncScope(context: SyncRunContext): SyncScope {
    return context.scope === 'checklist' ? 'checklist' : 'core'
  }

  private _requiresAuthoritativePull(reason?: string): boolean {
    return reason === 'sse-changed' || reason === 'server-change-followup' || reason === 'session-visibility'
      || reason === 'user-action' || reason === 'user-action-followup'
  }

  private _createContext(reason: string): SyncRunContext {
    const cryptoApi = (globalThis as any).crypto
    const id = cryptoApi && typeof cryptoApi.randomUUID === 'function'
      ? cryptoApi.randomUUID()
      : `sync-${Date.now()}-${Math.random().toString(16).slice(2)}`
    return { syncRunId: id, reason, scope: 'core' }
  }

  private _logSync(level: 'info' | 'warn', details: Record<string, any>): void {
    const allowed = [
      'event', 'sync_run_id', 'platform', 'stage', 'schema', 'table', 'record_id',
      'batch_index', 'batch_size', 'error_category', 'columns', 'cursor', 'previous',
      'from', 'to', 'next', 'advanced', 'retry_at', 'elapsed_ms', 'merged',
      'tasks', 'habits', 'checkins', 'rewards', 'outbox', 'wallets',
      'scope', 'provider_requested', 'provider_executed', 'provider_blocked',
    ]
    const safe = Object.fromEntries(allowed.filter(key => details[key] !== undefined).map(key => [key, details[key]]))
    console[level](`[SyncWorker] ${JSON.stringify(safe)}`)
  }

  /** SSE 订阅服务端变更通知，收到事件立即 pull */
  connectSSE(serverUrl: string, token: string): void {
    if (this._identityKey && !this._identityReady()) return
    if (!this._allowSSE) return
    if (this._sseEnabled) return
    this._sseEnabled = true
    try {
      const url = `${serverUrl}${SYNC_CONFIG.api.events}?token=${encodeURIComponent(token)}`
      this._eventSource = new EventSource(url)

      this._eventSource.addEventListener('changed', (event: MessageEvent) => {
        this._handleChangedEvent(event).catch(() => {})
      })
      this._eventSource.addEventListener('timer-state-changed', () => {
        const target = globalThis as any
        if (typeof target.dispatchEvent === 'function' && typeof target.Event === 'function') {
          target.dispatchEvent(new target.Event('mtl:timer-state-changed'))
        }
      })

      this._eventSource.onerror = () => {
        // EventSource 内置自动重连，降级到定时 Pull 兜底
      }
    } catch {
      this._sseEnabled = false
    }
  }

  /** 关闭 SSE 订阅 */
  disconnectSSE(): void {
    if (this._eventSource) {
      this._eventSource.close()
      this._eventSource = null
    }
    this._sseEnabled = false
  }

  private async _handleChangedEvent(event: MessageEvent): Promise<void> {
    let payload: any = {}
    try {
      payload = JSON.parse(event.data || '{}') || {}
    } catch {
      // 无法识别的旧通知继续按既有全量同步路径处理。
    }
    const tables: unknown = payload.tables
    if (Array.isArray(tables) && tables.length === 1 && tables[0] === 'study_sessions') {
      await this.pullSessionVisibility()
      return
    }
    const serverVersion = Number(payload.server_version)
    if (Number.isSafeInteger(serverVersion) && serverVersion > 0) {
      this._latestSseVersion = Math.max(this._latestSseVersion, serverVersion)
      await this._pullToLatestSseVersion()
      return
    }
    await this.requestSync('sse-changed')
  }

  private async _pullToLatestSseVersion(): Promise<void> {
    if (this._sseVersionPullInFlight) return this._sseVersionPullInFlight
    const run = (async () => {
      const currentVersion = () => Number((this._db as any)?.getLastServerVersion?.() ?? -1)
      if (currentVersion() >= this._latestSseVersion) return
      if (this._syncInFlight) await this._syncInFlight
      if (currentVersion() >= this._latestSseVersion) return
      await this.requestSync('sse-changed')
    })()
    this._sseVersionPullInFlight = run
    try { await run } finally { this._sseVersionPullInFlight = null }
  }

  /** 动态更新配置（热载 ApiClient 与 EventSource 重连） */
  updateConfig(serverUrl: string, token: string): void {
    if (!serverUrl || !token) {
      this.stop()
      this.disconnectSSE()
      this._api?.updateConfig('', '')
      return
    }

    const isChanged = !this._api?.matchesConfig(serverUrl, token)
    if (isChanged) {
      if (this._api) this._api.updateConfig(serverUrl, token)
      else this._api = new ApiClient(serverUrl, token)

      if (this._running) {
        this.disconnectSSE()
        this.connectSSE(serverUrl, token)
        this.requestSync('config-change').catch(e => console.error('[SyncWorker] config change pull failed:', e))
      } else {
        this.start()
        this.connectSSE(serverUrl, token)
      }
    }
  }

  /** 绑定数据库和 API 客户端 */
  bind(api: ApiClient, db: Database): void {
    if (this._identityKey && (db as any).getConfig?.('account_identity_key') !== this._identityKey) {
      this._api = null; this._db = null; this._queue.clear(); return
    }
    this._api = api
    this._db = db
    db.setEnqueue((table, id) => this.enqueue(table, id as number))
  }

  /** 非阻塞入队 */
  enqueue(table: string, recordId: number): void {
    if (this._pausedForReset) return
    if (!this._queue.has(table)) this._queue.set(table, new Set())
    this._queue.get(table)!.add(recordId)
  }

  /** 启动后台同步 */
  start(): void {
    if (this._running) return
    if (!this._recoveredInterruptedSending) {
      ;(this._db as any)?.recoverInterruptedOutboxSending?.()
      this._recoveredInterruptedSending = true
    }
    this._running = true

    this.requestSync('worker-startup').catch(e => console.error('[SyncWorker] startup push/pull failed:', e))
  }



  /** 停止 */
  stop(): void {
    this._running = false
    this._flush(this._createContext('worker-stop')).catch(() => {})
  }

  /** 数据清空期间硬暂停同步，包含定时器、SSE 触发和手动 flush/pull */
  pauseForReset(): void {
    this._pausedForReset = true
    this._running = false
    this._queue.clear()
  }

  /** 数据清空完成后恢复同步 */
  resumeFromReset(): void {
    this._pausedForReset = false
    this.start()
  }

  // ======================== Push ========================

  /** 仅执行本地变更推送（UI 手动触发使用） */
  async pushOnly(context: SyncRunContext = {}): Promise<{ ok: boolean, merged: number, pending: number, statsStr?: string, error?: string }> {
    if (!context.syncRunId) context.syncRunId = this._createContext('pushOnly').syncRunId
    
    if (this._pausedForReset) return { ok: true, merged: 0, pending: 0 }
    if (!this._identityReady()) return { ok: false, merged: 0, pending: 0, error: 'account_identity_mismatch' }

    const pendingOutboxCount = (this._db as any).getPendingOutbox?.(1)?.length ?? 0
    if (pendingOutboxCount === 0) {
      console.info('[SyncWorker] pushOnly skipped: pending=0')
      return { ok: true, merged: 0, pending: 0 }
    }

    console.info('[SyncWorker] pushOnly start', {
      sync_run_id: context.syncRunId,
      reason: context.reason,
      pending_outbox: pendingOutboxCount,
    })

    const result = await this._flushOutbox(context)
    
    const remainingCount = (this._db as any).getPendingOutbox?.(1)?.length ?? 0
    return { ok: result.ok, merged: pendingOutboxCount - remainingCount, pending: remainingCount, statsStr: result.statsStr, error: result.error }
  }

  private async _flush(context: SyncRunContext = {}): Promise<PushResult> {
    if (this._pausedForReset) return { ok: true }
    if (!this._identityReady()) return { ok: false, error: 'account_identity_mismatch' }

    const pendingOutboxCount = (this._db as any).getPendingOutbox?.(1)?.length ?? 0
    if (pendingOutboxCount === 0) return { ok: true }

    console.info('[SyncWorker] push start', {
      sync_run_id: context.syncRunId,
      reason: context.reason,
      pending_outbox: pendingOutboxCount,
    })

    const result = await this._flushOutbox(context)
    return result
  }

  private async _flushOutbox(context: SyncRunContext = {}): Promise<PushResult> {
    if (!this._api || !this._db) return { ok: false, error: 'sync_worker_not_ready' }
    const entries = (this._db as any).getPendingOutbox?.(50) ?? []
    if (entries.length === 0) return { ok: true }

    const ignoredIds: number[] = []
    const blockedTaskIds: number[] = []
    const deferredProviderIds: number[] = []
    const scope = this._syncScope(context)
    console.info('[SyncWorker] outbox push start', {
      sync_run_id: context.syncRunId,
      count: entries.length,
      tables: [...new Set(entries.map((entry: any) => entry.table_name))],
    })
    const operations = entries.flatMap((entry: any) => {
      let payload: Record<string, any> = {}
      try {
        payload = JSON.parse(entry.payload_json || '{}')
      } catch {
        payload = {}
      }
      if (scope === 'core' && ['tasks', 'habits'].includes(entry.table_name) && String(payload.source || 'ticktick') !== 'local') {
        deferredProviderIds.push(entry.id)
        return []
      }
      if (SYNC_TABLES.includes(entry.table_name) && isServerOwnedTable(entry.table_name)) {
        // Clear legacy local writes without ever letting them overwrite server facts.
        ignoredIds.push(entry.id)
        return []
      }
      if (isBlockedSyncConfig(entry.table_name, payload)) {
        ignoredIds.push(entry.id)
        return []
      }
      if (entry.table_name === 'tasks' && (
        entry.operation === 'delete' || entry.operation === 'archive' || String(payload.id || entry.record_id || '').startsWith('local_')
      )) {
        blockedTaskIds.push(entry.id)
        return []
      }
      return [{
        change_id: entry.change_id,
        device_id: entry.device_id,
        table: entry.table_name,
        record_id: entry.record_id,
        operation: entry.operation,
        base_version: entry.base_version,
        payload: payload,
      }]
    })
    const ids = entries.filter((entry: any) => !ignoredIds.includes(entry.id) && !blockedTaskIds.includes(entry.id) && !deferredProviderIds.includes(entry.id)).map((entry: any) => entry.id)
    if (ignoredIds.length) (this._db as any).markOutboxSynced?.(ignoredIds, this._now())
    if (blockedTaskIds.length) (this._db as any).markOutboxFailed?.(blockedTaskIds, 'task_structure_requires_command')
    if (operations.length === 0) return { ok: true, diagnostics: {
      scope, provider_requested: deferredProviderIds.length > 0, provider_executed: false, provider_blocked: deferredProviderIds.length,
    } }
    ;(this._db as any).markOutboxSending?.(ids)

    const resp = await this._api.post(SYNC_CONFIG.api.push, {
      operations,
      client_time: this._now(),
      sync_scope: scope,
    }, SYNC_CONFIG.timeout.push, context.syncRunId)
    this._emitAuthState(resp.status)

    if (resp.ok && resp.data?.status === 'ok') {
      const serverTime = resp.data.server_time ?? this._now()
      const results = Array.isArray(resp.data.operation_results) ? resp.data.operation_results : []
      const responseDiagnostics = {
        ...(resp.data.diagnostics || { scope, provider_requested: false, provider_executed: false }),
        request_id: resp.request_id ?? context.syncRunId,
      }
      if (results.length === 0) {
        ;(this._db as any).markOutboxSynced?.(ids, serverTime)
        this._db.setConfig('client_to_server_synced_at', serverTime)
        return { ok: true, diagnostics: responseDiagnostics, operationResults: operations.map((operation: any) => ({ ...operation, status: 'accepted' })) }
      }

      let statsStr = ''
      const tableCounts: Record<string, number> = {}
      for (const res of results) {
        if (['accepted', 'duplicate', 'skipped'].includes(res.status) && res.table) {
          tableCounts[res.table] = (tableCounts[res.table] || 0) + 1
        }
      }
      const parts = Object.entries(tableCounts).map(([k, v]) => {
        if (k === 'tasks') return `task ${v}`
        if (k === 'habit_checkins') return `habit ${v}`
        return `${k} ${v}`
      })
      if (parts.length > 0) {
        statsStr = parts.join(', ')
      }
      const byChangeId = new Map<string, any>(entries.map((entry: any) => [entry.change_id, entry]))
      const acceptedIds: number[] = []
      const failed: { id: number; reason: string }[] = []
      for (const result of results) {
        const entry = byChangeId.get(result.change_id)
        if (!entry) continue
        if (['accepted', 'duplicate', 'skipped'].includes(result.status)) {
          try {
            if (entry.table_name === 'categories' && result.record_id != null) {
              const localId = Number(entry.record_id); const serverId = Number(result.record_id)
              if (Number.isSafeInteger(localId) && Number.isSafeInteger(serverId) && localId !== serverId) {
                ;(this._db as any).rekeyCategoryId?.(localId, serverId)
              }
            }
            acceptedIds.push(entry.id as number)
          } catch (error) {
            failed.push({ id: entry.id as number, reason: error instanceof Error ? error.message : 'category_id_rekey_failed' })
          }
        } else if (result.status === 'rejected' && String(result.reason || '').startsWith('server_owned_')) {
          acceptedIds.push(entry.id as number)
        } else {
          failed.push({ id: entry.id as number, reason: result.reason || 'operation_rejected' })
        }
      }
      if (acceptedIds.length > 0) {
        ;(this._db as any).markOutboxSynced?.(acceptedIds, serverTime)
      }
      for (const item of failed) {
        ;(this._db as any).markOutboxFailed?.([item.id], item.reason)
      }
      this._db.setConfig('client_to_server_synced_at', serverTime)
      console.info('[SyncWorker] outbox push ok', {
        sync_run_id: context.syncRunId,
        accepted: acceptedIds.length,
        failed: failed.length,
      })
      if (failed.length > 0) {
        const error = failed[0].reason || 'operation_rejected'
        return { ok: false, statsStr, error, diagnostics: responseDiagnostics, operationResults: results }
      }
      return { ok: true, statsStr, diagnostics: responseDiagnostics, operationResults: results }
    }

    const error = resp.error || resp.data?.error || 'push_failed'
    ;(this._db as any).markOutboxFailed?.(ids, error)
    console.warn(`[SyncWorker] outbox push failed sync_run_id=${context.syncRunId || ''} count=${ids.length} error=${error}`)
    return {
      ok: false,
      error,
      diagnostics: {
        scope,
        provider_requested: false,
        provider_executed: false,
        request_id: resp.request_id ?? context.syncRunId,
        http_status: resp.status,
      },
      operationResults: [],
    }
  }

  // ======================== Pull ========================

  async pullAndMergeResult(refresh = false, context: SyncRunContext = {}): Promise<SyncRunResult> {
    if (this._pausedForReset) return { ok: true, merged: 0 }
    if (!this._api || !this._db) return { ok: false, merged: 0, error: 'sync_worker_not_ready' }
    if (context.ledgerExpectation && this._pullInFlight) {
      await this._pullInFlight.catch(() => {})
      return this.pullAndMergeResult(refresh, context)
    }
    if (!refresh && !context.ledgerExpectation && !this._requiresAuthoritativePull(context.reason)) {
      if (this._pullInFlight) {
        console.debug('[SyncWorker] pull skipped', {
          sync_run_id: context.syncRunId,
          reason: context.reason,
          skipped_by: 'in_flight',
        })
        return this._pullInFlight
      }
      const now = Date.now()
      if (now - this._lastPassivePullAt < SYNC_CONFIG.dedupe.passivePullMs) {
        console.debug('[SyncWorker] pull skipped', {
          sync_run_id: context.syncRunId,
          reason: context.reason,
          skipped_by: 'dedupe_window',
          elapsed_ms: now - this._lastPassivePullAt,
        })
        return {
          ok: true,
          merged: 0,
          diagnostics: {
            skipped: true,
            reason: 'dedupe_window',
            client_elapsed_ms: 0,
          },
        }
      }
    }

    const run = this._pullAndMergeResult(refresh, context)
    if (refresh) return run
    this._pullInFlight = run
    try {
      const result = await run
      if (result.ok) this._lastPassivePullAt = Date.now()
      return result
    } finally {
      this._pullInFlight = null
    }
  }

  /** 只拉取服务端权威时间记录，不推送 Outbox、读取计时状态或刷新第三方服务。 */
  async pullSessionVisibility(context: SyncRunContext = this._createContext('session-visibility')): Promise<SyncRunResult> {
    if (this._sessionVisibilityPullInFlight) return this._sessionVisibilityPullInFlight
    const run = this._pullSessionVisibility(context)
    this._sessionVisibilityPullInFlight = run
    try {
      return await run
    } finally {
      this._sessionVisibilityPullInFlight = null
    }
  }

  private async _pullSessionVisibility(context: SyncRunContext): Promise<SyncRunResult> {
    this._logSync('info', { event: 'session_visibility_pull_start', sync_run_id: context.syncRunId, stage: 'pull' })
    if (this._syncInFlight) {
      return await this._syncInFlight
    }
    if (this._pullInFlight) return await this._pullInFlight
    const result = await this.pullAndMergeResult(false, context)
    this._logSync('info', {
      event: 'session_visibility_pull_finish', sync_run_id: context.syncRunId,
      stage: 'pull', merged: result.merged, elapsed_ms: result.diagnostics?.client_elapsed_ms,
    })
    return result
  }

  private async _pullAndMergeResult(refresh = false, context: SyncRunContext = {}): Promise<SyncRunResult> {
    const startedAt = Date.now()
    if (!this._api || !this._db) return { ok: false, merged: 0, error: 'sync_worker_not_ready' }

    const lastServerVersion = (this._db as any).getLastServerVersion?.()
    const forceLegacySync = this._db.getConfig('sync_protocol') === 'legacy_timestamp'
    const useVersionPull = !forceLegacySync && typeof lastServerVersion === 'number' && lastServerVersion >= 0
    const lastSync = this._db.getConfig('server_to_client_synced_at') || this._db.getConfig('last_sync_at')
    const params: Record<string, string> = {}
    const scope = this._syncScope(context)
    params.sync_scope = scope
    if (useVersionPull) params.since_version = String(lastServerVersion)
    else if (lastSync && !refresh) params.since = lastSync
    if (refresh) params.refresh = 'true'
    if (scope === 'checklist' && context.reason === 'checklist-refresh') params.provider_manual = 'true'
    const snapshotVersion = (this._db as any).getLedgerSnapshotVersion?.()
    const snapshotConsistent = (this._db as any).hasConsistentLedgerSnapshot?.() === true
    if (useVersionPull && (refresh || Boolean(context.ledgerExpectation) || Boolean(context.walletReconcileAttempt) || typeof snapshotVersion !== 'number' || snapshotVersion <= 0 || !snapshotConsistent)) params.ledger_snapshot = 'true'

    console.info('[SyncWorker] pull start', {
      sync_run_id: context.syncRunId,
      reason: context.reason,
      scope,
      refresh,
      protocol: useVersionPull ? 'server_version' : 'legacy_timestamp',
      since_version: params.since_version,
      since: params.since,
      last_server_version: lastServerVersion,
    })
    const timeoutMs = refresh ? SYNC_CONFIG.timeout.refresh : SYNC_CONFIG.timeout.pull
    let retry = 0
    let resp = await this._api.get(SYNC_CONFIG.api.pull, params, timeoutMs, context.syncRunId)
    if (!resp.ok && resp.status === 0 && ['request_timeout', 'server_unreachable'].includes(String(resp.error))) {
      retry = 1
      await new Promise(resolve => setTimeout(resolve, 20 + Math.floor(Math.random() * 30)))
      resp = await this._api.get(SYNC_CONFIG.api.pull, params, timeoutMs, context.syncRunId)
    }
    this._emitAuthState(resp.status)
    if (!resp.ok || resp.data?.status !== 'ok') {
      const error = resp.error || resp.data?.error || 'pull_failed'
      console.warn('[SyncWorker] pull failed', {
        sync_run_id: context.syncRunId,
        error,
        stage: 'pull',
        http_status: resp.status,
      })
      return {
        ok: false,
        merged: 0,
        diagnostics: {
          ...(resp.data?.diagnostics || {}),
          stage: 'pull',
          http_status: resp.status,
          request_id: resp.request_id ?? context.syncRunId,
        },
        error,
      }
    }

    const rawTables = { ...(resp.data.tables ?? {}) }
    const ledgerSnapshot = resp.data.ledger_snapshot
    if (ledgerSnapshot) delete rawTables.reward_ledger
    const naturalMerge = this._deduplicateNaturalKeyRows(rawTables)
    const tables = naturalMerge.tables
    const serverTime = resp.data.server_time ?? this._now()
    const diagnostics = { ...(resp.data.diagnostics || {}) }
    diagnostics.retry = retry
    diagnostics.scope = diagnostics.scope || scope
    diagnostics.request_id = resp.request_id ?? context.syncRunId
    diagnostics.provider_requested = diagnostics.provider_requested ?? (scope === 'checklist' && refresh)
    diagnostics.provider_executed = diagnostics.provider_executed ?? false
    if (typeof resp.data.from_version === 'number') diagnostics.from_version = resp.data.from_version
    if (typeof resp.data.to_version === 'number') diagnostics.to_version = resp.data.to_version
    diagnostics.has_more = resp.data.has_more === true
    if (Object.keys(naturalMerge.duplicates).length > 0) diagnostics.natural_key_duplicates = naturalMerge.duplicates
    let merged = 0
    let walletChanged = false
    const mergeErrors: string[] = []
    const skipped: string[] = []
    const conflicts: string[] = []
    let bulkFailures: SafeBulkFailure[] = []
    const bulk = (this._db as any).androidBulk as AndroidBulkCapability | undefined
    if (ledgerSnapshot) {
      try {
        const replace = (this._db as any).replaceServerLedgerSnapshot
        if (typeof replace !== 'function') throw new Error('ledger_snapshot_unsupported')
        const before = this._db.getLedgerSummary?.()
        const result = replace.call(this._db, ledgerSnapshot, Number(resp.data.to_version ?? lastServerVersion))
        walletChanged = Number(before?.balance) !== Number(ledgerSnapshot.summary?.balance)
        diagnostics.ledger_snapshot = { applied: true, removed: result.removed, count: ledgerSnapshot.integrity?.count, epoch: ledgerSnapshot.epoch }
      } catch (error) {
        diagnostics.ledger_snapshot = { applied: false, error: error instanceof Error ? error.message : 'ledger_snapshot_failed' }
        diagnostics.cursor = { previous: lastServerVersion, next: lastServerVersion, advanced: false }
        return { ok: false, merged: 0, diagnostics, error: 'ledger_snapshot_failed' }
      }
    }
    if (bulk && this._lastBulkFailure && context.reason !== 'manual-flush') {
      const gate = this._bulkFailureGate.canAttempt(this._lastBulkFailure.fingerprint, Number(resp.data.to_version ?? -1))
      if (!gate.allowed) return { ok: false, merged: 0, diagnostics: { stage: 'backoff', retry_at: gate.retryAt }, error: 'local_merge_backoff' }
    }

    const schemaFailure = this._preflightMergeSchema(tables, bulk)
    if (schemaFailure) {
      const label = `${schemaFailure.table}:${schemaFailure.category}`
      bulkFailures = [schemaFailure]
      mergeErrors.push(label)
      diagnostics.merge = { applied: 0, failed: 1, errors: [label], skipped: [], conflicts: [], failure_details: bulkFailures }
      diagnostics.cursor = { previous: lastServerVersion, next: lastServerVersion, advanced: false }
      if (bulk) {
        const fingerprint = `${schemaFailure.table}:*:${schemaFailure.category}`
        const version = Number(resp.data.to_version ?? -1)
        diagnostics.merge.retry_at = this._bulkFailureGate.fail(fingerprint, version)
        this._lastBulkFailure = { fingerprint, version }
      }
      this._logSync('warn', { event: 'pull_merge_failed', sync_run_id: context.syncRunId,
        platform: bulk ? 'android' : 'pc', stage: 'merge', schema: 'required_columns', table: schemaFailure.table,
        record_id: '*', error_category: schemaFailure.category, columns: schemaFailure.columns,
        cursor: `${lastServerVersion}->${lastServerVersion}`, previous: lastServerVersion,
        from: diagnostics.from_version, to: diagnostics.to_version, next: lastServerVersion, advanced: false,
        retry_at: diagnostics.merge.retry_at, elapsed_ms: Date.now() - startedAt, merged: 0 })
      return { ok: false, merged: 0, diagnostics, error: 'local_merge_failed' }
    }

    const resetRows = (tables.system_config ?? []).filter((row: any) =>
      row.key === 'checklist_ticktick_reset_marker' && String(row._sync_operation || row.operation || '') !== 'delete')
    const resetMarker = resetRows[resetRows.length - 1]?.value
    if (resetMarker != null) {
      const localReset = (this._db as any).applyChecklistResetMarker?.(String(resetMarker))
      if (localReset?.applied) this._logSync('info', {
        event: 'local_checklist_reset', sync_run_id: context.syncRunId, stage: 'merge', ...localReset,
      })
    }

    // 应用云端下发的钱包余额快照
    if (!ledgerSnapshot && resp.data.wallet && resp.data.wallet.balance !== undefined) {
      const nextBalance = String(resp.data.wallet.balance)
      walletChanged = this._db.getConfig('wallet_balance') !== nextBalance
      this._db.setConfig('wallet_balance', nextBalance);
    }

    if ((tables.categories ?? []).length > 0) this._alignPulledCategoryIds(tables.categories)
    if (bulk) {
      const result = await this._mergeBulkTables(bulk, tables, serverTime, context)
      merged += result.merged
      walletChanged = walletChanged || result.walletChanged
      mergeErrors.push(...result.errors)
      skipped.push(...result.skipped)
      conflicts.push(...result.conflicts)
      bulkFailures = result.failures
    } else for (const { table, rows: serverRows } of this._mergeTableStages(tables)) {
      for (const sRow of serverRows) {
        const pk = localLookupKeyForTable(table)
        const primaryKey = primaryKeyForTable(table)
        let opId = sRow[pk]
        let recordLabel = String(opId)
        recordLabel = opId == null ? String(sRow.id ?? '') : String(opId)

        if (opId == null) continue

        const localMatch = this._findLocalMergeRow(table, sRow, pk)
        const local = localMatch.row

        const serverOwned = isServerOwnedTable(table)
        const outboxId = local?.id != null ? local.id : opId
        const hasPendingOutbox = !serverOwned && (
          Boolean((this._db as any).hasPendingOutbox?.(table, opId)) ||
          Boolean(outboxId !== opId && (this._db as any).hasPendingOutbox?.(table, outboxId))
        )
        const action = serverOwned ? SyncAction.PULL : resolve(local ?? null, sRow, hasPendingOutbox)

        if (action === SyncAction.PULL) {
          if (primaryKey !== 'id' || pk !== 'id') {
            if (table === 'user_wallets') delete sRow.id
            else if (local) sRow.id = local.id
            else delete sRow.id
          } else if (localMatch.naturalKey && local) {
            sRow[primaryKey] = local[primaryKey]
          }
          if (table === 'user_wallets' && sRow.balance !== undefined) {
            walletChanged = walletChanged || this._db.getConfig('wallet_balance') !== String(sRow.balance)
          }
          if (table === 'habit_checkins' && String(sRow._sync_operation || sRow.operation || '') !== 'delete') {
            const parentHabitId = sRow.habit_id
            const parentExists = parentHabitId != null && Boolean(this._db.getRecordById('habits', parentHabitId))
            if (!parentExists) {
              const missingParentLabel = `${table}:${recordLabel}:missing_parent`
              console.warn('[SyncWorker] defer habit_checkins missing parent habit', {
                sync_run_id: context.syncRunId,
                table,
                record_id: recordLabel,
                habit_id: parentHabitId,
                checkin_date: sRow.checkin_date,
                reason: 'missing_parent',
              })
              mergeErrors.push(missingParentLabel)
              skipped.push(missingParentLabel)
              continue
            }
          }
          const failureCategory = this._upsertLocal(table, sRow, serverTime, local?.pushed_at)
          if (!failureCategory) merged++
          else {
            bulkFailures.push({ table, recordId: recordLabel, category: failureCategory })
            mergeErrors.push(`${table}:${recordLabel}:${failureCategory}`)
          }
        } else if (action === SyncAction.PUSH) {
          conflicts.push(`${table}:${recordLabel}`)
        }
      }
    }
    if ((tables.categories ?? []).length > 0) this._db.normalizeDuplicateCategories()
    diagnostics.merge = {
      applied: merged,
      failed: mergeErrors.length,
      errors: mergeErrors,
      skipped,
      conflicts,
      failure_details: bulkFailures,
    }
    if (bulk && bulkFailures.length) {
      const first = bulkFailures[0]; const fingerprint = `${first.table}:${first.recordId}:${first.category}`
      const version = Number(resp.data.to_version ?? -1); const retryAt = this._bulkFailureGate.fail(fingerprint, version)
      this._lastBulkFailure = { fingerprint, version }; diagnostics.merge.retry_at = retryAt
    } else if (bulk && mergeErrors.length === 0) { this._bulkFailureGate.succeed(); this._lastBulkFailure = null }
    const mergeSucceeded = mergeErrors.length === 0 && conflicts.length === 0
    const expectation = context.ledgerExpectation
    const expectedRows = ledgerSnapshot?.rows ?? tables.reward_ledger ?? []
    const expectedLedgerConfirmed = !expectation || Boolean((expectedRows as any[]).some(row =>
      String(row?.source_type || '') === expectation.sourceType && String(row?.target_date || '').slice(0, 10) === expectation.targetDate
    )) === expectation.exists
    if (expectation) diagnostics.ledger_expectation = {
      ...expectation,
      confirmed: expectedLedgerConfirmed,
      attempt: Number(context.ledgerConfirmationAttempt || 0),
    }
    if (mergeSucceeded && expectation && !expectedLedgerConfirmed) {
      diagnostics.cursor = { previous: lastServerVersion, next: lastServerVersion, advanced: false }
      if (Number(context.ledgerConfirmationAttempt || 0) < 1) {
        await new Promise(resolve => setTimeout(resolve, 120))
        return this._pullAndMergeResult(false, { ...context, ledgerConfirmationAttempt: Number(context.ledgerConfirmationAttempt || 0) + 1 })
      }
      return { ok: false, merged, diagnostics, error: 'ledger_confirmation_pending' }
    }
    const serverWalletBalance = Number(resp.data.wallet?.balance)
    const localLedgerBalance = Number(this._db.getLedgerSummary?.()?.balance)
    const walletMismatch = mergeSucceeded && resp.data.has_more !== true && Number.isFinite(serverWalletBalance)
      && Number.isFinite(localLedgerBalance) && Math.abs(localLedgerBalance - serverWalletBalance) > 0.000001
    if (walletMismatch) {
      diagnostics.wallet_reconciliation = { server_balance: serverWalletBalance, local_balance: localLedgerBalance,
        attempt: Number(context.walletReconcileAttempt || 0), confirmed: false }
      diagnostics.cursor = { previous: lastServerVersion, next: lastServerVersion, advanced: false }
      if (Number(context.walletReconcileAttempt || 0) < 1) {
        return this._pullAndMergeResult(false, { ...context, walletReconcileAttempt: 1 })
      }
      return { ok: false, merged, diagnostics, error: 'wallet_balance_mismatch' }
    }
    if (Number.isFinite(serverWalletBalance) && Number.isFinite(localLedgerBalance)) {
      diagnostics.wallet_reconciliation = { server_balance: serverWalletBalance, local_balance: localLedgerBalance, confirmed: true }
    }
    diagnostics.cursor = pullCursorDecision(lastServerVersion, resp.data.to_version, {
      versioned: useVersionPull,
      snapshot: resp.data.snapshot === true,
      succeeded: mergeSucceeded,
    })

    const applySyncState = () => {
      if (useVersionPull && typeof diagnostics.cursor.next === 'number') {
        ;(this._db as any).setLastServerVersion?.(diagnostics.cursor.next)
      }
      this._db!.setConfig('server_to_client_synced_at', serverTime)
      this._db!.setConfig('last_sync_at', serverTime)
    }
    if (mergeSucceeded) {
      if (typeof (this._db as any).runInTransaction === 'function') {
        ;(this._db as any).runInTransaction(applySyncState)
      } else {
        applySyncState()
      }
    }
    const syncState = resp.data.sync_state ?? {}
    if (syncState.server_to_ticktick_synced_at) {
      this._db.setConfig('server_to_ticktick_synced_at', syncState.server_to_ticktick_synced_at)
    }
    if (syncState.ticktick_to_server_synced_at) {
      this._db.setConfig('ticktick_to_server_synced_at', syncState.ticktick_to_server_synced_at)
    }
    this._emitSyncEvents(walletChanged)
    if (mergeErrors.length > 0) {
      const firstFailure = bulkFailures[0]
      this._logSync('warn', { event: 'pull_merge_failed', sync_run_id: context.syncRunId,
        platform: bulk ? 'android' : 'pc', stage: 'merge', schema: 'validated', table: firstFailure?.table,
        record_id: firstFailure?.recordId, error_category: firstFailure?.category || 'sqlite_operation_failed',
        cursor: `${diagnostics.cursor.previous}->${diagnostics.cursor.next}`, previous: diagnostics.cursor.previous,
        from: diagnostics.from_version, to: diagnostics.to_version, next: diagnostics.cursor.next,
        advanced: diagnostics.cursor.advanced, retry_at: diagnostics.merge.retry_at,
        elapsed_ms: Date.now() - startedAt, merged })
      return { ok: false, merged, diagnostics, error: 'local_merge_failed' }
    }
    if (conflicts.length > 0) {
      return { ok: false, merged, diagnostics, error: 'local_outbox_conflict' }
    }
    if (refresh && diagnostics && diagnostics.ok === false) {
      console.warn('[SyncWorker] provider refresh failed', {
        sync_run_id: context.syncRunId,
        merged,
        diagnostics,
      })
      return { ok: false, merged, diagnostics, error: diagnostics.errors?.[0] || 'ticktick_refresh_failed' }
    }
    if (resp.data.has_more === true) {
      const page = Number(context.page || 1)
      if (!diagnostics.cursor.advanced || page >= 20) {
        diagnostics.pagination = { page, advanced: diagnostics.cursor.advanced }
        return { ok: false, merged, diagnostics, error: 'invalid_pull_pagination' }
      }
      this._logSync('info', { event: 'pull_merge_page_ok', sync_run_id: context.syncRunId,
        platform: bulk ? 'android' : 'pc', stage: 'merge', previous: diagnostics.cursor.previous,
        next: diagnostics.cursor.next, advanced: true, elapsed_ms: Date.now() - startedAt, merged })
      const next = await this._pullAndMergeResult(false, { ...context, page: page + 1 })
      return {
        ...next,
        merged: merged + next.merged,
        diagnostics: { ...(next.diagnostics || {}), pages: 1 + Number(next.diagnostics?.pages || 1) },
      }
    }
    diagnostics.pages = 1
    this._logSync('info', { event: 'pull_merge_ok', sync_run_id: context.syncRunId,
      platform: bulk ? 'android' : 'pc', stage: 'merge', schema: 'validated',
      cursor: `${diagnostics.cursor.previous}->${diagnostics.cursor.next}`, previous: diagnostics.cursor.previous,
      from: diagnostics.from_version, to: diagnostics.to_version, next: diagnostics.cursor.next,
      advanced: diagnostics.cursor.advanced, elapsed_ms: Date.now() - startedAt, merged })
    return { ok: true, merged, diagnostics }
  }

  async pullAndMerge(refresh = false, context: SyncRunContext = this._createContext('manual-pull')): Promise<number> {
    const result = await this.pullAndMergeResult(refresh, context)
    return result.ok ? result.merged : 0
  }

  /** App、Network、SSE 与手动触发共用的 Push/Pull single-flight 入口。 */
  async requestSync(reason: string, refresh = false, context: SyncRunContext = this._createContext(reason)): Promise<SyncRunResult> {
    if (this._syncInFlight) {
      if (context.ledgerExpectation) {
        await this._syncInFlight.catch(() => {})
        return this.requestSync(reason, refresh, context)
      }
      if (this._syncScope(context) === 'checklist') {
        await this._syncInFlight
        return this.requestSync(reason, refresh, context)
      }
      if (this._requiresAuthoritativePull(reason)) this._syncRerunRequested = true
      if (reason === 'user-action') this._syncRerunActionRequested = true
      return this._syncInFlight
    }
    let result: SyncRunResult
    let firstRun = true
    do {
      const rerunAction = !firstRun && this._syncRerunActionRequested
      this._syncRerunRequested = false
      this._syncRerunActionRequested = false
      const run = firstRun
        ? this._flushNow(refresh, context)
        : rerunAction
          ? this._flushNow(false, this._createContext('user-action-followup'))
          : this.pullAndMergeResult(false, this._createContext('sse-changed'))
      this._syncInFlight = run
      try { result = await run } finally { this._syncInFlight = null }
      firstRun = false
    } while (this._syncRerunRequested)
    return result!
  }

  /** 事件驱动立即推送 + 拉取（不等定时器），低时延同步 */
  async flushNow(refresh = false, context: SyncRunContext = {}): Promise<SyncRunResult> {
    const reason = context.reason || 'manual-flush'
    const completeContext = context.syncRunId
      ? context
      : {
          ...this._createContext(reason),
          ...context,
          reason,
          scope: context.scope || 'core',
        }
    return this.requestSync(reason, refresh, completeContext)
  }

  private async _flushNow(refresh = false, context: SyncRunContext = {}): Promise<SyncRunResult> {
    if (this._pausedForReset) return { ok: true, merged: 0 }
    const pushed = await this._flush(context)
    if (!pushed.ok) {
      const pulled = await this._pullAndMergeResult(refresh, context)
      return {
        ...pulled,
        diagnostics: {
          ...(pulled.diagnostics || {}),
          sync_run_id: context.syncRunId,
          reason: context.reason,
          push: {
            ok: false,
            stage: 'push',
            error: pushed.error || 'push_failed',
            ...(pushed.diagnostics || {}),
            operation_results: pushed.operationResults || [],
          },
        },
        error: pulled.ok ? pulled.error : (pulled.error || pushed.error || 'sync_failed'),
      }
    }
    const pulled = await this.pullAndMergeResult(refresh, context)
    return {
      ...pulled,
      diagnostics: {
        ...(pulled.diagnostics || {}),
        provider_requested: Boolean(pulled.diagnostics?.provider_requested || pushed.diagnostics?.provider_requested),
        provider_executed: Boolean(pulled.diagnostics?.provider_executed || pushed.diagnostics?.provider_executed),
        push: { ok: true, stage: 'push', ...(pushed.diagnostics || {}), operation_results: pushed.operationResults || [] },
      },
    }
  }

  // ======================== 工具 ========================

  private _preflightMergeSchema(tables: Record<string, any[]>, bulk?: AndroidBulkCapability): SafeBulkFailure | null {
    for (const table of SYNC_TABLES) {
      if ((tables[table] ?? []).length === 0) continue
      const check = validateMergeSchema(this._mergeTableColumns(table, bulk), [primaryKeyForTable(table), 'pulled_at'])
      if (!check.ok) return { table, recordId: '*', category: check.error, columns: check.missingColumns }
    }
    return null
  }

  private _mergeTableStages(tables: Record<string, any[]>): Array<{ table: string; rows: any[] }> {
    const orderedTables = ['categories', ...SYNC_TABLES.filter(table => table !== 'categories')]
    const parentIndex = orderedTables.indexOf('habits')
    const deleted = (row: any) => String(row._sync_operation || row.operation || '') === 'delete'
    const phase = (table: string, wantDeleted: boolean) => ({ table, rows: (tables[table] ?? []).filter(row => deleted(row) === wantDeleted) })
    return [
      ...orderedTables.slice(0, parentIndex).map(table => ({ table, rows: tables[table] ?? [] })),
      phase('habit_checkins', true), phase('habits', true), phase('habits', false), phase('habit_checkins', false),
      ...orderedTables.slice(parentIndex + 2).map(table => ({ table, rows: tables[table] ?? [] })),
    ].filter(({ rows }) => rows.length > 0)
  }

  private _deduplicateNaturalKeyRows(tables: Record<string, any[]>): { tables: Record<string, any[]>; duplicates: Record<string, number> } {
    const result = { ...tables }; const duplicates: Record<string, number> = {}
    for (const [table, rows] of Object.entries(tables)) {
      const naturalKeys = naturalKeysForTable(table)
      if (naturalKeys.length === 0 || rows.length < 2) continue
      const winners = new Map<string, any>(); const passthrough: any[] = []
      for (const row of rows) {
        const operation = String(row._sync_operation || row.operation || '')
        const key = operation === 'delete' ? null : naturalKeyForRecord(table, row)
        if (!key) { passthrough.push(row); continue }
        const previous = winners.get(key)
        if (!previous) winners.set(key, row)
        else {
          duplicates[table] = (duplicates[table] || 0) + 1
          if (this._compareNaturalKeyRows(row, previous) < 0) winners.set(key, row)
        }
      }
      result[table] = [...passthrough, ...winners.values()]
    }
    return { tables: result, duplicates }
  }

  private _compareNaturalKeyRows(left: Record<string, any>, right: Record<string, any>): number {
    const leftTime = Date.parse(String(left.updated_at || '')); const rightTime = Date.parse(String(right.updated_at || ''))
    if (leftTime !== rightTime) return leftTime > rightTime ? -1 : 1
    return String(left.id ?? '').localeCompare(String(right.id ?? ''))
  }

  private _alignPulledCategoryIds(records: Record<string, any>[]): void {
    const db = this._db as any
      if (!db?.allRaw || !db?.rekeyCategoryId) return
    const canonical = (name: any) => CATEGORY_NAME_ALIASES[String(name || '').trim()] || String(name || '').trim()
    const incoming = records.filter(row => String(row._sync_operation || row.operation || '') !== 'delete'
      && Number.isSafeInteger(Number(row.id)) && canonical(row.name))
    const localRows = db.allRaw('SELECT id,name,is_active FROM categories') as Array<{ id: number; name: string; is_active: number }>
    const localByName = new Map(
      localRows.filter(row => Number(row.is_active) === 1).map(row => [canonical(row.name), row]),
    )
    const moves = incoming.map(row => ({ localId: Number(localByName.get(canonical(row.name))?.id), serverId: Number(row.id) }))
      .filter(move => Number.isSafeInteger(move.localId) && move.localId > 0 && move.localId !== move.serverId)
    if (!moves.length) return
    const movingSources = new Set(moves.map(move => move.localId))
    const occupied = new Map(localRows.map(row => [Number(row.id), row]))
    let spareId = Math.max(0, ...localRows.map(row => Number(row.id)), ...incoming.map(row => Number(row.id))) + 1
      const rekeySteps: Array<{ localId: number; serverId: number }> = []
      for (const move of moves) {
        const blocker = occupied.get(move.serverId)
        if (blocker && !movingSources.has(Number(blocker.id))) rekeySteps.push({ localId: Number(blocker.id), serverId: spareId++ })
      }
      const staged = moves.map(move => {
        const temporaryId = spareId++
        rekeySteps.push({ localId: move.localId, serverId: temporaryId })
        return { temporaryId, serverId: move.serverId }
      })
      staged.forEach(move => rekeySteps.push({ localId: move.temporaryId, serverId: move.serverId }))
      if (typeof db.rekeyCategoryIds === 'function') db.rekeyCategoryIds(rekeySteps)
      else rekeySteps.forEach(move => db.rekeyCategoryId(move.localId, move.serverId))
  }

  private _findLocalMergeRow(table: string, source: Record<string, any>, lookupKey: string): { row: Record<string, any> | null; naturalKey: string | null } {
    const naturalKeys = naturalKeysForTable(table); const naturalKey = naturalKeyForRecord(table, source)
    if (naturalKey && typeof (this._db as any)?.allRaw === 'function') {
      try {
        const where = naturalKeys.map(key => `${key} = ?`).join(' AND ')
        const rows = (this._db as any).allRaw(`SELECT * FROM ${table} WHERE ${where}`, naturalKeys.map(key => source[key]))
        if (rows[0]) return { row: rows[0], naturalKey }
      } catch { /* schema preflight will report missing columns; use the primary-key fallback here */ }
    }
    const opId = source[lookupKey]
    if (opId == null) return { row: null, naturalKey }
    const row = lookupKey === 'id' ? this._db!.getRecordById(table, opId) : (this._db as any).getRecordByUnique(table, lookupKey, opId)
    return { row: row ?? null, naturalKey }
  }

  private _mergeTableColumns(table: string, bulk?: AndroidBulkCapability): Set<string> | null {
    if (bulk) return this._bulkTableColumns(bulk, table)
    if (typeof (this._db as any)?.allRaw !== 'function') return null
    let columns = this._localColumns.get(table)
    if (!columns) {
      columns = new Set((this._db as any).allRaw(`PRAGMA table_info(${table})`).map((column: any) => String(column.name)))
      this._localColumns.set(table, columns)
    }
    return columns
  }

  private async _mergeBulkTables(bulk: AndroidBulkCapability, tables: Record<string, any[]>, serverTime: string, _context: SyncRunContext): Promise<BulkMergeSummary> {
    const result: BulkMergeSummary = { merged: 0, walletChanged: false, errors: [], skipped: [], conflicts: [], failures: [] }
    for (const { table, rows } of this._mergeTableStages(tables)) {
      const lookupKey = localLookupKeyForTable(table); const primaryKey = primaryKeyForTable(table)
      const columns = this._bulkTableColumns(bulk, table)
      const pending = new Set(bulk.query("SELECT record_id FROM sync_outbox WHERE table_name = ? AND status IN ('pending','failed','sending')", [table]).map(row => String(row.record_id)))
      for (let offset = 0; offset < rows.length; offset += 100) {
        const batch = rows.slice(offset, offset + 100).filter(row => row[lookupKey] != null)
        const locals = this._bulkLocalRows(bulk, table, lookupKey, batch.map(row => row[lookupKey]))
        const naturalLocals = this._bulkLocalRowsByNaturalKeys(bulk, table, batch)
        const parentIds = table === 'habit_checkins' ? [...new Set(batch.map(row => row.habit_id).filter((id: any) => id != null))] : []
        const parents = parentIds.length ? this._bulkLocalRows(bulk, 'habits', 'id', parentIds) : new Map()
        const plans = planBulkMerge(batch.map(source => {
          const server = { ...source }; const naturalKey = naturalKeyForRecord(table, server)
          const local = (naturalKey ? naturalLocals.get(naturalKey) : locals.get(String(server[lookupKey]))) ?? null
          if (primaryKey !== 'id' || lookupKey !== 'id' || (naturalKey && local)) {
            if (table === 'user_wallets') delete server.id
            else if (local) server.id = local.id
            else delete server.id
          }
          const outboxId = local?.id != null ? local.id : server[lookupKey]
          return { local, server, serverOwned: isServerOwnedTable(table), hasPendingOutbox: pending.has(String(server[lookupKey])) || pending.has(String(outboxId)) }
        }))
        const operations: AndroidBulkOperation[] = []; const wallets: string[] = []
        for (const plan of plans) {
          const label = `${table}:${String(plan.server[lookupKey] ?? '')}`
          if (plan.action === SyncAction.PUSH) { result.conflicts.push(label); continue }
          if (plan.action !== SyncAction.PULL) continue
          if (table === 'habit_checkins'
            && String(plan.server._sync_operation || plan.server.operation || '') !== 'delete'
            && !parents.has(String(plan.server.habit_id))) {
            result.errors.push(`${label}:missing_parent`); result.skipped.push(`${label}:missing_parent`)
            result.failures.push({ table, recordId: String(plan.server[lookupKey]), category: 'missing_parent' }); continue
          }
          if (table === 'habits' && String(plan.server._sync_operation || plan.server.operation || '') === 'delete') {
            const childIds = bulk.query('SELECT id FROM habit_checkins WHERE habit_id = ?', [plan.server[primaryKey]])
              .map(child => String(child.id))
            if (childIds.some(id => bulk.query("SELECT 1 FROM sync_outbox WHERE table_name = ? AND record_id = ? AND status IN ('pending','failed','sending') LIMIT 1", ['habit_checkins', id]).length > 0)) {
              result.errors.push(`${label}:pending_child_conflict`); result.failures.push({ table, recordId: String(plan.server[lookupKey]), category: 'pending_child_conflict' }); continue
            }
            operations.push(...childIds.map(id => ({ sql: 'DELETE FROM habit_checkins WHERE id = ?', params: [id], internal: true })))
          }
          const operation = this._bulkOperation(table, plan.server, serverTime, plan.local?.pushed_at, columns)
          if (!operation) { result.errors.push(label); result.failures.push({ table, recordId: String(plan.server[lookupKey]), category: 'invalid_operation' }); continue }
          operations.push(operation)
          if (table === 'user_wallets' && plan.server.balance !== undefined) wallets.push(String(plan.server.balance))
        }
        if (operations.length) {
          const outcome = await applyBulkWithIsolation(operations, group => bulk.transaction(group))
          result.merged += outcome.applied - operations.filter(operation => operation.internal).length; result.failures.push(...outcome.failures)
          result.errors.push(...outcome.failures.map(failure => `${failure.table}:${failure.recordId}:${failure.category}`))
          if (outcome.failures.length === 0) for (const balance of wallets) { result.walletChanged ||= this._db!.getConfig('wallet_balance') !== balance; this._db!.setConfig('wallet_balance', balance) }
        }
        await bulk.yieldToUi()
      }
    }
    return result
  }

  private _bulkTableColumns(bulk: AndroidBulkCapability, table: string): Set<string> {
    let columns = this._bulkColumns.get(table)
    if (!columns) {
      columns = new Set(bulk.query(`PRAGMA table_info(${table})`).map(column => String(column.name)))
      this._bulkColumns.set(table, columns)
    }
    return columns
  }

  private _bulkLocalRows(bulk: AndroidBulkCapability, table: string, key: string, ids: any[]): Map<string, Record<string, any>> {
    if (ids.length === 0) return new Map()
    const placeholders = ids.map(() => '?').join(',')
    return new Map(bulk.query(`SELECT * FROM ${table} WHERE ${key} IN (${placeholders})`, ids)
      .map(row => [String(row[key]), row]))
  }

  private _bulkLocalRowsByNaturalKeys(bulk: AndroidBulkCapability, table: string, rows: Record<string, any>[]): Map<string, Record<string, any>> {
    const keys = naturalKeysForTable(table); const candidates = rows.filter(row => naturalKeyForRecord(table, row))
    if (keys.length === 0 || candidates.length === 0) return new Map()
    const clauses = candidates.map(() => `(${keys.map(key => `${key} = ?`).join(' AND ')})`).join(' OR ')
    const params = candidates.flatMap(row => keys.map(key => row[key]))
    try {
      return new Map(bulk.query(`SELECT * FROM ${table} WHERE ${clauses}`, params)
        .map(row => [naturalKeyForRecord(table, row) as string, row]))
    } catch { return new Map() }
  }

  private _bulkOperation(table: string, source: Record<string, any>, serverTime: string, pushedAt: any, columns: Set<string>): AndroidBulkOperation | null {
    const row = table === 'tasks' ? normalizeTaskTimeFields(source) : { ...source }
    if (table === 'exercise_daily_logs') Object.assign(row, {
      week_num: row.week_num ?? 1, day_name: row.day_name || row.exercise_type || 'daily',
      completed_items: row.completed_items ?? 0, total_items: row.total_items ?? 0,
      plan_version: row.plan_version || 'v0', created_at: row.created_at || this._now(),
    })
    const operation = String(row._sync_operation || row.operation || '')
    delete row._sync_operation
    const pk = primaryKeyForTable(table); const id = row[pk]
    if (operation === 'delete') return id == null ? null : { sql: `DELETE FROM ${table} WHERE ${pk} = ?`, params: [id], table, recordId: String(id) }
    if (table !== 'user_wallets') delete row.user_id
    for (const column of SERVER_INTERNAL_SYNC_COLUMNS[table] ?? []) delete row[column]
    if (table === 'categories' && !row.created_at) row.created_at = this._now()
    row.pulled_at = serverTime; row.pushed_at = pushedAt ?? null
    const filtered = filterMergePayload(row, columns).row
    const keys = Object.keys(filtered)
    const updates = keys.filter(key => key !== pk)
    const conflict = updates.length ? `DO UPDATE SET ${updates.map(key => `${key}=excluded.${key}`).join(', ')}` : 'DO NOTHING'
    return keys.length === 0 ? null : { sql: `INSERT INTO ${table} (${keys.join(', ')}) VALUES (${keys.map(() => '?').join(', ')}) ON CONFLICT(${pk}) ${conflict}`, params: keys.map(key => filtered[key]), table, recordId: String(id ?? '') }
  }

  private _upsertLocal(table: string, record: Record<string, any>, serverTime: string, pushedAt?: string | null): string | null {
    const row = table === 'tasks' ? normalizeTaskTimeFields(record) : { ...record }
    if (table === 'exercise_daily_logs') {
      row.week_num = row.week_num ?? 1
      row.day_name = row.day_name || row.exercise_type || 'daily'
      row.completed_items = row.completed_items ?? 0
      row.total_items = row.total_items ?? 0
      row.plan_version = row.plan_version || 'v0'
      row.created_at = row.created_at || this._now()
    }
    const operation = String(row._sync_operation || row.operation || '')
    delete row._sync_operation
    if (operation === 'delete') {
      const pk = primaryKeyForTable(table)
      const id = row[pk]
      if (id == null) return 'invalid_operation'
      if (table === 'habits') return this._deletePulledHabit(String(id))
      try {
        this._db!.runRaw(`DELETE FROM ${table} WHERE ${pk} = ?`, [id])
      } catch (error) {
        return this._localErrorCategory(error)
      }
      return null
    }
    if (table !== 'user_wallets') delete row.user_id
    for (const column of SERVER_INTERNAL_SYNC_COLUMNS[table] ?? []) {
      delete row[column]
    }
    if (table === 'categories' && !row.created_at) {
      row.created_at = this._now()
    }
    row.pulled_at = serverTime
    row.pushed_at = pushedAt ?? null
    const filtered = filterMergePayload(row, this._mergeTableColumns(table)).row
    const keys = Object.keys(filtered)
    const vals = keys.map(k => filtered[k])
    const placeholders = keys.map(() => '?').join(', ')

    try {
      const pk = primaryKeyForTable(table); const updates = keys.filter(key => key !== pk)
      const conflict = updates.length ? `DO UPDATE SET ${updates.map(key => `${key}=excluded.${key}`).join(', ')}` : 'DO NOTHING'
      this._db!.runRaw(`INSERT INTO ${table} (${keys.join(', ')}) VALUES (${placeholders}) ON CONFLICT(${pk}) ${conflict}`, vals)
      if (table === 'user_wallets' && row.balance !== undefined) {
        this._db!.setConfig('wallet_balance', String(row.balance))
      }
    } catch (error) {
      return this._localErrorCategory(error)
    }
    return null
  }

  private _deletePulledHabit(habitId: string): string | null {
    const children = (this._db as any).allRaw?.('SELECT id FROM habit_checkins WHERE habit_id = ?', [habitId]) ?? []
    if (children.some((child: any) => (this._db as any).hasPendingOutbox?.('habit_checkins', child.id))) return 'pending_child_conflict'
    const remove = () => {
      for (const child of children) this._db!.runRaw('DELETE FROM habit_checkins WHERE id = ?', [child.id])
      this._db!.runRaw('DELETE FROM habits WHERE id = ?', [habitId])
    }
    try {
      if (typeof (this._db as any).runInTransaction === 'function') (this._db as any).runInTransaction(remove)
      else remove()
    } catch (error) {
      return this._localErrorCategory(error)
    }
    return null
  }

  private _localErrorCategory(error: unknown): string {
    const message = error instanceof Error ? error.message.toLowerCase() : ''
    return message.includes('constraint') ? 'constraint' : message.includes('locked') || message.includes('disk') ? 'storage' : 'sqlite_operation_failed'
  }

  private _now(): string {
    return nowShanghaiDateTimeString()
  }

  private _emitAuthState(status: number): void {
    const name = status === 401 || status === 403 ? 'mtl:auth-challenge' : status >= 200 && status < 300 ? 'mtl:auth-restored' : ''
    const w = (globalThis as any).window
    if (name && w?.dispatchEvent && w?.CustomEvent) w.dispatchEvent(new w.CustomEvent(name))
  }

  private _emitSyncEvents(walletChanged: boolean): void {
    const w = (globalThis as any).window
    if (!w || typeof w.dispatchEvent !== 'function' || typeof w.CustomEvent !== 'function') return
    w.dispatchEvent(new w.CustomEvent('sync-pull-complete'))
    if (walletChanged) {
      w.dispatchEvent(new w.CustomEvent('balance-updated'))
      w.dispatchEvent(new w.CustomEvent('local-shortcut-trigger', { detail: 'balance-updated' }))
    }
  }
}
