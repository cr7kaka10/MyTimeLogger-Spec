/** 客户端数据库适配与初始化层 */

import { detectPlatformRuntime, getElectronApi, isElectron } from './platform'
import { accountDatabaseName, createCapacitorDatabaseAdapter, getAndroidBulkCapability } from './platform/capacitorDatabase'
import { readActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import { type AccountIdentity } from '@core/AccountIdentity'
import { SENSITIVE_SETTINGS_KEYS } from '@core/SettingsConfigPortability'
import { credentialView, loadScopedCredentialView, readActiveAccountStorageKey, scopedCredentialKey, setSecureCredential } from './platform/credentials'
import { platformFetch } from './platform/fetch'
import { formatBeijingDateTime } from '@core/BeijingTime'

/** 小组件通过此 key 从 CapacitorStorage 读取当前活跃数据库名 */
const WIDGET_ACTIVE_DB_KEY = 'mtl.runtime.widget.active_database_name'

let _ready = false
let _initPromise: Promise<void> | null = null
let capacitorDbAdapter: IDatabaseAdapter | null = null
let activeAccountStorageKey = ''

// SyncWorker 单例
let _syncWorker: any = null
let _syncWorkerInitPromise: Promise<void> | null = null
let coreActionSyncRequester: (() => void) | null = null
export function setCoreActionSyncRequester(requester: (() => void) | null): void {
  coreActionSyncRequester = requester
}
let _currentTimerClient: any = null
const currentTimerClientListeners = new Set<(client: any | null) => void>()

export function createCurrentTimerClientStore() {
  let client: any | null = null
  const listeners = new Set<(next: any | null) => void>()
  return {
    get: () => client,
    set: (next: any | null) => {
      if (client === next) return
      client = next
      listeners.forEach(listener => listener(next))
    },
    subscribe: (listener: (next: any | null) => void) => {
      listeners.add(listener)
      listener(client)
      return () => listeners.delete(listener)
    },
  }
}

const currentTimerClientStore = createCurrentTimerClientStore()

function setCurrentTimerClient(client: any | null, forceNotify = false): void {
  if (_currentTimerClient === client && !forceNotify) return
  _currentTimerClient = client
  currentTimerClientStore.set(client)
}

export interface SyncNowOptions {
  reason?: string
  ledgerExpectation?: { sourceType: string; targetDate: string; exists: boolean }
}

export interface ChecklistSyncNowOptions extends SyncNowOptions {
  providerRefresh?: boolean
}

export interface SyncNowResult {
  ok: boolean
  merged: number
  pending?: number
  statsStr?: string
  diagnostics?: Record<string, any>
  error?: string
}

export interface SyncChangeResult {
  delivery: 'accepted' | 'duplicate' | 'pending' | 'rejected'
  pullOk: boolean
  reason?: string
  ledgerConfirmed?: boolean
  sync: SyncNowResult
}

export type SharedSyncState = 'connecting' | 'syncing' | 'synced' | 'offline' | 'failed'
export type SharedSyncStatus = { state: SharedSyncState; at: string; error?: string }
let latestSharedSyncSequence = 0

export function emitSharedSyncStatus(state: SharedSyncState, error?: string): void {
  const target = globalThis as any
  if (typeof target.dispatchEvent !== 'function' || typeof target.CustomEvent !== 'function') return
  target.dispatchEvent(new target.CustomEvent('mtl:sync-status', { detail: { state, at: formatBeijingDateTime(), error } satisfies SharedSyncStatus }))
}

export function formatSyncProgress(result: Pick<SyncNowResult, 'diagnostics' | 'error'>): string {
  const diagnostics = result.diagnostics || {}; const merge = diagnostics.merge || {}
  const applied = Number(merge.applied ?? 0); const failed = Number(merge.failed ?? 0)
  const conflicts = Array.isArray(merge.conflicts) ? merge.conflicts.length : 0
  const total = applied + failed + conflicts
  const retryAt = Number(merge.retry_at ?? diagnostics.retry_at ?? 0)
  const retryTime = retryAt > 0 ? new Date(retryAt).toLocaleTimeString('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Shanghai',
  }) : ''
  if (diagnostics.stage === 'backoff' || result.error === 'local_merge_backoff') {
    return retryTime ? `下次 ${retryTime}` : ''
  }
  const stage = diagnostics.stage === 'pull' ? '拉取' : '合并'
  const retry = retryTime ? ` · 下次 ${retryTime}` : ''
  if (result.error || failed > 0) return `${stage}失败${retry}`
  return total > 0 || retry ? `${stage} ${applied}/${total}${retry}` : ''
}

export type DateSwitchSyncModule = 'timebook' | 'checklist' | 'exercise' | 'sleep'

export type SleepTimerCommand = { id: string; command_type: string; status: string }
const sleepCommandKey = (id: string) => `sleep_command_executed:${id}`
export const pendingSleepTimerCommands = (db: any): SleepTimerCommand[] => {
  try { return db.allRaw("SELECT id,command_type,status FROM sleep_automation_commands WHERE status='pending' AND command_type='switch_to_sleep'") }
  catch { return [] }
}
export const isSleepTimerCommandExecuted = (db: any, id: string): boolean =>
  Boolean(db.allRaw('SELECT 1 FROM client_sync_state WHERE key=?', [sleepCommandKey(id)])[0])
export const markSleepTimerCommandExecuted = (db: any, id: string): void => db.runRaw(
  "INSERT OR IGNORE INTO client_sync_state (key,value,description,updated_at) VALUES (?, '1', '已执行的睡眠切换命令', datetime('now','localtime'))",
  [sleepCommandKey(id)],
)

const dateSwitchSyncState: Record<DateSwitchSyncModule, { key: string; at: number; promise: Promise<SyncNowResult> | null }> = {
  timebook: { key: '', at: 0, promise: null },
  checklist: { key: '', at: 0, promise: null },
  exercise: { key: '', at: 0, promise: null },
  sleep: { key: '', at: 0, promise: null },
}

const createSyncRunId = (): string => {
  const cryptoApi = (globalThis as any).crypto
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  return `sync-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export async function syncAfterDateSwitch(module: DateSwitchSyncModule, date: string): Promise<SyncNowResult> {
  const state = dateSwitchSyncState[module]
  const key = `${module}:${date}`
  const now = Date.now()
  if (state.promise && state.key === key) return state.promise
  if (state.key === key && now - state.at < 1500) {
    return { ok: true, merged: 0, diagnostics: { skipped: true, reason: 'date_switch_dedupe' } }
  }
  state.key = key
  state.at = now
  state.promise = syncNow({
    reason: module === 'checklist' ? 'checklist-date-switch' : `${module}-date-switch`,
  }).finally(() => {
    state.promise = null
  })
  return state.promise
}

const requireElectronApi = () => {
  const api = getElectronApi()
  if (!api) throw new Error('Electron bridge is not available')
  return api
}

const unsupportedStorageError = () =>
  new Error('当前环境不支持本地数据库。MyTimeLogger 客户端仅支持 PC Electron 客户端和未来 Android 原生适配器。')

export interface IDatabaseAdapter {
  run: (sql: string, params?: any[]) => void;
  exec: (sql: string) => void;
  prepare: (sql: string) => {
    bind: (params?: any[]) => void;
    step: () => boolean;
    getAsObject: () => any;
    free: () => void;
  };
}

export function attachAndroidBulkCapability(db: any, adapter: unknown): any {
  const capability = getAndroidBulkCapability(adapter)
  if (capability) db.androidBulk = capability
  return db
}

export function createDatabaseFacade<T>(create: () => Promise<T>): () => Promise<T> {
  let database: T | null = null
  let initializing: Promise<T> | null = null
  return () => {
    if (database) return Promise.resolve(database)
    if (!initializing) {
      initializing = create().then(value => {
        database = value
        return value
      }).finally(() => { initializing = null })
    }
    return initializing
  }
}

const ANDROID_CREDENTIAL_FIELDS: Record<string, string[]> = {
  atimelogger_config: ['password', 'token', 'refresh_token'],
  ai_model_config: ['text_api_key', 'vision_api_key'],
}

export function attachAndroidCredentialFacade(db: any, namespace = ''): any {
  const sensitive = new Set(SENSITIVE_SETTINGS_KEYS)
  const scrubJson = (raw: string, fields: string[]) => {
    const value = JSON.parse(raw)
    fields.forEach(field => { delete value[field] })
    return JSON.stringify(value)
  }
  db.runInTransaction(() => {
    SENSITIVE_SETTINGS_KEYS.forEach(key => db.runRaw('DELETE FROM system_config WHERE key = ?', [key]))
    for (const [parent, fields] of Object.entries(ANDROID_CREDENTIAL_FIELDS)) {
      const row = db.allRaw('SELECT value FROM system_config WHERE key = ?', [parent])[0]
      if (row?.value) db.runRaw('UPDATE system_config SET value = ? WHERE key = ?', [scrubJson(row.value, fields), parent])
    }
    for (const row of db.allRaw("SELECT id, record_id, payload_json FROM sync_outbox WHERE table_name = 'system_config'")) {
      if (sensitive.has(row.record_id)) db.runRaw('DELETE FROM sync_outbox WHERE id = ?', [row.id])
      else if (ANDROID_CREDENTIAL_FIELDS[row.record_id]) {
        const payload = JSON.parse(row.payload_json)
        if (typeof payload.value === 'string') payload.value = scrubJson(payload.value, ANDROID_CREDENTIAL_FIELDS[row.record_id])
        db.runRaw('UPDATE sync_outbox SET payload_json = ? WHERE id = ?', [JSON.stringify(payload), row.id])
      }
    }
  })
  const getConfig = db.getConfig.bind(db)
  const getAllConfig = db.getAllConfig.bind(db)
  const setConfig = db.setConfig.bind(db)
  db.getConfig = (key: string) => sensitive.has(key) ? credentialView.get(scopedCredentialKey(namespace, key)) : getConfig(key)
  db.getAllConfig = () => {
    const values = getAllConfig()
    sensitive.forEach(key => { delete values[key]; const value = credentialView.get(scopedCredentialKey(namespace, key)); if (value) values[key] = value })
    return values
  }
  db.setConfig = (key: string, value: string, desc = '') => {
    if (!sensitive.has(key)) return setConfig(key, value, desc)
    void setSecureCredential(scopedCredentialKey(namespace, key), value).catch(error => console.error('[credentials] secure write failed', error))
  }
  db.setSecureConfig = async (key: string, value: string, desc = '') => {
    if (!sensitive.has(key)) { setConfig(key, value, desc); return }
    await setSecureCredential(scopedCredentialKey(namespace, key), value)
  }
  return db
}

// 跨平台统一的原生数据库适配器
const nativeDbAdapter: IDatabaseAdapter = {
  run: (sql: string, params: any[] = []) => {
    if (isElectron()) {
      const api = requireElectronApi()
      const res = api.dbExecuteSync?.(sql, params);
      if (res && res.error) {
        throw new Error(res.error);
      }
    }
  },
  exec: (sql: string) => {
    if (isElectron()) {
      const api = requireElectronApi()
      const res = api.dbExecuteSync?.(sql, []);
      if (res && res.error) {
        throw new Error(res.error);
      }
    }
  },
  prepare: (sql: string) => {
    let rows: any[] = [];
    let cursor = 0;
    let bound = false;

    const executeQuery = (params: any[] = []) => {
      if (isElectron()) {
        try {
          const api = requireElectronApi()
          const res = api.dbQuerySync?.(sql, params);
          if (res && res.error) {
            console.error('[nativeDbAdapter] query returned error:', res.error);
            return [];
          }
          return Array.isArray(res) ? res : [];
        } catch (e) {
          console.error('[nativeDbAdapter] dbQuerySync exception:', sql, e);
          return [];
        }
      }
      return [];
    };

    return {
      bind: (params: any[] = []) => {
        rows = executeQuery(params);
        cursor = 0;
        bound = true;
      },
      step: () => {
        if (!bound) {
          rows = executeQuery([]);
          cursor = 0;
          bound = true;
        }
        return cursor < rows.length;
      },
      getAsObject: () => {
        const row = rows[cursor];
        cursor++;
        return row;
      },
      free: () => {
        rows = [];
        bound = false;
      }
    };
  }
};

export async function initDatabase(dbUrl = '/my_time_logger.db'): Promise<void> {
  if (_ready) return
  if (_initPromise) return _initPromise

  if (detectPlatformRuntime() === 'capacitor-android') {
    _initPromise = (async () => {
      const accountStorageKey = await readActiveAccountStorageKey()
      activeAccountStorageKey = accountStorageKey || ''
      const dbName = accountStorageKey ? accountDatabaseName(accountStorageKey) : undefined
      const adapter = createCapacitorDatabaseAdapter(undefined, dbName)
      capacitorDbAdapter = adapter
      // 写入实际数据库名，供小组件 Java 侧读取
      const { Preferences } = await import('@capacitor/preferences')
      await Preferences.set({ key: WIDGET_ACTIVE_DB_KEY, value: dbName || 'mtl-bootstrap.db' })
      if (accountStorageKey) await loadScopedCredentialView(accountStorageKey)
      _ready = true
    })().catch(error => { _initPromise = null; throw error })
    return _initPromise
  }

  if (isElectron()) {
    _initPromise = (async () => {
      console.log('[db] Electron environment detected, using native bridge')
      _ready = true
    })()
    return _initPromise
  }

  void dbUrl
  _initPromise = Promise.reject(unsupportedStorageError())
  return _initPromise
}

export function getRawDb(): any {
  if (isElectron()) return nativeDbAdapter
  if (capacitorDbAdapter) return capacitorDbAdapter
  throw unsupportedStorageError()
}

async function _initSyncWorker(db: any) {
  const runtime = readActiveEnvironmentRuntimeConfig(db.getAllConfig?.() || {})
  const serverUrl = runtime.serverUrl
  const authToken = runtime.authToken

  if (!serverUrl || !authToken) {
    if (_syncWorker?.stop) _syncWorker.stop()
    _syncWorker = null
    setCurrentTimerClient(null)
    return
  }
  if (_syncWorker) {
    _syncWorker.updateConfig(serverUrl, authToken)
    setCurrentTimerClient(_currentTimerClient, true)
    return
  }
  if (_syncWorkerInitPromise) {
    await _syncWorkerInitPromise
    if (_syncWorker) _syncWorker.updateConfig(serverUrl, authToken)
    return
  }

  _syncWorkerInitPromise = (async () => {
    const mod = await import('@core/SyncWorker')
    const apiMod = await import('@core/ApiClient')
    const platformRuntime = detectPlatformRuntime()
    const identityKey = db.getConfig?.('account_identity_key') || ''
    if (!identityKey) return
    _syncWorker = new mod.SyncWorker({ enableSSE: platformRuntime !== 'capacitor-android', identityKey })
    const requester = platformRuntime === 'capacitor-android' ? platformFetch : undefined
    const api = new apiMod.ApiClient(serverUrl, authToken, undefined, requester)
    setCurrentTimerClient(api)
    _syncWorker.bind(api, db)
    _syncWorker.start()
    console.log('[db] SyncWorker 已启动')
  })()

  try {
    await _syncWorkerInitPromise
  } catch (e) {
    console.warn('[db] SyncWorker 初始化失败:', e)
  } finally {
    _syncWorkerInitPromise = null
  }
}

export function getTimerLeaseClient(): any {
  return _currentTimerClient
}

export function getCurrentTimerClient(): any {
  return _currentTimerClient
}

export function subscribeCurrentTimerClient(listener: (client: any | null) => void): () => void {
  return currentTimerClientStore.subscribe(listener)
}

export async function deleteServerSession(sessionId: number | string): Promise<boolean> {
  if (!_currentTimerClient?.delete) return false
  const response = await _currentTimerClient.delete(`/api/sessions/${encodeURIComponent(String(sessionId))}`)
  return response?.ok === true
}

export async function refreshCurrentTimerState(): Promise<any> {
  if (!_currentTimerClient?.readCurrentTimer) return { code: 'network', status: 0, errorCode: 'timer_client_not_ready' }
  const outcome = await _currentTimerClient.readCurrentTimer()
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('mtl:current-timer-state', { detail: outcome }))
  }
  return outcome
}

export async function refreshSyncConfiguration(db: any): Promise<void> {
  await _initSyncWorker(db)
  if (!_syncWorker) return
  const runtime = readActiveEnvironmentRuntimeConfig(db.getAllConfig?.() || {})
  if (runtime.serverUrl && runtime.authToken) _syncWorker.connectSSE(runtime.serverUrl, runtime.authToken)
}

async function createDatabase() {
  await initDatabase()
  const m = await import('@models/Database')
  const adapter = getRawDb()
  const rawDb = new m.Database(adapter)
  const db = detectPlatformRuntime() === 'capacitor-android'
    ? attachAndroidCredentialFacade(attachAndroidBulkCapability(rawDb, adapter), activeAccountStorageKey) : rawDb

  if (activeAccountStorageKey) db.setConfig('account_identity_key', activeAccountStorageKey)
  // 初始化服务端同步 + SSE 订阅
  await refreshSyncConfiguration(db)

  // 注入真实 enqueue（替换空 log）
  if (_syncWorker) {
    db.setEnqueue((table: string, id: number | string) => {
      _syncWorker!.enqueue(table, id as any)
      coreActionSyncRequester?.()
    })
  } else {
    db.setEnqueue((table: string, id: number | string) => {
      console.log(`[sync] ${table}#${id} pending push`)
      coreActionSyncRequester?.()
    })
  }

  return db
}

let applicationDatabase: any = null
let applicationDatabaseInit: Promise<any> | null = null

export function getDatabase() {
  if (applicationDatabase) return Promise.resolve(applicationDatabase)
  if (!applicationDatabaseInit) {
    applicationDatabaseInit = createDatabase().then(db => {
      applicationDatabase = db
      return db
    }).finally(() => { applicationDatabaseInit = null })
  }
  return applicationDatabaseInit
}

export async function activateAccountStorage(identity: AccountIdentity): Promise<any> {
  if (_syncWorker?.stop) _syncWorker.stop()
  _syncWorker = null; setCurrentTimerClient(null)
  activeAccountStorageKey = identity.storageKey
  if (isElectron()) {
    const result = await getElectronApi()?.activateAccountDatabase?.(identity.storageKey)
    if (!result?.ok) throw new Error('account_database_activation_failed')
  } else if (detectPlatformRuntime() === 'capacitor-android') {
    const dbName = accountDatabaseName(identity.storageKey)
    capacitorDbAdapter = createCapacitorDatabaseAdapter(undefined, dbName)
    // 切换账号后更新小组件数据库名
    void import('@capacitor/preferences').then(({ Preferences }) =>
      Preferences.set({ key: WIDGET_ACTIVE_DB_KEY, value: dbName })
    ).catch(() => {})
  } else {
    throw new Error('account_storage_unsupported')
  }
  applicationDatabase = null; applicationDatabaseInit = null
  const db = await getDatabase()
  db.setConfig('account_identity_key', identity.storageKey)
  await loadScopedCredentialView(identity.storageKey)
  return db
}

/** 事件驱动立即推送（不等 5s 定时器），用于操作后即时同步 */
export function flushSync() {
  syncNow().catch(() => {})
}

/** 执行指定同步域；公共入口始终使用 core，只有清单专用入口可使用 checklist。 */
async function runSyncNow(options: SyncNowOptions, scope: 'core' | 'checklist', refresh: boolean): Promise<SyncNowResult> {
  const syncRunId = createSyncRunId()
  const sharedSyncSequence = ++latestSharedSyncSequence
  const startedAt = Date.now()
  const reason = options.reason || 'manual'
  console.info('[syncNow] start', { sync_run_id: syncRunId, reason, scope, refresh })
  emitSharedSyncStatus('syncing')
  if (!_syncWorker) await getDatabase().catch(() => {})
  if (!_syncWorker && _syncWorkerInitPromise) await _syncWorkerInitPromise.catch(() => {})
  if (_syncWorker && typeof _syncWorker.flushNow === 'function') {
    const timerBefore = await refreshCurrentTimerState().catch(() => ({ code: 'network' }))
    let result: any
    try {
      result = await _syncWorker.flushNow(refresh, { syncRunId, reason, scope, ledgerExpectation: options.ledgerExpectation })
    } catch {
      result = { ok: false, merged: 0, error: 'sync_failed' }
    }
    const timerAfter = await refreshCurrentTimerState().catch(() => ({ code: 'network' }))
    const normalized = result && typeof result === 'object'
      ? result
      : { ok: true, merged: 0 }
    normalized.diagnostics = {
      ...(normalized.diagnostics || {}),
      sync_run_id: syncRunId,
      scope,
      client_elapsed_ms: Date.now() - startedAt,
      timer_state_before: timerBefore.code,
      timer_state_after: timerAfter.code,
    }
    console.info('[syncNow] finish', {
      sync_run_id: syncRunId,
      reason,
      scope,
      refresh,
      ok: normalized.ok,
      merged: normalized.merged,
      error: normalized.error,
      request_id: normalized.diagnostics?.request_id,
      elapsed_ms: normalized.diagnostics?.client_elapsed_ms,
    })
    if (sharedSyncSequence === latestSharedSyncSequence) {
      emitSharedSyncStatus(normalized.ok ? 'synced' : 'failed', normalized.error)
    }
    return normalized
  }
  const failed = {
    ok: false,
    merged: 0,
    error: 'sync_worker_not_ready',
    diagnostics: { sync_run_id: syncRunId, client_elapsed_ms: Date.now() - startedAt },
  }
  console.warn('[syncNow] failed', failed.diagnostics)
  if (sharedSyncSequence === latestSharedSyncSequence) emitSharedSyncStatus('failed', failed.error)
  return failed
}

/** 通用小同步：仅客户端与服务端，不具备 TickTick 刷新能力。 */
export async function syncNow(options: SyncNowOptions = {}): Promise<SyncNowResult> {
  return runSyncNow(options, 'core', false)
}

/** 清单专用大同步：只有清单页面可请求 TickTick 对账。 */
export async function syncChecklistNow(options: ChecklistSyncNowOptions = {}): Promise<SyncNowResult> {
  return runSyncNow(options, 'checklist', Boolean(options.providerRefresh))
}

export async function syncChangeNow(
  changeId: string,
  options: SyncNowOptions = {},
  requestSync: (options?: SyncNowOptions) => Promise<SyncNowResult> = syncNow,
): Promise<SyncChangeResult> {
  const sync = await requestSync(options)
  const operations = sync.diagnostics?.push?.operation_results
  const target = Array.isArray(operations) ? operations.find((item: any) => item.change_id === changeId) : undefined
  const ledgerConfirmed = sync.ok && (!options.ledgerExpectation || sync.diagnostics?.ledger_expectation?.confirmed === true)
  if (target?.status === 'rejected') return { delivery: 'rejected', pullOk: sync.ok, ledgerConfirmed, reason: target.reason || 'operation_rejected', sync }
  if (target?.status === 'accepted' || target?.status === 'duplicate' || target?.status === 'skipped') {
    return { delivery: target.status === 'duplicate' ? 'duplicate' : 'accepted', pullOk: sync.ok, ledgerConfirmed, sync }
  }
  const db = await getDatabase().catch(() => null)
  const persisted = db?.allRaw?.('SELECT status,last_error FROM sync_outbox WHERE change_id=? LIMIT 1', [changeId])?.[0]
  if (persisted?.status === 'synced') return { delivery: 'accepted', pullOk: sync.ok, ledgerConfirmed, sync }
  return { delivery: 'pending', pullOk: sync.ok, ledgerConfirmed, reason: sync.error, sync }
}

/** 时间书进入和会话提交通知专用：仅拉取服务端时间记录增量。 */
export async function pullTimeBookSessionVisibility(): Promise<SyncNowResult> {
  const syncRunId = createSyncRunId()
  const startedAt = Date.now()
  console.info('[timebookSessionVisibility] start', { sync_run_id: syncRunId })
  emitSharedSyncStatus('syncing')
  if (!_syncWorker) await getDatabase().catch(() => {})
  if (!_syncWorker && _syncWorkerInitPromise) await _syncWorkerInitPromise.catch(() => {})
  if (_syncWorker && typeof _syncWorker.pullSessionVisibility === 'function') {
    try {
      const result: SyncNowResult = await _syncWorker.pullSessionVisibility({ syncRunId, reason: 'session-visibility' })
      result.diagnostics = { ...(result.diagnostics || {}), sync_run_id: syncRunId, client_elapsed_ms: Date.now() - startedAt }
      console.info('[timebookSessionVisibility] finish', {
        sync_run_id: syncRunId, ok: result.ok, merged: result.merged,
        error: result.error, elapsed_ms: result.diagnostics.client_elapsed_ms,
      })
      emitSharedSyncStatus(result.ok ? 'synced' : 'failed', result.error)
      return result
    } catch (error: any) {
      const failed: SyncNowResult = {
        ok: false, merged: 0, error: error?.message || 'pull_failed',
        diagnostics: { sync_run_id: syncRunId, client_elapsed_ms: Date.now() - startedAt },
      }
      emitSharedSyncStatus('failed', failed.error)
      return failed
    }
  }
  const failed: SyncNowResult = {
    ok: false, merged: 0, error: 'sync_worker_not_ready',
    diagnostics: { sync_run_id: syncRunId, client_elapsed_ms: Date.now() - startedAt },
  }
  emitSharedSyncStatus('failed', failed.error)
  return failed
}

/** 仅推送 Outbox 队列到服务端（不拉取），用于独立 Push 按钮 */
export async function pushChecklistOnly(): Promise<SyncNowResult> {
  const syncRunId = createSyncRunId()
  const startedAt = Date.now()
  console.info('[pushOnly] start', { sync_run_id: syncRunId })
  emitSharedSyncStatus('syncing')
  if (_syncWorker && typeof _syncWorker.pushOnly === 'function') {
    try {
      const res = await _syncWorker.pushOnly({ syncRunId, reason: 'checklist-push-only', scope: 'checklist' })
      const result: SyncNowResult = {
        ok: res.ok,
        merged: res.merged,
        pending: res.pending,
        statsStr: res.statsStr,
        diagnostics: {
          sync_run_id: syncRunId,
          client_elapsed_ms: Date.now() - startedAt,
        },
      }
      if (!res.ok) {
        result.error = 'push_failed'
      }
      console.info('[pushOnly] finish', result)
      emitSharedSyncStatus(result.ok ? 'synced' : 'failed', result.error)
      return result
    } catch (e: any) {
      const failed: SyncNowResult = {
        ok: false,
        merged: 0,
        pending: 0,
        error: e?.message || 'push_failed',
        diagnostics: { sync_run_id: syncRunId, client_elapsed_ms: Date.now() - startedAt },
      }
      console.error('[pushOnly] failed', failed)
      emitSharedSyncStatus('failed', failed.error)
      return failed
    }
  }
  const failed: SyncNowResult = {
    ok: false,
    merged: 0,
    pending: 0,
    error: 'sync_worker_not_ready',
    diagnostics: { sync_run_id: syncRunId, client_elapsed_ms: Date.now() - startedAt },
  }
  console.warn('[pushOnly] failed', failed.diagnostics)
  emitSharedSyncStatus('failed', failed.error)
  return failed
}

/** 立即拉取服务端增量并 await 结果，用于刷新按钮 */
export async function pullSync(): Promise<number> {
  emitSharedSyncStatus('syncing')
  if (_syncWorker && typeof _syncWorker.pullAndMergeResult === 'function') {
    try {
      const result = await _syncWorker.pullAndMergeResult(false, { scope: 'core', reason: 'server-readback' })
      emitSharedSyncStatus(result.ok ? 'synced' : 'failed', result.error)
      return result.ok ? result.merged : 0
    } catch (error: any) {
      emitSharedSyncStatus('failed', error?.message || 'pull_failed')
      return 0
    }
  }
  emitSharedSyncStatus('failed', 'sync_worker_not_ready')
  return 0
}

/** 暂停后台同步（用于清空数据等排他操作） */
export function pauseSync() {
  if (_syncWorker && typeof _syncWorker.pauseForReset === 'function') {
    _syncWorker.pauseForReset()
    return
  }
  if (_syncWorker && typeof _syncWorker.stop === 'function') {
    _syncWorker.stop()
  }
}

/** 恢复后台同步 */
export function resumeSync() {
  if (_syncWorker && typeof _syncWorker.resumeFromReset === 'function') {
    _syncWorker.resumeFromReset()
    return
  }
  if (_syncWorker && typeof _syncWorker.start === 'function') {
    _syncWorker.start()
  }
}
