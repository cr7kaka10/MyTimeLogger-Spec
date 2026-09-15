/**
 * 数据库 CRUD 层 — 从 app/models/database.py + 各 Store 翻译
 *
 * 使用同步 SQLite 适配器，PC 端由 Electron better-sqlite3 桥接承载。
 * 所有写操作自动维护 updated_at / pushed_at。
 */

import { initDatabase } from './Schema'
import { HabitService } from './services/HabitService'
import { RewardLedgerService, type LedgerSummary } from './services/RewardLedgerService'
import { encryptString, decryptString } from '../utils/crypto'
import { normalizeShanghaiDateTime, normalizeTaskTimeFields } from '../utils/time'
import { resolveChecklistSyncStartDate } from '../core/ChecklistSyncStartDate'
import { isDeviceLocalSetting } from '../core/SettingDefinitions'
import { isOutboxEnabledTable } from '../core/SyncEntities'
import { sessionBusinessDate } from '../core/SessionBusinessDate'
import type { ExercisePlanDefinition, PlanDay, ScoreRule } from './ExercisePlanSampleDataInitializer'

const V4_DIET_RULE_KEYS = ['no_snacks', 'no_sugary_drinks', 'no_refined_staples']

// system_config 表 key 名常量
export const SYSTEM_CONFIG_KEYS = {
  deviceId: 'device_id',
  lastServerVersion: 'last_server_version',
  clientToServerSyncedAt: 'client_to_server_synced_at',
  serverToClientSyncedAt: 'server_to_client_synced_at',
  lastSyncAt: 'last_sync_at',
  serverToTicktickSyncedAt: 'server_to_ticktick_synced_at',
  ticktickToServerSyncedAt: 'ticktick_to_server_synced_at',
  syncProtocol: 'sync_protocol',
} as const

const SENSITIVE_KEYS = [
  'auth_token',
  'env_development_auth_token',
  'env_testing_auth_token',
  'env_production_auth_token',
  'ai_text_api_key',
  'ai_vision_api_key',
  'atimelogger_password',
  'atimelogger_token',
  'atimelogger_refresh_token',
]

// ======================== 类型 ========================

export interface Category {
  id: number; name: string; icon: string; color: string
  group_name: string; sort_order: number; is_active: number
  created_at: string; updated_at?: string; pushed_at?: string | null
}

export interface SessionRec {
  id: number | string; start_time: string; end_time: string
  net_duration_minutes: number; net_duration_seconds?: number | null; date: string; day_of_week?: string
  pause_count: number; pause_reasons?: string; session_summary?: string
  category_id: number | null; updated_at?: string; pushed_at?: string | null
}

export interface ATimeLoggerSegment {
  id: number
  local_session_id: string
  local_segment_key: string
  local_category_id?: number | null
  atimelogger_type_id?: string | null
  atimelogger_activity_id?: string | null
  atimelogger_interval_id?: string | null
  remote_status: string
  sync_state: string
  last_error?: string | null
  created_at: string
  updated_at?: string | null
}

export interface Habit {
  id: number | string; title: string; icon: string; color: string
  category_id: number | null; sort_order: number
  is_active: number; difficulty: string; created_at?: string
  updated_at?: string; pushed_at?: string | null
}

export interface CategoryNormalizationPreview {
  name: string
  canonicalId: number
  duplicateIds: number[]
  referenceCounts: Record<number, number>
}

const CATEGORY_REFERENCE_COLUMNS = [
  ['study_sessions', 'category_id'], ['tasks', 'category_id'], ['habits', 'category_id'],
  ['goals', 'category_id'], ['goal_category_bindings', 'category_id'], ['learning_tasks', 'category_id'],
  ['atimelogger_segments', 'local_category_id'],
] as const

export interface HabitCheckin {
  id: number | string; habit_id: number | string; checkin_date: string
  checkin_time?: string; status: number; updated_at?: string; pushed_at?: string | null
}

export interface Goal {
  id: number | string; title: string; category_id: number | null
  category_ids?: number[]
  metric: string; target_value: number; period: string
  reward_coins: number; reward_id?: number | string; operator: string
  penalty_coins: number; is_active: number; created_at?: string
  updated_at?: string; pushed_at?: string | null
}

export interface Reward {
  id: number | string; title: string; icon: string; price: number
  redemption_mode?: 'coins' | 'task' | 'goal' | 'pending_binding' | 'custom_spend'
  description?: string; unlock_task_id?: string; unlock_task_title?: string
  fulfillment_mode?: 'immediate' | 'fragment'; fragment_target_count?: number; fragment_rule_version?: number
  is_active: number; created_at?: string; updated_at?: string; pushed_at?: string | null
}

export interface LedgerEntry {
  id: number | string; amount: number; source_type: string; source_id?: number | string
  description?: string; target_date?: string; occurred_at?: string | null; created_at?: string; updated_at?: string; pushed_at?: string | null
}

export interface ServerLedgerSnapshot {
  rows: LedgerEntry[]
  summary: { balance: number; income: number; expense: number }
  integrity: { count: number; sha256: string }
  epoch?: number
  reward_fragments?: Array<Record<string, any>>
}

export interface SyncOutboxEntry {
  id: number
  change_id: string
  device_id: string
  table_name: string
  record_id: string
  operation: string
  base_version?: string | null
  payload_json: string
  status: string
  retry_count: number
  last_error?: string | null
  created_at: string
  updated_at: string
}

export interface SleepData {
  id: number; date: string; sleep_score?: number
  total_sleep_min?: number; deep_sleep_min?: number; light_sleep_min?: number
  rem_sleep_min?: number; awake_count?: number; sleep_start?: string; sleep_end?: string
  deep_sleep_ratio?: number; light_sleep_ratio?: number; rem_sleep_ratio?: number
  sleep_continuity?: number; breathing_score?: number; sleep_cycles?: number
  awake_min?: number; fall_asleep_min?: number; wake_up_min?: number
  atm_sleep_start?: string; atm_sleep_end?: string; analysis_report?: string
  analysis_html?: string; official_advice?: string
  morning_diary?: string; evening_diary?: string; morning_diary_written_at?: string; evening_diary_written_at?: string; report_status: number
  full_report_state?: 'generated' | 'insufficient_time_records'; tracked_duration_seconds?: number
  source?: string; synced_at?: string; sync_status?: string; sync_error?: string
  updated_at?: string; pushed_at?: string | null
}

const SLEEP_DATA_COLUMNS = new Set([
  'sleep_score', 'total_sleep_min', 'deep_sleep_min', 'light_sleep_min',
  'rem_sleep_min', 'awake_count', 'sleep_start', 'sleep_end',
  'deep_sleep_ratio', 'light_sleep_ratio', 'rem_sleep_ratio',
  'sleep_continuity', 'breathing_score', 'sleep_cycles', 'awake_min',
  'fall_asleep_min', 'wake_up_min', 'atm_sleep_start', 'atm_sleep_end',
  'analysis_report', 'analysis_html', 'official_advice',
  'morning_diary', 'evening_diary', 'morning_diary_written_at', 'evening_diary_written_at', 'report_status',
  'full_report_state', 'tracked_duration_seconds',
  'source', 'synced_at', 'sync_status', 'sync_error', 'updated_at', 'pushed_at',
])

export type SqlDB = any  // Electron better-sqlite3 bridge 或 Android 原生 SQLite 适配器

const CONFIG_MAPPING: Record<string, { parent: string; key: string; type: 'string' | 'number' | 'boolean' }> = {
  // atimelogger_config
  atimelogger_enabled: { parent: 'atimelogger_config', key: 'enabled', type: 'boolean' },
  atimelogger_username: { parent: 'atimelogger_config', key: 'username', type: 'string' },
  atimelogger_password: { parent: 'atimelogger_config', key: 'password', type: 'string' },
  atimelogger_owner_username: { parent: 'atimelogger_config', key: 'owner_username', type: 'string' },
  atimelogger_token: { parent: 'atimelogger_config', key: 'token', type: 'string' },
  atimelogger_refresh_token: { parent: 'atimelogger_config', key: 'refresh_token', type: 'string' },
  atimelogger_device_id: { parent: 'atimelogger_config', key: 'device_id', type: 'string' },
  atimelogger_auth_required: { parent: 'atimelogger_config', key: 'auth_required', type: 'boolean' },
  atimelogger_type_map: { parent: 'atimelogger_config', key: 'type_map', type: 'string' },
  atimelogger_unmatched_categories: { parent: 'atimelogger_config', key: 'unmatched_categories', type: 'string' },

  // ai_model_config
  ai_vision_endpoint: { parent: 'ai_model_config', key: 'vision_base_url', type: 'string' },
  ai_vision_api_key: { parent: 'ai_model_config', key: 'vision_api_key', type: 'string' },
  ai_vision_model: { parent: 'ai_model_config', key: 'vision_model', type: 'string' },
  ai_text_endpoint: { parent: 'ai_model_config', key: 'text_base_url', type: 'string' },
  ai_text_api_key: { parent: 'ai_model_config', key: 'text_api_key', type: 'string' },
  ai_text_model: { parent: 'ai_model_config', key: 'text_model', type: 'string' },

  // hotkeys
  shortcut_toggle_timer: { parent: 'hotkeys', key: 'toggle_pause', type: 'string' },
  shortcut_minimize: { parent: 'hotkeys', key: 'toggle_activity_panel', type: 'string' },
}

const CONFIG_DEFAULTS: Record<string, any> = {
  atimelogger_config: { enabled: false, username: '', password: '', owner_username: '', token: '', refresh_token: '', device_id: '', auth_required: false, type_map: '{}', unmatched_categories: '[]' },
  ai_model_config: { vision_base_url: 'https://open.bigmodel.cn/api/paas/v4', vision_api_key: '', vision_model: 'glm-4v-flash', text_base_url: 'https://open.bigmodel.cn/api/paas/v4', text_api_key: '', text_model: 'glm-4-flash' },
  hotkeys: { toggle_pause: '<alt>+c', toggle_activity_panel: '<alt>+z' },
}

const LOCAL_SYNC_CONFIG_KEYS = new Set([
  'account_identity_key',
  'device_id',
  'wallet_balance',
  'music_folder',
  'server_url',
  'auth_token',
  'atimelogger_config',
  'ticktick_config',
  'ai_model_config',
  's3_backup_config',
  'active_environment',
  'env_development_server_url',
  'env_development_username',
  'env_development_auth_token',
  'env_testing_server_url',
  'env_testing_username',
  'env_testing_auth_token',
  'env_production_server_url',
  'env_production_username',
  'env_production_auth_token',
  'hotkeys',
  'sync_protocol',
  'client_to_server_synced_at',
  'server_to_client_synced_at',
  'last_sync_at',
  'server_to_ticktick_synced_at',
  'ticktick_to_server_synced_at',
])

// ======================== Database 类 ========================

export class Database {
  private _db: SqlDB
  private _enqueueFn: ((table: string, id: number | string) => void) | null = null
  private _lastInsertedUUID: string | null = null
  private _habitService: HabitService
  private _rewardLedgerService: RewardLedgerService

  constructor(db: SqlDB) {
    this._db = db
    initDatabase(db)
    this._habitService = new HabitService({
      all: (sql, params = []) => this._all(sql, params),
      run: (sql, params = []) => this._run(sql, params),
      getConfig: key => this.getConfig(key),
      setConfig: (key, value, desc = '') => this.setConfig(key, value, desc),
    })
    this._rewardLedgerService = new RewardLedgerService({
      now: () => this._now(),
      localToday: () => this._localToday(),
      get: (sql, params = []) => this._get(sql, params),
      all: (sql, params = []) => this._all(sql, params),
      run: (sql, params = []) => this._run(sql, params),
      afterWrite: (table, id) => this._afterWrite(table, id),
      getConfig: key => this.getConfig(key),
      setConfig: (key, value, desc = '') => this.setConfig(key, value, desc),
      getRecordById: (table, id) => this.getRecordById(table, id),
    })
    this.ensureDeviceId()
    this.repairInterruptedDietCheckinOutbox()
    this.migrateSensitiveConfigs()
    this.repairManualSessionBusinessDates()
  }

  /** 注入 SyncWorker.enqueue 函数，供写操作后调用 */
  setEnqueue(fn: (table: string, id: number | string) => void): void {
    this._enqueueFn = fn
  }

  addBehaviorEvent(event: Record<string, any>): void {
    this._run(`INSERT OR IGNORE INTO behavior_event_outbox (event_id,occurred_at,device_id,runtime,page,event_type,action,target_type,target_id,result,error_code,trace_id,metadata_json,priority,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`, [event.event_id,event.occurred_at,event.device_id,event.runtime,event.page,event.event_type,event.action,event.target_type||null,event.target_id||null,event.result,event.error_code||null,event.trace_id||null,JSON.stringify(event.metadata||{}),event.priority||'normal',this._now()])
  }

  listBehaviorEvents(limit = 50): any[] { return this._all('SELECT * FROM behavior_event_outbox ORDER BY created_at,event_id LIMIT ?', [Math.min(Math.max(limit, 1), 100)]) }
  deleteBehaviorEvents(ids: string[]): void { ids.forEach(id => this._run('DELETE FROM behavior_event_outbox WHERE event_id=?', [id])) }
  trimBehaviorEvents(maxRows = 5000): void {
    const count = Number(this._get('SELECT COUNT(*) AS count FROM behavior_event_outbox')?.count || 0)
    const excess = count - maxRows
    if (excess <= 0) return
    const removable = this._all("SELECT event_id FROM behavior_event_outbox WHERE result NOT IN ('failed','error','rejected') ORDER BY CASE priority WHEN 'low' THEN 0 ELSE 1 END,created_at,event_id LIMIT ?", [excess])
    removable.forEach(row => this._run('DELETE FROM behavior_event_outbox WHERE event_id=?', [row.event_id]))
    if (removable.length) this.addBehaviorEvent({ event_id: this._generateUUID(), occurred_at: this._now(), device_id: this.getConfig('device_id') || 'unknown', runtime: 'client', page: 'audit', event_type: 'system', action: 'audit.outbox_trimmed', result: 'accepted', priority: 'high', metadata: { removed_count: removable.length } })
  }

  // ======================== 工具 ========================

  private _beijingNow(d: Date = new Date()): Date {
    const utc = d.getTime() + (d.getTimezoneOffset() * 60000);
    return new Date(utc + (3600000 * 8));
  }

  private _parseLocalDate(dateStr: string): Date {
    const parts = dateStr.split('-');
    return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  }

  private _now(d: Date = new Date()): string {
    const bj = this._beijingNow(d)
    const year = bj.getFullYear()
    const month = String(bj.getMonth() + 1).padStart(2, '0')
    const day = String(bj.getDate()).padStart(2, '0')
    const hour = String(bj.getHours()).padStart(2, '0')
    const minute = String(bj.getMinutes()).padStart(2, '0')
    const second = String(bj.getSeconds()).padStart(2, '0')
    return `${year}-${month}-${day} ${hour}:${minute}:${second}`
  }

  private _localToday(): string {
    return this._now().slice(0, 10)
  }

  private _sessionBusinessDate(startTime: string, endTime: string, fallback = ''): string {
    return sessionBusinessDate(startTime, endTime, fallback)
  }


  private _generateUUID(): string {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  ensureDeviceId(): string {
    const existing = this.getConfig('device_id')
    if (existing) return existing
    const deviceId = `device_${this._generateUUID()}`
    this.setConfig('device_id', deviceId, '客户端设备 ID')
    return deviceId
  }

  createOutboxOperation(table: string, recordId: number | string, operation: string, payload: Record<string, any>, baseVersion?: string | null): string {
    const now = this._now()
    const deviceId = this.ensureDeviceId()
    const changeId = `${deviceId}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
    this._run(
      `INSERT INTO sync_outbox (
         change_id, device_id, table_name, record_id, operation, base_version,
         payload_json, status, retry_count, created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)`,
      [
        changeId,
        deviceId,
        table,
        String(recordId),
        operation,
        baseVersion ?? null,
        JSON.stringify(payload),
        now,
        now,
      ],
    )
    console.info(`[Outbox Enqueue] table=${table} record_id=${recordId} operation=${operation} change_id=${changeId}`)
    return changeId
  }

  private _enqueueOutbox(table: string, recordId: number | string, operation: string, payload: Record<string, any>, baseVersion?: string | null): void {
    const existing = this._get(
      `SELECT id FROM sync_outbox WHERE table_name = ? AND record_id = ? AND status IN ('pending', 'failed') ORDER BY id DESC LIMIT 1`,
      [table, String(recordId)],
    )
    if (existing) {
      this._run(
        `UPDATE sync_outbox SET operation = ?, payload_json = ?, base_version = ?, status = 'pending', last_error = NULL, updated_at = ? WHERE id = ?`,
        [operation, JSON.stringify(payload), baseVersion ?? null, this._now(), existing.id],
      )
      return
    }
    this.createOutboxOperation(table, recordId, operation, payload, baseVersion)
  }

  private repairInterruptedDietCheckinOutbox(): void {
    const placeholders = V4_DIET_RULE_KEYS.map(() => '?').join(',')
    const rows = this._all(`SELECT d.* FROM exercise_diet_checkins d
      WHERE d.plan_version='v4' AND d.rule_key IN (${placeholders}) AND d.pushed_at IS NULL
      AND COALESCE(d.updated_at,'') > COALESCE(d.pulled_at,'')
      AND NOT EXISTS (SELECT 1 FROM sync_outbox o WHERE o.table_name='exercise_diet_checkins'
        AND o.record_id=CAST(d.id AS TEXT) AND o.status IN ('pending','failed','sending'))`, V4_DIET_RULE_KEYS)
    rows.forEach(row => this._enqueueOutbox('exercise_diet_checkins', row.id, 'upsert', row, row.pulled_at ?? null))
  }

  private _formatLedgerDescription(template: string, replacements: Record<string, string>): string {
    let result = template
    for (const [k, v] of Object.entries(replacements)) {
      result = result.replace(new RegExp(`{${k}}`, 'g'), v)
    }
    return result
  }

  private _processInsert(sql: string, params: any[]): { sql: string, params: any[] } {
    const match = sql.match(/INSERT\s+(?:OR\s+\w+\s+)?INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)/i);
    if (!match) return { sql, params };

    const table = match[1].toLowerCase();
    const columnsStr = match[2];
    const valuesStr = match[3];

    const uuidTables = [
      'study_sessions', 'reward_ledger', 'habit_checkins',
      'tasks', 'habits', 'external_rewards', 'goals', 'rewards'
    ];

    if (!uuidTables.includes(table)) return { sql, params };

    const columns = columnsStr.split(',').map(c => c.trim().toLowerCase());
    if (columns.includes('id')) return { sql, params };

    const newColumnsStr = 'id, ' + columnsStr;
    const newValuesStr = '?, ' + valuesStr;
    const newSqlSafe = sql.replace(columnsStr, newColumnsStr).replace(valuesStr, newValuesStr);

    const uuid = this._generateUUID();
    this._lastInsertedUUID = uuid;
    const newParams = [uuid, ...params];

    return { sql: newSqlSafe, params: newParams };
  }

  private _run(sql: string, params: any[] = []): void {
    const processed = this._processInsert(sql, params);
    this._db.run(processed.sql, processed.params)
  }

  private _get(sql: string, params: any[] = []): Record<string, any> | undefined {
    if (sql.trim().toLowerCase().includes('last_insert_rowid()') && this._lastInsertedUUID !== null) {
      const val = this._lastInsertedUUID;
      this._lastInsertedUUID = null;
      return { id: val };
    }
    const rows = this._all(sql, params)
    return rows.length > 0 ? rows[0] : undefined
  }

  private _all(sql: string, params: any[] = []): Record<string, any>[] {
    try {
      const stmt = this._db.prepare(sql)
      stmt.bind(params)
      const rows: Record<string, any>[] = []
      while (stmt.step()) {
        rows.push(stmt.getAsObject())
      }
      stmt.free()
      return rows
    } catch {
      return []
    }
  }

  /** 按表名 + id 查询单条记录（SyncWorker 用） */
  getRecordById(table: string, id: number | string): Record<string, any> | undefined {
    return this._get(`SELECT * FROM ${table} WHERE id = ?`, [id])
  }

  getPendingOutbox(limit = 50): SyncOutboxEntry[] {
    return this._all(
      `SELECT * FROM sync_outbox
       WHERE status IN ('pending', 'failed')
       ORDER BY id ASC
       LIMIT ?`,
      [limit],
    ) as SyncOutboxEntry[]
  }

  hasPendingOutbox(table: string, recordId: number | string): boolean {
    const row = this._get(
      `SELECT 1 AS found FROM sync_outbox
       WHERE table_name = ? AND record_id = ? AND status IN ('pending', 'failed', 'sending')
       LIMIT 1`,
      [table, String(recordId)],
    )
    return Boolean(row)
  }

  markOutboxSending(ids: number[]): void {
    if (ids.length === 0) return
    const now = this._now()
    const placeholders = ids.map(() => '?').join(',')
    this._run(`UPDATE sync_outbox SET status = 'sending', updated_at = ? WHERE id IN (${placeholders})`, [now, ...ids])
  }

  recoverInterruptedOutboxSending(): number {
    const count = Number(this._get("SELECT COUNT(*) AS count FROM sync_outbox WHERE status = 'sending'")?.count ?? 0)
    if (count > 0) {
      this._run("UPDATE sync_outbox SET status = 'pending', last_error = NULL, updated_at = ? WHERE status = 'sending'", [this._now()])
    }
    return count
  }

  markOutboxSynced(ids: number[], serverTime = this._now()): void {
    if (ids.length === 0) return
    const placeholders = ids.map(() => '?').join(',')
    const entries = this._all(`SELECT table_name, record_id FROM sync_outbox WHERE id IN (${placeholders})`, ids)
    const allowed = new Set([
      'categories', 'study_sessions', 'tasks', 'habits', 'habit_checkins', 'goals',
      'rewards', 'external_rewards', 'reward_config', 'huawei_sleep_data', 'system_config',
      'exercise_plan_versions', 'exercise_daily_logs', 'exercise_checkins', 'exercise_diet_checkins',
      'learning_objectives', 'learning_krs', 'learning_tasks',
    ])
    for (const entry of entries) {
      if (!allowed.has(String(entry.table_name))) continue
      const pk = entry.table_name === 'system_config' ? 'key' : 'id'
      this._run(`UPDATE ${entry.table_name} SET pushed_at = ? WHERE ${pk} = ?`, [serverTime, entry.record_id])
    }
    this._run(`UPDATE sync_outbox SET status = 'synced', updated_at = ?, last_error = NULL WHERE id IN (${placeholders})`, [serverTime, ...ids])
  }

  markOutboxFailed(ids: number[], error: string): void {
    if (ids.length === 0) return
    const now = this._now()
    const placeholders = ids.map(() => '?').join(',')
    this._run(
      `UPDATE sync_outbox
       SET status = 'failed', retry_count = retry_count + 1, last_error = ?, updated_at = ?
       WHERE id IN (${placeholders})`,
      [error, now, ...ids],
    )
  }

  getLastServerVersion(): number {
    const row = this._get("SELECT value FROM client_sync_state WHERE key = 'last_server_version'")
    const parsed = Number(row?.value ?? 0)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
  }

  setLastServerVersion(version: number): void {
    const safeVersion = Math.max(0, Math.trunc(Number(version) || 0))
    const now = this._now()
    this._run(
      `INSERT INTO client_sync_state (key, value, description, updated_at)
       VALUES ('last_server_version', ?, '客户端最后成功应用的服务端版本号', ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
      [String(safeVersion), now],
    )
  }

  getLedgerSnapshotVersion(): number {
    const row = this._get("SELECT value FROM client_sync_state WHERE key = 'ledger_snapshot_version'")
    const parsed = Number(row?.value ?? 0)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
  }

  hasConsistentLedgerSnapshot(): boolean {
    const saved = this._get("SELECT value FROM client_sync_state WHERE key = 'ledger_snapshot_reconciliation'")?.value
    try {
      const expected = JSON.parse(String(saved || '')).facts
      const rows = this._all('SELECT id, amount FROM reward_ledger ORDER BY id') as Array<{ id: string; amount: number }>
      const facts = rows.reduce((summary, row) => ({ ...summary, balance: summary.balance + Number(row.amount), income: summary.income + Math.max(Number(row.amount), 0), expense: summary.expense + Math.max(-Number(row.amount), 0) }), { count: rows.length, ids: rows.map(row => String(row.id)).sort().join(','), balance: 0, income: 0, expense: 0 })
      return ['count', 'ids', 'balance', 'income', 'expense'].every(key => expected?.[key] === facts[key as keyof typeof facts])
    } catch { return false }
  }

  /** 按表名 + 任意唯一键 查询单条记录 */
  getRecordByUnique(table: string, key: string, value: any): Record<string, any> | undefined {
    return this._get(`SELECT * FROM ${table} WHERE ${key} = ?`, [value])
  }

  /** 暴露 run 给 SyncWorker（INSERT OR REPLACE 用） */
  runRaw(sql: string, params: any[] = []): void {
    this._run(sql, params)
  }

  runInTransaction(fn: () => void): void {
    this._db.run('BEGIN')
    try {
      fn()
      this._db.run('COMMIT')
    } catch (error) {
      this._db.run('ROLLBACK')
      throw error
    }
  }

  applyChecklistResetMarker(marker: string): Record<string, number | boolean> {
    const markerKey = 'checklist_ticktick_reset_marker'
    const empty = { applied: false, tasks: 0, habits: 0, checkins: 0, rewards: 0, outbox: 0, wallets: 0 }
    if (!marker || this.getConfig(markerKey) === marker) return empty
    const imported = "COALESCE(raw_json, '') != ''"
    const importedCheckin = `(${imported} OR habit_id IN (SELECT id FROM habits WHERE ${imported}))`
    const derived = `(source_type='task_complete' AND source_id IN (SELECT id FROM tasks WHERE ${imported}))
      OR (source_type IN ('habit_checkin','habit_fail') AND (source_id IN (SELECT id FROM habits WHERE ${imported})
      OR source_id IN (SELECT id FROM habit_checkins WHERE ${imported})))`
    const counts = {
      applied: true,
      tasks: Number(this._get(`SELECT COUNT(*) count FROM tasks WHERE ${imported}`)?.count ?? 0),
      habits: Number(this._get(`SELECT COUNT(*) count FROM habits WHERE ${imported}`)?.count ?? 0),
      checkins: Number(this._get(`SELECT COUNT(*) count FROM habit_checkins WHERE ${importedCheckin}`)?.count ?? 0),
      rewards: Number(this._get(`SELECT COUNT(*) count FROM reward_ledger WHERE ${derived}`)?.count ?? 0),
      outbox: Number(this._get("SELECT COUNT(*) count FROM sync_outbox WHERE table_name IN ('tasks','habits','habit_checkins') AND status IN ('pending','failed','sending')")?.count ?? 0),
      wallets: Number(this._get('SELECT COUNT(*) count FROM user_wallets')?.count ?? 0),
    }
    this.runInTransaction(() => {
      this._run(`DELETE FROM reward_ledger WHERE ${derived}`)
      this._run("DELETE FROM sync_outbox WHERE table_name IN ('tasks','habits','habit_checkins') AND status IN ('pending','failed','sending')")
      this._run(`DELETE FROM habit_checkins WHERE ${importedCheckin}`)
      this._run(`DELETE FROM tasks WHERE ${imported}`)
      this._run(`DELETE FROM habits WHERE ${imported}`)
      this._run('DELETE FROM user_wallets')
      this._run(`INSERT INTO system_config (key,value,description,updated_at) VALUES (?,?,'清单缓存重置世代',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,description=excluded.description,updated_at=excluded.updated_at`, [markerKey, marker, this._now()])
    })
    return counts
  }

  /** 暴露全部查询给外部 Hook 用 */
  allRaw(sql: string, params: any[] = []): Record<string, any>[] {
    return this._all(sql, params)
  }

  /** 主动触发单个记录的同步队列 */
  enqueueSync(table: string, id: number | string): void {
    const allowed = new Set(['learning_objectives', 'learning_krs', 'learning_tasks'])
    if (allowed.has(table)) {
      const row = this.getRecordById(table, id)
      if (row && !this.hasPendingOutbox(table, id)) {
        this._enqueueOutbox(table, id, 'upsert', row, row.pushed_at ?? null)
      }
    }
    this._enqueueFn?.(table, id as any)
  }

  /** 写操作后：标记 updated_at + 入队同步 */
  private _afterWrite(table: string, id: number | string): void {
    const now = this._now()
    const primaryKey = table === 'system_config' ? 'key' : 'id'
    this._run(`UPDATE ${table} SET updated_at = ?, pushed_at = NULL WHERE ${primaryKey} = ?`, [now, id])
    this._enqueueFn?.(table, id as any)
    if (isOutboxEnabledTable(table)) {
      const row = this.getRecordById(table, id)
      if (row) {
        const payload = table === 'flash_cards'
          ? { id: row.id, occurred_at: row.occurred_at, original_text: row.original_text,
              analysis_status: row.analysis_status, ...(row.deleted_at ? { deleted_at: row.deleted_at } : {}) }
          : row
        this._enqueueOutbox(table, id, 'upsert', payload, row.pushed_at ?? null)
      }
    }

    // 如果写入的是本地流水，我们需要同步增减配置中的本地 wallet_balance
    if (table === 'reward_ledger') {
      try {
        const ledger = this.getRecordById('reward_ledger', id);
        if (ledger) {
          const configVal = this.getConfig('wallet_balance');
          const currentBalance = configVal !== null ? Number(configVal) : 0;
          this.setConfig('wallet_balance', String(currentBalance + Number(ledger.amount)));
        }
      } catch (e) {
        // 忽略
      }
    }
  }

  // ======================== 分类 ========================
  // 临时兼容层：UI Hook -> Database 分类方法 -> categories SQL -> SyncWorker。
  // TODO(CHG-20260606-001后续)：迁移到 CategoryService/CategoryRepository，Database 只保留门面转发。

  getCategories(): Category[] {
    return this._all('SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order') as Category[]
  }

  previewCategoryNormalization(): CategoryNormalizationPreview[] {
    const groups = this._all(`SELECT name, id FROM categories WHERE is_active = 1 ORDER BY name COLLATE NOCASE, sort_order, id`)
      .reduce<Map<string, number[]>>((groups, row) => {
        const name = String(row.name).trim(); const entries = groups.get(name) ?? []
        entries.push(Number(row.id)); groups.set(name, entries); return groups
      }, new Map())
    return Array.from(groups.entries()).filter(([, ids]) => ids.length > 1).map(([name, ids]) => ({
        name, canonicalId: ids[0], duplicateIds: ids.slice(1),
        referenceCounts: Object.fromEntries(ids.map(id => [id, CATEGORY_REFERENCE_COLUMNS.reduce((count, [table, column]) =>
          count + Number(this._get(`SELECT COUNT(*) AS count FROM ${table} WHERE ${column} = ?`, [id])?.count ?? 0), 0)])),
      }))
  }

  normalizeDuplicateCategories(): CategoryNormalizationPreview[] {
    const preview = this.previewCategoryNormalization()
    this.runInTransaction(() => preview.forEach(({ canonicalId, duplicateIds }) => duplicateIds.forEach(duplicateId => {
      CATEGORY_REFERENCE_COLUMNS.forEach(([table, column]) => {
        this._run(`UPDATE ${table} SET ${column} = ? WHERE ${column} = ?`, [canonicalId, duplicateId])
      })
      this._run('UPDATE categories SET is_active = 0, updated_at = ? WHERE id = ?', [this._now(), duplicateId])
      this._afterWrite('categories', duplicateId)
    })))
    return preview
  }

  /** 将一组分类 ID 在同一事务中换位，避免占位迁移失败留下半成品引用。 */
  rekeyCategoryIds(moves: Array<{ localId: number; serverId: number }>): void {
    const validMoves = moves.map(({ localId, serverId }) => ({ from: Number(localId), to: Number(serverId) }))
      .filter(({ from, to }) => Number.isSafeInteger(from) && Number.isSafeInteger(to) && from > 0 && to > 0 && from !== to)
    if (!validMoves.length) return
    this.runInTransaction(() => validMoves.forEach(({ from, to }) => {
      const source = this._get('SELECT id FROM categories WHERE id = ?', [from])
      if (!source) return
      if (this._get('SELECT id FROM categories WHERE id = ?', [to])) throw new Error('category_id_rekey_target_exists')
      CATEGORY_REFERENCE_COLUMNS.forEach(([table, column]) => this._run(`UPDATE ${table} SET ${column} = ? WHERE ${column} = ?`, [to, from]))
      this._all("SELECT id,payload_json FROM sync_outbox WHERE table_name='categories' AND record_id=? AND status!='synced'", [String(from)]).forEach(row => {
        let payload = row.payload_json
        try { payload = JSON.stringify({ ...JSON.parse(String(payload)), id: to }) } catch { /* 保留原始负载 */ }
        this._run('UPDATE sync_outbox SET record_id=?,payload_json=?,updated_at=? WHERE id=?', [String(to), payload, this._now(), row.id])
      })
      this._run('UPDATE categories SET id = ? WHERE id = ?', [to, from])
    }))
  }

  /** 将本地分类与服务端权威 ID 对齐，同时保留所有引用这条分类的历史记录。 */
  rekeyCategoryId(localId: number, serverId: number): void {
    this.rekeyCategoryIds([{ localId, serverId }])
  }

  addCategory(name: string, icon: string, color: string, group: string): number {
    if (this._get('SELECT id FROM categories WHERE is_active = 1 AND LOWER(TRIM(name)) = LOWER(TRIM(?))', [name])) {
      throw new Error('分类名称已存在')
    }
    const now = this._now()
    const row = this._get('SELECT MAX(sort_order) as m FROM categories WHERE group_name = ?', [group])
    const nextOrder = ((row as any)?.m ?? 0) + 1
    this._run(
      `INSERT INTO categories (name, icon, color, group_name, sort_order, is_active, created_at, updated_at)
       VALUES (?,?,?,?,?,1,?,?)`,
      [name, icon, color, group, nextOrder, now, now],
    )
    const id = (this._get('SELECT last_insert_rowid() as id') as any).id as number
    this._afterWrite('categories', id)
    return id
  }

  updateCategory(id: number, fields: Partial<Category>): void {
    if (fields.name && this._get('SELECT id FROM categories WHERE is_active = 1 AND id != ? AND LOWER(TRIM(name)) = LOWER(TRIM(?))', [id, fields.name])) {
      throw new Error('分类名称已存在')
    }
    const now = this._now()
    const sets: string[] = ['updated_at = ?']
    const vals: any[] = [now]
    for (const [k, v] of Object.entries(fields)) {
      if (v !== undefined && k !== 'id') {
        sets.push(`${k} = ?`); vals.push(v)
      }
    }
    vals.push(id)
    this._run(`UPDATE categories SET ${sets.join(', ')} WHERE id = ?`, vals)
    this._afterWrite('categories', id)
  }

  deleteCategory(id: number): void {
    this._run('UPDATE categories SET is_active = 0, updated_at = ? WHERE id = ?', [this._now(), id])
    this._afterWrite('categories', id)
  }

  // ======================== 专注会话 ========================
  // 临时兼容层：useTimer/LogicEngine -> Database 会话方法 -> study_sessions SQL -> 同步队列。
  // TODO：迁移到 SessionService，避免计时结算、分类汇总和 SQL 继续混在 Database.ts。

  getSessionsByDate(date: string): SessionRec[] {
    return this._all(
      `SELECT s.*, c.name as category_name, c.color as category_color, c.group_name
       FROM study_sessions s LEFT JOIN categories c ON s.category_id = c.id
       WHERE s.date = ? ORDER BY s.start_time ASC`,
      [date],
    ) as SessionRec[]
  }

  getSessionById(id: number | string): SessionRec | undefined {
    return this._get(
      `SELECT s.*, c.name as category_name, c.color as category_color, c.group_name
       FROM study_sessions s LEFT JOIN categories c ON s.category_id = c.id
       WHERE s.id = ?`,
      [id],
    ) as SessionRec | undefined
  }

  getAvailableDates(limit = 90): string[] {
    return this._all(
      'SELECT DISTINCT date FROM study_sessions WHERE date IS NOT NULL ORDER BY date DESC LIMIT ?',
      [limit],
    ).map(r => r.date as string)
  }

  logSession(s: {
    startTime: string; endTime: string; netDurationMinutes: number; netDurationSeconds?: number
    date: string; dayOfWeek?: string; pauseCount?: number
    pauseReasons?: string; sessionSummary?: string; categoryId?: number | null
  }): number | string {
    const now = this._now()
    this._run(
      `INSERT INTO study_sessions (start_time, end_time, net_duration_minutes, net_duration_seconds, date, day_of_week,
       pause_count, pause_reasons, session_summary, category_id, updated_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
      [s.startTime, s.endTime, s.netDurationMinutes, s.netDurationSeconds ?? Math.max(0, Math.round(s.netDurationMinutes * 60)), s.date, s.dayOfWeek ?? '',
       s.pauseCount ?? 0, s.pauseReasons ?? '无', s.sessionSummary ?? '', s.categoryId ?? null, now],
    )
    const id = (this._get('SELECT last_insert_rowid() as id') as any).id as number | string
    this._afterWrite('study_sessions', id)
    return id
  }

  updateSession(id: number | string, fields: Partial<SessionRec>): void {
    const now = this._now()
    const existing = this.getRecordById('study_sessions', id) as SessionRec | undefined
    const normalizedFields = { ...fields }
    const businessDate = this._sessionBusinessDate(
      String(fields.start_time ?? existing?.start_time ?? ''),
      String(fields.end_time ?? existing?.end_time ?? ''),
      String(existing?.date ?? ''),
    )
    if (businessDate) normalizedFields.date = businessDate
    const sets: string[] = ['updated_at = ?']
    const vals: any[] = [now]
    for (const [k, v] of Object.entries(normalizedFields)) {
      if (v !== undefined && k !== 'id') { sets.push(`${k} = ?`); vals.push(v) }
    }
    vals.push(id)
    this._run(`UPDATE study_sessions SET ${sets.join(', ')} WHERE id = ?`, vals)
    this._afterWrite('study_sessions', id)
  }

  deleteSession(id: number | string): void {
    this._run('DELETE FROM study_sessions WHERE id = ?', [id])
  }

  // --- Flash Cards ---
  getFlashCards(dateStart: string, dateEnd: string): any[] {
    return this._all(
      `SELECT * FROM flash_cards
       WHERE occurred_at >= ? AND occurred_at < ? AND deleted_at IS NULL
       ORDER BY occurred_at ASC`,
      [dateStart, dateEnd]
    )
  }

  getFlashCard(id: string): any {
    return this._get('SELECT * FROM flash_cards WHERE id = ?', [id])
  }

  saveFlashCard(card: {
    id?: string; occurred_at: string; original_text: string;
    polished_text?: string | null; diary_mood?: string | null; diary_content?: string | null;
    analysis_status?: string; analysis_draft_id?: string | null
  }): string {
    const now = this._now()
    const id = card.id || crypto.randomUUID()
    const status = card.analysis_status || 'pending'
    const existing = this.getFlashCard(id)
    if (existing) {
      this._run(
        `UPDATE flash_cards SET occurred_at = ?, original_text = ?, polished_text = ?, diary_mood = ?, diary_content = ?, analysis_status = ?, analysis_draft_id = ?, updated_at = ? WHERE id = ?`,
        [card.occurred_at, card.original_text, card.polished_text ?? null, card.diary_mood ?? null, card.diary_content ?? null, status, card.analysis_draft_id ?? null, now, id]
      )
    } else {
      this._run(
        `INSERT INTO flash_cards (id, occurred_at, original_text, polished_text, diary_mood, diary_content, analysis_status, analysis_draft_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)`,
        [id, card.occurred_at, card.original_text, card.polished_text ?? null, card.diary_mood ?? null, card.diary_content ?? null, status, card.analysis_draft_id ?? null, now, now]
      )
    }
    this._afterWrite('flash_cards', id)
    return id
  }

  deleteFlashCard(id: string): void {
    const now = this._now()
    this._run('UPDATE flash_cards SET deleted_at = ?, analysis_status = ?, updated_at = ? WHERE id = ?', [now, 'done', now, id])
    this._afterWrite('flash_cards', id)
  }

  getFlashTaskRecommendations(flashCardIds: string[]): any[] {
    if (flashCardIds.length === 0) return []
    const placeholders = flashCardIds.map(() => '?').join(',')
    return this._all(`SELECT * FROM flash_task_recommendations WHERE flash_card_id IN (${placeholders}) ORDER BY flash_card_id,ordinal`, flashCardIds)
  }


  // --- Management Plans ---
  getManagementPlans(): any[] {
    return this._all('SELECT * FROM management_plans WHERE status != "deleted"')
  }

  getManagementPlan(id: string): any {
    return this._get('SELECT * FROM management_plans WHERE id = ?', [id])
  }

  getManagementPlanByKey(planKey: string): any {
    return this._get('SELECT * FROM management_plans WHERE plan_key = ?', [planKey])
  }

  saveManagementPlan(plan: {
    id?: string; plan_key: string; title: string; active_revision_id?: string | null; status?: string;
  }): string {
    const now = this._now()
    const id = plan.id || crypto.randomUUID()
    const existing = this.getManagementPlan(id) || this.getManagementPlanByKey(plan.plan_key)
    const targetId = existing ? existing.id : id
    if (existing) {
      this._run(
        `UPDATE management_plans SET plan_key = ?, title = ?, active_revision_id = ?, status = ?, updated_at = ? WHERE id = ?`,
        [plan.plan_key, plan.title, plan.active_revision_id || existing.active_revision_id, plan.status || existing.status, now, targetId]
      )
    } else {
      this._run(
        `INSERT INTO management_plans (id, plan_key, title, active_revision_id, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)`,
        [targetId, plan.plan_key, plan.title, plan.active_revision_id || null, plan.status || 'active', now, now]
      )
    }
    return targetId
  }

  getManagementPlanRevisions(planId: string): any[] {
    return this._all('SELECT * FROM management_plan_revisions WHERE plan_id = ? ORDER BY created_at DESC', [planId])
  }

  saveManagementPlanRevision(rev: {
    id?: string; plan_id: string; config_json: string; logical_version: string;
  }): string {
    const now = this._now()
    const id = rev.id || crypto.randomUUID()
    this._run(
      `INSERT INTO management_plan_revisions (id, plan_id, config_json, logical_version, created_at) VALUES (?,?,?,?,?)`,
      [id, rev.plan_id, rev.config_json, rev.logical_version, now]
    )
    return id
  }

  /** 手动添加会话 */
  addManualSession(s: {
    startTime: string; endTime: string; netDurationMinutes: number
    date: string; dayOfWeek?: string; categoryId?: number | null; sessionSummary?: string
  }): number | string {
    const now = this._now()
    const businessDate = this._sessionBusinessDate(s.startTime, s.endTime, s.date)
    this._run(
      `INSERT INTO study_sessions (start_time, end_time, net_duration_minutes, date, day_of_week,
       pause_count, pause_reasons, session_summary, category_id, updated_at)
       VALUES (?,?,?,?,?,0,'手动添加',?,?,?)`,
      [s.startTime, s.endTime, s.netDurationMinutes, businessDate, s.dayOfWeek ?? '',
       s.sessionSummary ?? '', s.categoryId ?? null, now],
    )
    const id = (this._get('SELECT last_insert_rowid() as id') as any).id as number | string
    this._afterWrite('study_sessions', id)
    return id
  }

  /** 仅迁移早期手动记录，避免改写计时会话或已有正确业务日期。 */
  repairManualSessionBusinessDates(): number {
    const rows = this._all("SELECT id, start_time, end_time, date FROM study_sessions WHERE pause_reasons = '手动添加'")
    let repaired = 0
    for (const row of rows) {
      const businessDate = this._sessionBusinessDate(String(row.start_time), String(row.end_time), String(row.date ?? ''))
      if (businessDate && businessDate !== row.date) {
        this._run('UPDATE study_sessions SET date = ? WHERE id = ?', [businessDate, row.id])
        this._afterWrite('study_sessions', row.id)
        repaired += 1
      }
    }
    return repaired
  }

  // ======================== aTimeLogger 备份映射 ========================

  upsertATimeLoggerSegment(input: {
    localSessionId: number | string
    localSegmentKey?: string
    localCategoryId?: number | null
    atimeloggerTypeId?: string | null
    atimeloggerActivityId?: string | null
    atimeloggerIntervalId?: string | null
    remoteStatus?: string
    syncState?: string
    lastError?: string | null
  }): number {
    const now = this._now()
    const localSessionId = String(input.localSessionId)
    const segmentKey = input.localSegmentKey || `session:${localSessionId}`
    const existing = this._get(
      'SELECT id FROM atimelogger_segments WHERE local_session_id = ? AND local_segment_key = ?',
      [localSessionId, segmentKey],
    )

    if (existing) {
      this._run(
        `UPDATE atimelogger_segments
         SET local_category_id = ?, atimelogger_type_id = ?, atimelogger_activity_id = ?,
             atimelogger_interval_id = ?, remote_status = ?, sync_state = ?, last_error = ?, updated_at = ?
         WHERE id = ?`,
        [
          input.localCategoryId ?? null,
          input.atimeloggerTypeId ?? null,
          input.atimeloggerActivityId ?? null,
          input.atimeloggerIntervalId ?? null,
          input.remoteStatus || 'pending',
          input.syncState || 'pending_create',
          input.lastError ?? null,
          now,
          (existing as any).id,
        ],
      )
      return Number((existing as any).id)
    }

    this._run(
      `INSERT INTO atimelogger_segments (
         local_session_id, local_segment_key, local_category_id, atimelogger_type_id,
         atimelogger_activity_id, atimelogger_interval_id, remote_status, sync_state,
         last_error, created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        localSessionId,
        segmentKey,
        input.localCategoryId ?? null,
        input.atimeloggerTypeId ?? null,
        input.atimeloggerActivityId ?? null,
        input.atimeloggerIntervalId ?? null,
        input.remoteStatus || 'pending',
        input.syncState || 'pending_create',
        input.lastError ?? null,
        now,
        now,
      ],
    )
    const row = this._get(
      'SELECT id FROM atimelogger_segments WHERE local_session_id = ? AND local_segment_key = ?',
      [localSessionId, segmentKey],
    ) as any
    return Number(row.id)
  }

  getATimeLoggerSegmentsForSession(localSessionId: number | string): ATimeLoggerSegment[] {
    return this._all(
      'SELECT * FROM atimelogger_segments WHERE local_session_id = ? ORDER BY id ASC',
      [String(localSessionId)],
    ) as ATimeLoggerSegment[]
  }

  getATimeLoggerPendingSegments(): ATimeLoggerSegment[] {
    return this._all(
      `SELECT * FROM atimelogger_segments
       WHERE sync_state LIKE 'pending_%' OR sync_state = 'failed'
       ORDER BY local_session_id ASC, id ASC`,
    ) as ATimeLoggerSegment[]
  }

  getATimeLoggerSegment(localSessionId: number | string, segmentKey: string): ATimeLoggerSegment | undefined {
    return this._get(
      'SELECT * FROM atimelogger_segments WHERE local_session_id = ? AND local_segment_key = ?',
      [String(localSessionId), segmentKey],
    ) as ATimeLoggerSegment | undefined
  }

  getATimeLoggerSegmentByRemote(activityId: string, intervalId?: string | null): ATimeLoggerSegment | undefined {
    if (intervalId) {
      return this._get(
        'SELECT * FROM atimelogger_segments WHERE atimelogger_activity_id = ? AND atimelogger_interval_id = ?',
        [activityId, intervalId],
      ) as ATimeLoggerSegment | undefined
    }
    return this._get(
      'SELECT * FROM atimelogger_segments WHERE atimelogger_activity_id = ?',
      [activityId],
    ) as ATimeLoggerSegment | undefined
  }

  markATimeLoggerSegmentError(localSessionId: number | string, error: string, segmentKey?: string): void {
    const key = segmentKey || `session:${String(localSessionId)}`
    const existing = this._get(
      'SELECT id FROM atimelogger_segments WHERE local_session_id = ? AND local_segment_key = ?',
      [String(localSessionId), key],
    )
    if (!existing) {
      this.upsertATimeLoggerSegment({
        localSessionId,
        localSegmentKey: key,
        syncState: 'failed',
        remoteStatus: 'pending',
        lastError: error,
      })
      return
    }
    this._run(
      'UPDATE atimelogger_segments SET sync_state = ?, last_error = ?, updated_at = ? WHERE id = ?',
      ['failed', error, this._now(), (existing as any).id],
    )
  }

  markATimeLoggerSegmentState(localSessionId: number | string, segmentKey: string, syncState: string, remoteStatus = 'pending', error: string | null = null): void {
    const existing = this.getATimeLoggerSegment(localSessionId, segmentKey)
    if (!existing) {
      this.upsertATimeLoggerSegment({
        localSessionId,
        localSegmentKey: segmentKey,
        syncState,
        remoteStatus,
        lastError: error,
      })
      return
    }
    this._run(
      'UPDATE atimelogger_segments SET sync_state = ?, remote_status = ?, last_error = ?, updated_at = ? WHERE id = ?',
      [syncState, remoteStatus, error, this._now(), existing.id],
    )
  }

  deleteATimeLoggerSegment(localSessionId: number | string, segmentKey: string): void {
    this._run(
      'DELETE FROM atimelogger_segments WHERE local_session_id = ? AND local_segment_key = ?',
      [String(localSessionId), segmentKey],
    )
  }

  deleteATimeLoggerSegmentsForSession(localSessionId: number | string): void {
    this._run('DELETE FROM atimelogger_segments WHERE local_session_id = ?', [String(localSessionId)])
  }

  // ======================== 任务 (清单/TickTick) ========================
  // 临时兼容层：useChecklist/SyncWorker -> Database 任务方法 -> tasks/external_rewards/reward_ledger SQL。
  // TODO：迁移到 TaskService，并与 TickTick 同步、金币奖励幂等键统一。

  getActiveTasks(): Record<string, any>[] {
    return this._all(
      `SELECT t.*, c.name as category_name
       FROM tasks t LEFT JOIN categories c ON t.category_id = c.id
       WHERE t.status = 0 AND t.deleted_at IS NULL
       ORDER BY t.priority DESC, t.due_date ASC`,
    )
  }

  getChecklistTasks(date?: string): Record<string, any>[] {
    console.log('=== Database.getChecklistTasks ===')
    
    if (date) {
      // 如果指定了日期，查询该日期的任务
      console.log('查询日期:', date)
      const result = this._all(
        `SELECT t.*, c.name as category_name
         FROM tasks t LEFT JOIN categories c ON t.category_id = c.id
         WHERE t.due_date = ? AND t.deleted_at IS NULL
         ORDER BY t.status ASC, t.priority DESC`,
        [date]
      )
      console.log('查询结果数量:', result.length)
      console.log('SQL:', `SELECT * FROM tasks WHERE due_date = '${date}'`)
      return result
    } else {
      // 如果未指定日期，返回所有任务
      console.log('查询所有任务（无日期过滤）')
      const result = this._all(
        `SELECT t.*, c.name as category_name
         FROM tasks t LEFT JOIN categories c ON t.category_id = c.id
         WHERE t.deleted_at IS NULL
         ORDER BY t.due_date DESC, t.status ASC, t.priority DESC`
      )
      console.log('查询结果数量:', result.length)
      return result
    }
  }

  addTask(title: string, dueDate = ''): string {
    const now = this._now()
    const normalizedTitle = title.trim()
    if (!normalizedTitle) throw new Error('任务标题不能为空')
    const localId = 'local_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    const normalizedDueDate = dueDate ? normalizeShanghaiDateTime(dueDate) : now.slice(0, 10)
    this._run(
      `INSERT INTO tasks (id, title, priority, status, due_date, source, updated_at)
       VALUES (?, ?, 0, 0, ?, 'local', ?)`,
      [localId, normalizedTitle, normalizedDueDate, now],
    )
    this._afterWrite('tasks', localId)
    return localId
  }

  updateTaskStatus(id: string | number, status: number): void {
    const now = this._now()
    this._run('UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?', [status, now, id])
    this._afterWrite('tasks', id)
  }

  updateTaskPriority(id: string | number, priority: number): void {
    this._run('UPDATE tasks SET priority = ?, updated_at = ? WHERE id = ?', [priority, this._now(), id])
    this._afterWrite('tasks', id)
  }

  upsertTask(task: Record<string, any>): void {
    const normalizedTask = normalizeTaskTimeFields(task)
    const dueDate = normalizedTask.due_date ?? ''
    const startDate = resolveChecklistSyncStartDate(this.getConfig('statistics_start_date') || this.getConfig('checklist_sync_start_date')).date
    if (!dueDate || dueDate < startDate) return
    const now = this._now()
    const taskId = normalizedTask.id || normalizedTask.ticktick_id
    const existing = this._get('SELECT id, status FROM tasks WHERE id = ?', [taskId])
    if (existing) {
      const id = (existing as any).id
      const localStatus = (existing as any).status as number
      // 防降级：本地已完成(status=2)不接受远端活跃(status=0)覆盖
      let status = normalizedTask.status ?? 0
      if (localStatus === 2 && status === 0) status = 2
      this._run(
        `UPDATE tasks SET title=?, priority=?, status=?, due_date=?, tags=?, raw_json=?, updated_at=?
         WHERE id=?`,
        [normalizedTask.title, normalizedTask.priority ?? 0, status, normalizedTask.due_date ?? '', JSON.stringify(normalizedTask.tags ?? []), JSON.stringify(normalizedTask),
         now, id],
      )
      this._afterWrite('tasks', id)
    } else {
      this._run(
        `INSERT INTO tasks (id, title, priority, status, due_date, tags, raw_json, updated_at)
         VALUES (?,?,?,?,?,?,?,?)`,
        [taskId, normalizedTask.title, normalizedTask.priority ?? 0, normalizedTask.status ?? 0,
         normalizedTask.due_date ?? '', JSON.stringify(normalizedTask.tags ?? []),
         JSON.stringify(normalizedTask), now],
      )
      this._afterWrite('tasks', taskId)
    }
  }

  deleteTask(id: string | number): void {
    const existing = this.getRecordById('tasks', id)
    const now = this._now()
    if (existing) {
      this._run('UPDATE tasks SET deleted_at = ?, updated_at = ?, pushed_at = NULL WHERE id = ?', [now, now, id])
      const tombstone = { ...existing, deleted_at: now, updated_at: now, pushed_at: null }
      this._enqueueOutbox('tasks', id, 'delete', tombstone, existing.pushed_at ?? null)
    }
    this._enqueueFn?.('tasks', id as any)
  }

  // ======================== 习惯 ========================

  getHabits(): Habit[] {
    // is_active = 0 表示正常（与 TickTick 一致），is_active = 1 表示归档
    return this._all('SELECT * FROM habits WHERE is_active = 0 ORDER BY sort_order') as Habit[]
  }

  addHabit(name: string, icon = '✅', difficulty = 'easy'): string {
    const now = this._now()
    const normalizedName = name.trim()
    if (!normalizedName) throw new Error('习惯名称不能为空')
    const row = this._get('SELECT MAX(sort_order) as m FROM habits')
    const order = ((row as any)?.m ?? 0) + 1
    const localId = 'local_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    this._run(
      `INSERT INTO habits (id, name, icon, color, sort_order, is_active, difficulty, source, created_at, updated_at)
       VALUES (?,?,?,'#A3BE8C',?,0,?, 'local', ?,?)`,  // is_active = 0 表示正常
      [localId, normalizedName, icon, order, difficulty, now, now],
    )
    this._afterWrite('habits', localId)
    return localId
  }

  updateHabit(id: string | number, fields: Partial<Habit>): void {
    const now = this._now()
    const sets: string[] = ['updated_at = ?']
    const vals: any[] = [now]
    for (const [k, v] of Object.entries(fields)) {
      if (v !== undefined && k !== 'id') { sets.push(`${k} = ?`); vals.push(v) }
    }
    vals.push(id)
    this._run(`UPDATE habits SET ${sets.join(', ')} WHERE id = ?`, vals)
    this._afterWrite('habits', id)
  }

  deleteHabit(id: string | number): void {
    // is_active = 1 表示归档（与 TickTick 一致）
    this._run('UPDATE habits SET is_active = 1, updated_at = ? WHERE id = ?', [this._now(), id])
    this._afterWrite('habits', id)
  }

  /** 按 TickTick ID 查找本地习惯 */
  getHabitByTickTickId(ttId: string): Habit | undefined {
    const row = this._get("SELECT * FROM habits WHERE id = ? OR name = ?", [ttId, ttId])
    return row as Habit | undefined
  }

  /** TickTick 习惯落库（INSERT OR REPLACE） */
  upsertHabit(habit: { id: string; name: string; status: number; sortOrder: number; icon?: string; repeat_rule?: string; color?: string }): string {
    console.log('=== Database.upsertHabit ===')
    console.log('习惯ID:', habit.id)
    console.log('习惯名称:', habit.name)
    console.log('TickTick status:', habit.status, '(0=正常, 1=归档)')
    console.log('sortOrder:', habit.sortOrder)
    console.log('repeat_rule:', habit.repeat_rule)
    
    const now = this._now()
    const existing = this._get(
      "SELECT id FROM habits WHERE id = ?",
      [habit.id],
    )
    const icon = habit.icon || '🎯'
    const color = habit.color || '#A3BE8C'
    // ✅ 现在直接使用 TickTick 的 status 值（0=正常，1=归档）
    const isActive = habit.status
    
    console.log('数据库 is_active 值:', isActive)
    
    if (existing) {
      const hid = (existing as any).id
      console.log('更新已有习惯:', hid)
      this._run(
        'UPDATE habits SET name=?, sort_order=?, is_active=?, icon=?, repeat_rule=?, color=?, updated_at=? WHERE id=?',
        [habit.name, habit.sortOrder, isActive, icon, habit.repeat_rule || null, color, now, hid],
      )
      this._afterWrite('habits', hid)
      return hid
    } else {
      console.log('插入新习惯')
      this._run(
        `INSERT INTO habits (id, name, icon, color, sort_order, is_active, difficulty, repeat_rule, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, 'easy', ?, ?, ?)`,
        [habit.id, habit.name, icon, color, habit.sortOrder, isActive, habit.repeat_rule || null, now, now],
      )
      this._afterWrite('habits', habit.id)
      return habit.id
    }
  }


  /** 写入 TickTick 打卡记录（INSERT OR IGNORE 防重复） */
  upsertHabitCheckin(habitId: string | number, checkinDate: string, status: number): void {
    const startDate = resolveChecklistSyncStartDate(this.getConfig('statistics_start_date') || this.getConfig('checklist_sync_start_date')).date
    if (checkinDate < startDate) return
    const now = this._now()
    const existing = this._get(
      'SELECT id FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?',
      [habitId, checkinDate],
    )
    const habit = this._get('SELECT name FROM habits WHERE id = ?', [habitId])
    const habitName = (habit as any)?.name ?? null

    if (existing) {
      this._run(
        'UPDATE habit_checkins SET status = ?, updated_at = ?, habit_name = ? WHERE id = ?',
        [status, now, habitName, (existing as any).id],
      )
    } else {
      const checkinId = 'checkin_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
      this._run(
        'INSERT INTO habit_checkins (id, habit_id, habit_name, date, created_at, checkin_date, checkin_time, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [checkinId, habitId, habitName, checkinDate, now, checkinDate, now, status, now],
      )
    }
  }

  /** 真实连续打卡天数 */
  getRealStreak(habitId: string | number): number {
    const rows = this._all(
      'SELECT checkin_date, status FROM habit_checkins WHERE habit_id = ? ORDER BY checkin_date DESC',
      [habitId],
    )
    let streak = 0
    const today = this._localToday()
    let expected = this._parseLocalDate(today)
    for (const r of rows) {
      const rec = r as any
      if (rec.status !== 2) continue // 只计完成状态
      const d = rec.checkin_date
      const diff = Math.floor((expected.getTime() - this._parseLocalDate(d).getTime()) / 86400000)
      if (diff === 0 || diff === 1) {
        streak++
        expected = this._parseLocalDate(d)
      } else {
        break
      }
    }
    return streak
  }

  /** 本周打卡状态 [mon...sun] */
  getWeeklyCheckins(habitId: string | number, weekStart: string): number[] {
    const result: number[] = []
    const start = this._parseLocalDate(weekStart)
    const formatYYYYMMDD = (d: Date) => {
      const year = d.getFullYear()
      const month = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${year}-${month}-${day}`
    }
    for (let i = 0; i < 7; i++) {
      const d = new Date(start.getTime())
      d.setDate(start.getDate() + i)
      const ds = formatYYYYMMDD(d)
      const row = this._get(
        'SELECT status FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?',
        [habitId, ds],
      )
      result.push(row ? (row as any).status : 0)
    }
    return result
  }

  toggleCheckin(habitId: string | number, date: string, forceStatus?: number): { status: number; coins: number } {
    const now = this._now()
    const existing = this._get(
      'SELECT id, status FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?',
      [habitId, date],
    )

    const habit = this._get('SELECT name, difficulty, color FROM habits WHERE id = ?', [habitId])
    const habitName = (habit as any)?.name ?? null

    let checkinId: string | number
    let newStatus: number
    if (existing) {
      const currStatus = (existing as any).status as number
      if (forceStatus !== undefined) {
        if (currStatus === forceStatus) {
          this._run('DELETE FROM habit_checkins WHERE id = ?', [(existing as any).id])
          newStatus = 0
        } else {
          this._run('UPDATE habit_checkins SET status = ?, updated_at = ?, habit_name = ? WHERE id = ?', [forceStatus, now, habitName, (existing as any).id])
          newStatus = forceStatus
        }
      } else {
        if (currStatus === 2) {
          this._run('DELETE FROM habit_checkins WHERE id = ?', [(existing as any).id])
          newStatus = 0
        } else {
          this._run('UPDATE habit_checkins SET status = 2, updated_at = ?, habit_name = ? WHERE id = ?', [now, habitName, (existing as any).id])
          newStatus = 2
        }
      }
      checkinId = (existing as any).id
    } else {
      const status = forceStatus !== undefined ? forceStatus : 2
      const localId = 'checkin_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
      this._run(
        'INSERT INTO habit_checkins (id, habit_id, habit_name, date, created_at, checkin_date, checkin_time, status, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
        [localId, habitId, habitName, date, now, date, now, status, now],
      )
      checkinId = localId
      newStatus = status
    }

    this._afterWrite('habit_checkins', checkinId)

    return { status: newStatus, coins: 0 }
  }

  getTodayCheckins(date: string): HabitCheckin[] {
    return this._all('SELECT * FROM habit_checkins WHERE checkin_date = ?', [date]) as HabitCheckin[]
  }

  // ======================== 目标 ========================
  // 临时兼容层：useGoals -> Database 目标方法 -> goals/reward_ledger/external_rewards SQL。
  // TODO：迁移到 GoalService，目标结算和奖励领取应与 RewardLedgerService 共用事务入口。

  getGoals(): Goal[] {
    const goals = this._all('SELECT * FROM goals WHERE is_active = 1') as Goal[]
    if (goals.length === 0) return goals
    const bindings = this._all('SELECT goal_id, category_id FROM goal_category_bindings') as Array<{ goal_id: string; category_id: number }>
    const byGoal = new Map<string, number[]>()
    for (const binding of bindings) {
      const ids = byGoal.get(String(binding.goal_id)) ?? []
      ids.push(Number(binding.category_id))
      byGoal.set(String(binding.goal_id), ids)
    }
    return goals.map(goal => ({
      ...goal,
      category_ids: byGoal.get(String(goal.id)) ?? (goal.category_id == null ? [] : [goal.category_id]),
    }))
  }

  addGoal(g: Omit<Goal, 'id'>): number {
    const now = this._now()
    this._run(
      `INSERT INTO goals (title, category_id, metric, target_value, period, reward_coins, reward_id, operator, penalty_coins, is_active, created_at, updated_at)
       VALUES (?,?,?,?,?,?,?,?,?,1,?,?)`,
      [g.title, g.category_id, g.metric, g.target_value, g.period,
       g.reward_coins, g.reward_id ?? null, g.operator ?? '>=', g.penalty_coins ?? g.reward_coins, now, now],
    )
    const id = (this._get('SELECT last_insert_rowid() as id') as any).id as number
    this._afterWrite('goals', id)
    return id
  }

  updateGoal(id: number, fields: Partial<Goal>): void {
    const now = this._now()
    const sets: string[] = ['updated_at = ?']
    const vals: any[] = [now]
    for (const [k, v] of Object.entries(fields)) {
      if (v !== undefined && k !== 'id') { sets.push(`${k} = ?`); vals.push(v) }
    }
    vals.push(id)
    this._run(`UPDATE goals SET ${sets.join(', ')} WHERE id = ?`, vals)
    this._afterWrite('goals', id)
  }

  deleteGoal(id: number | string): void {
    this._run('UPDATE goals SET is_active = 0, updated_at = ? WHERE id = ?', [this._now(), id])
    this._afterWrite('goals', id)
  }

  deleteLedgerEntry(id: number | string): boolean {
    return this._rewardLedgerService.deleteLedgerEntry(id)
  }

  // ======================== 奖励商店 ========================

  getBalance(): number {
    return this._rewardLedgerService.getBalance()
  }

  getLedgerSummary(): LedgerSummary {
    return this._rewardLedgerService.getLedgerSummary()
  }

  getRewards(): Reward[] {
    const now = this._now()
    return this._all(`SELECT r.*,
      COALESCE((SELECT SUM(f.progress_units-f.consumed_units) FROM reward_fragments f
        WHERE f.reward_id=CAST(r.id AS TEXT) AND f.status='active' AND f.expires_at>?),0) AS fragment_progress_units,
      COALESCE((SELECT COUNT(*) FROM reward_ledger l WHERE l.source_type='reward_buy'
        AND (l.source_id LIKE CAST(r.id AS TEXT)||':%' OR l.source_id LIKE 'unlock:'||CAST(r.id AS TEXT)||':%')
        AND ((r.inventory_mode='daily' AND l.target_date=?) OR (r.inventory_mode='monthly' AND substr(l.target_date,1,7)=?))),0) AS inventory_used
      FROM rewards r WHERE r.is_active=1`, [now, now.slice(0, 10), now.slice(0, 7)]) as Reward[]
  }

  addReward(title: string, icon = '🎁', price = 10, description = '', unlockTaskId: string | null = null, unlockTaskTitle: string | null = null): number {
    const now = this._now()
    this._run(
      `INSERT INTO rewards (title, icon, price, description, unlock_task_id, unlock_task_title, is_active, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)`,
      [title, icon, price, description, unlockTaskId, unlockTaskTitle, now, now],
    )
    const id = (this._get('SELECT last_insert_rowid() as id') as any).id as number
    this._afterWrite('rewards', id)
    return id
  }

  updateReward(id: number | string, title: string, icon = '🎁', price = 10, description = '', unlockTaskId: string | null = null, unlockTaskTitle: string | null = null): void {
    const now = this._now()
    this._run(
      `UPDATE rewards
       SET title = ?, icon = ?, price = ?, description = ?, unlock_task_id = ?, unlock_task_title = ?, updated_at = ?
       WHERE id = ?`,
      [title, icon, price, description, unlockTaskId, unlockTaskTitle, now, id],
    )
    this._afterWrite('rewards', id)
  }

  getHabitById(id: number | string): Habit | undefined {
    return this._get("SELECT * FROM habits WHERE id = ?", [id]) as Habit | undefined
  }

  getCheckin(habitId: number | string, date: string): Record<string, any> | undefined {
    return this._get('SELECT * FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?', [habitId, date])
  }

  buyReward(rewardId: number | string): boolean {
    const reward = this._get('SELECT * FROM rewards WHERE id = ? AND is_active = 1', [rewardId])
    if (!reward) throw new Error('奖励不存在')
    const unlockTaskId = (reward as any).unlock_task_id
    const unlockTaskTitle = (reward as any).unlock_task_title

    if (unlockTaskId) {
      const available = this.getAvailableUnlocks(unlockTaskId, rewardId)
      if (available <= 0) {
        throw new Error(`需要先完成条件「${unlockTaskTitle || '指定任务'}」才能兑换（或额度不足）！`)
      }
    }

    return true
  }


  getLedger(limit = 30): LedgerEntry[] {
    return this._rewardLedgerService.getLedger(limit)
  }

  /** 全量金币流水，支持分页 */
  getLedgerFull(limit = 50, offset = 0): LedgerEntry[] {
    return this._rewardLedgerService.getLedgerFull(limit, offset)
  }

  replaceServerLedgerSnapshot(snapshot: ServerLedgerSnapshot, version: number): { removed: number; balance: number } {
    const rows = Array.isArray(snapshot?.rows) ? snapshot.rows : []
    const expected = snapshot?.summary
    const ids = new Set(rows.map(row => String(row?.id ?? '')))
    const computed = rows.reduce((total, row) => {
      const amount = Number(row.amount)
      return { balance: total.balance + amount, income: total.income + Math.max(amount, 0), expense: total.expense + Math.max(-amount, 0) }
    }, { balance: 0, income: 0, expense: 0 })
    if (!expected || Number(snapshot?.integrity?.count) !== rows.length || !/^[a-f0-9]{64}$/i.test(snapshot?.integrity?.sha256 || '') || ids.size !== rows.length || ids.has('') || ![computed.balance, computed.income, computed.expense].every(Number.isFinite)
      || ['balance', 'income', 'expense'].some(key => Math.abs(computed[key as keyof typeof computed] - Number(expected[key as keyof typeof expected])) > 0.000001)) {
      throw new Error('invalid_server_ledger_snapshot')
    }
    const removed = Number(this._get('SELECT COUNT(*) AS count FROM reward_ledger')?.count ?? 0)
    const fragments = Array.isArray(snapshot.reward_fragments) ? snapshot.reward_fragments : []
    const fragmentIds = new Set(fragments.map(row => String(row?.id ?? '')))
    if (fragmentIds.size !== fragments.length || fragmentIds.has('')) throw new Error('invalid_server_reward_fragment_snapshot')
    const facts = { count: rows.length, ids: [...ids].sort().join(','), balance: computed.balance, income: computed.income, expense: computed.expense }
    this.runInTransaction(() => {
      this._run('DELETE FROM reward_ledger')
      this._run("DELETE FROM sync_outbox WHERE table_name = 'reward_ledger' AND status IN ('pending', 'failed', 'sending')")
      for (const row of rows) this._run(
        `INSERT INTO reward_ledger (id, amount, source_type, source_id, description, target_date, occurred_at, created_at, updated_at, pushed_at, pulled_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)` ,
        [row.id, row.amount, row.source_type, row.source_id ?? null, row.description ?? '', row.target_date ?? '', row.occurred_at ?? null, row.created_at ?? this._now(), row.updated_at ?? this._now(), this._now()],
      )
      this._run('DELETE FROM reward_fragments')
      for (const row of fragments) this._run(
        `INSERT INTO reward_fragments
           (id,reward_id,source_type,source_id,completion_event_key,rule_version,progress_units,consumed_units,issued_at,expires_at,status,compose_batch_id,created_at,updated_at,pulled_at)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
        [row.id, row.reward_id, row.source_type, row.source_id, row.completion_event_key,
          row.rule_version, row.progress_units ?? 100, row.consumed_units ?? 0, row.issued_at, row.expires_at, row.status, row.compose_batch_id ?? null,
          row.created_at, row.updated_at, this._now()],
      )
      const now = this._now()
      this._run(`INSERT INTO system_config (key,value,description,updated_at) VALUES ('wallet_balance',?,'服务端权威金币余额',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,description=excluded.description,updated_at=excluded.updated_at`, [String(expected.balance), now])
      this._run(`INSERT INTO client_sync_state (key,value,description,updated_at) VALUES ('ledger_snapshot_version',?,'服务端权威金币账本快照版本',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at`, [String(Math.max(0, Math.trunc(version))), now])
      this._run(`INSERT INTO client_sync_state (key,value,description,updated_at) VALUES ('ledger_snapshot_reconciliation',?,'金币账本收敛摘要',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at`, [JSON.stringify({ removed, facts }), now])
      this._run(`INSERT INTO client_sync_state (key,value,description,updated_at) VALUES ('reward_rebuild_epoch',?,'金币重建代次',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at`, [String(Math.max(0, Math.trunc(Number(snapshot.epoch) || 0))), now])
    })
    return { removed, balance: expected.balance }
  }

  addLedgerEntry(amount: number, sourceType: string, sourceId?: number | string, description?: string, targetDate?: string): string {
    return this._rewardLedgerService.addLedgerEntry(amount, sourceType, sourceId, description, targetDate)
  }

  /** 将旧格式流水迁移到新格式：√/× 任务/习惯/目标 [补卡]名称 MM-DD */
  migrateLedgerFormat(): number {
    const rows = this._all('SELECT id, source_type, description, amount, created_at, target_date FROM reward_ledger')
    let migrated = 0
    for (const row of rows) {
      const r = row as any
      const desc = (r.description || '').trim()
      const type = r.source_type || ''
      const createdAt = r.created_at || ''
      const currentTargetDate = r.target_date

      // 1. 尝试从原 description 尾部提取日期 (MM-DD 或 YYYY-MM-DD)
      let extractedDate = ''
      const m = desc.match(/\s+(\d{2}-\d{2})$/)
      if (m) {
        const year = createdAt ? createdAt.slice(0, 4) : new Date().getFullYear().toString()
        extractedDate = `${year}-${m[1]}`
      } else {
        const mFull = desc.match(/\s+(\d{4}-\d{2}-\d{2})$/)
        if (mFull) {
          extractedDate = mFull[1]
        }
      }

      // 如果有提取的日期，使用它。否则用 created_at 的前10位。
      const targetDateVal = extractedDate || (createdAt ? createdAt.slice(0, 10) : this._localToday())

      // 2. 清洗描述，彻底洗白 description
      // 去除开头 "√ 习惯", "× 任务" 等前缀
      let newDesc = desc
        .replace(/^[√×✕❌]\s*(习惯|任务|目标)?\s*/, '')
        // 去除尾部 " 05-31" 或 " 2026-05-31" 等日期
        .replace(/\s+\d{2}-\d{2}$/, '')
        .replace(/\s+\d{4}-\d{2}-\d{2}$/, '')

      // 检查原先是不是补卡记录
      const hasMakeupKeyword = desc.includes('[补卡]') || desc.includes('补卡')
      if (hasMakeupKeyword) {
        if (extractedDate) {
          const baseDesc = newDesc.replace(/\[补卡\]/g, '').replace(/补卡/g, '').trim()
          newDesc = `[补卡]${baseDesc}`
        } else {
          newDesc = newDesc.replace(/\[补卡\]/g, '').replace(/补卡/g, '').trim()
        }
      }

      let isChanged = false
      if (newDesc !== desc) {
        isChanged = true
      }
      if (!currentTargetDate || currentTargetDate !== targetDateVal) {
        isChanged = true
      }

      if (isChanged) {
        this._run(
          'UPDATE reward_ledger SET description = ?, target_date = ? WHERE id = ?',
          [newDesc, targetDateVal, r.id]
        )
        migrated++
      }
    }
    return migrated
  }

  // ======================== 睡眠数据 ========================
  // 临时兼容层：useSleep -> Database 睡眠方法 -> huawei_sleep_data SQL -> SyncWorker。
  // TODO：迁移到 SleepDataService；这里暂时只做 CRUD 与 pushed_at 标记，不承接 UI 状态。

  getSleepData(date: string): SleepData | undefined {
    return this._get('SELECT * FROM huawei_sleep_data WHERE date = ?', [date]) as SleepData | undefined
  }

  getSleepHistory(days = 14): SleepData[] {
    const rows = this._all(
      'SELECT * FROM huawei_sleep_data ORDER BY date DESC LIMIT ?', [days],
    ) as SleepData[]
    return rows.reverse()
  }

  saveSleepData(date: string, data: Partial<SleepData>): void {
    const now = this._now()
    const incoming = { ...(data as Record<string, any>) }
    if (!date && incoming.sleep_date) date = String(incoming.sleep_date)
    const cleanData = Object.fromEntries(
      Object.entries(incoming).filter(([key, value]) =>
        value !== undefined && key !== 'id' && key !== 'date' && SLEEP_DATA_COLUMNS.has(key),
      ),
    )
    const existing = this._get('SELECT id, morning_diary, evening_diary FROM huawei_sleep_data WHERE date = ?', [date]) as Record<string, any> | undefined
    for (const type of ['morning', 'evening'] as const) {
      const contentKey = `${type}_diary`
      const writtenAtKey = `${contentKey}_written_at`
      if (contentKey in cleanData && cleanData[contentKey] !== existing?.[contentKey] && !(writtenAtKey in cleanData)) {
        cleanData[writtenAtKey] = String(cleanData[contentKey] || '').trim() ? now : null
      }
    }
    if (existing) {
      const sets: string[] = ['updated_at = ?']
      const vals: any[] = [now]
      for (const [k, v] of Object.entries(cleanData)) {
        if (k === 'updated_at') continue
        sets.push(`${k} = ?`); vals.push(v)
      }
      vals.push(date)
      this._run(`UPDATE huawei_sleep_data SET ${sets.join(', ')} WHERE date = ?`, vals)
    } else {
      const keys = Object.keys(cleanData).filter(k => k !== 'updated_at')
      const vals = keys.map(k => (cleanData as any)[k])
      const extraColumns = keys.length ? `, ${keys.join(', ')}` : ''
      const extraPlaceholders = keys.length ? `, ${keys.map(() => '?').join(', ')}` : ''
      this._run(
        `INSERT INTO huawei_sleep_data (date${extraColumns}, updated_at)
         VALUES (?${extraPlaceholders}, ?)`,
        [date, ...vals, now],
      )
    }
    const row = this._get('SELECT id FROM huawei_sleep_data WHERE date = ?', [date])
    if (row) this._afterWrite('huawei_sleep_data', (row as any).id)
  }

  saveSleepDiary(date: string, type: 'morning' | 'evening', content: string): { changeId: string; recordId: number | string } {
    const now = this._now()
    const field = `${type}_diary`; const writtenAtField = `${field}_written_at`
    let row = this._get('SELECT id FROM huawei_sleep_data WHERE date = ?', [date])
    if (row) {
      this._run(`UPDATE huawei_sleep_data SET ${field}=?,${writtenAtField}=?,updated_at=?,pushed_at=NULL WHERE id=?`,
        [content, content.trim() ? now : null, now, row.id])
    } else {
      this._run(`INSERT INTO huawei_sleep_data (date,${field},${writtenAtField},updated_at) VALUES (?,?,?,?)`,
        [date, content, content.trim() ? now : null, now])
      row = this._get('SELECT id FROM huawei_sleep_data WHERE date = ?', [date])
    }
    if (!row) throw new Error('sleep_diary_local_save_failed')
    this._enqueueFn?.('huawei_sleep_data', row.id as any)
    const payload = { id: row.id, date, [field]: content, [writtenAtField]: content.trim() ? now : null }
    return { changeId: this.createOutboxOperation('huawei_sleep_data', row.id, 'upsert', payload), recordId: row.id }
  }

  // ======================== 背包 ========================

  /** 背包：获取已兑换奖励列表 */
  getBackpackItems(): Record<string, any>[] {
    const rows = this._all(
      `SELECT rl.id, COALESCE(rw.icon, '🎁') AS icon, COALESCE(rw.title, '已下架奖励') AS title,
              rl.created_at, rl.description AS memo, rw.unlock_task_title, used.created_at AS used_at
       FROM reward_ledger rl
       LEFT JOIN rewards rw ON rl.source_id = rw.id OR rl.source_id LIKE rw.id || ':%'
       LEFT JOIN reward_ledger used ON used.source_type = 'backpack_use' AND used.source_id = rl.id
       WHERE rl.source_type = 'reward_buy'
       ORDER BY rl.created_at DESC`,
    )
    return rows.map(r => ({
      ...r,
      is_used: Boolean((r as any).used_at),
    }))
  }

  /** 背包：标记物品已使用 */
  markBackpackItemUsed(ledgerId: string | number): void {
    const row = this._get('SELECT description FROM reward_ledger WHERE id = ?', [ledgerId])
    if (!row) return
    const desc = (row as any).description || ''
    if (desc.includes('[已使用]')) return  // 幂等
    const newDesc = desc + ' [已使用]'
    this._run('UPDATE reward_ledger SET description = ? WHERE id = ?', [newDesc, ledgerId])
    this._afterWrite('reward_ledger', ledgerId)
  }

  /** 写入待领取奖励（INSERT OR IGNORE 防重复） */
  addExternalReward(extId: string, itemType: string, itemName: string, coins: number, status = 0): void {
    const now = this._now()
    const existing = this._get('SELECT id FROM external_rewards WHERE ext_id = ?', [extId]) as any
    if (existing) {
      this._run(
        'UPDATE external_rewards SET item_type = ?, item_name = ?, coins = ?, status = ?, updated_at = ? WHERE id = ?',
        [itemType, itemName, coins, status, now, existing.id]
      )
      this._afterWrite('external_rewards', existing.id)
    } else {
      const extUuid = 'ext_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
      this._run(
        `INSERT OR IGNORE INTO external_rewards (id, ext_id, item_type, item_name, coins, status, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        [extUuid, extId, itemType, itemName, coins, status, now, now],
      )
      this._afterWrite('external_rewards', extUuid)
    }
  }

  /** 获取待领取奖励列表 */
  getUnclaimedRewards(): Record<string, any>[] {
    return this._all('SELECT * FROM external_rewards WHERE status = 0')
  }


  /** 批量领取奖励，返回总金币数 */
  claimRewards(ids: string[]): number {
    if (ids.length === 0) return 0
    const now = this._now()
    const placeholders = ids.map(() => '?').join(',')
    const rows = this._all(
      `SELECT id, coins, item_type, item_name FROM external_rewards WHERE id IN (${placeholders}) AND status = 0`,
      ids,
    )
    let total = 0
    for (const r of rows) {
      const rec = r as any
      this._run('UPDATE external_rewards SET status = 1, updated_at = ? WHERE id = ?', [now, rec.id])
      this._afterWrite('external_rewards', rec.id)
      const sourceType = rec.item_type === 'task'
        ? 'task_complete'
        : rec.item_type === 'habit'
          ? (Number(rec.coins) >= 0 ? 'habit_checkin' : 'habit_fail')
          : rec.item_type === 'goal'
            ? (Number(rec.coins) >= 0 ? 'goal_reward' : 'goal_penalty')
            : 'external_claim'
      this._rewardLedgerService.addLedgerEntry(
        Number(rec.coins),
        sourceType,
        rec.id,
        rec.item_name || '外部奖励',
        now.slice(0, 10),
      )
      total += rec.coins
    }
    return total
  }

  getDiaryForDate(date: string): { morning_diary?: string; evening_diary?: string; morning_diary_written_at?: string; evening_diary_written_at?: string; report_status: number; morning_diary_reward_status?: string; morning_diary_reward_amount?: number; morning_diary_reward_reason?: string; evening_diary_reward_status?: string; evening_diary_reward_amount?: number; evening_diary_reward_reason?: string } | null {
    const row = this._get(
      `SELECT h.morning_diary,h.evening_diary,h.morning_diary_written_at,h.evening_diary_written_at,h.report_status,
              s.morning_diary_reward_status,s.morning_diary_reward_amount,s.morning_diary_reward_reason,
              s.evening_diary_reward_status,s.evening_diary_reward_amount,s.evening_diary_reward_reason
       FROM huawei_sleep_data h LEFT JOIN sleep_score_settlements s ON s.sleep_date=h.date
       WHERE h.date=? ORDER BY (s.rule_version='sleep-score-v2') DESC,s.updated_at DESC LIMIT 1`,
      [date],
    )
    if (!row) return { report_status: 0 }
    return {
      morning_diary: (row as any).morning_diary || undefined,
      evening_diary: (row as any).evening_diary || undefined,
      morning_diary_written_at: (row as any).morning_diary_written_at || undefined,
      evening_diary_written_at: (row as any).evening_diary_written_at || undefined,
      report_status: typeof (row as any).report_status === 'number' ? (row as any).report_status : 0,
      morning_diary_reward_status: (row as any).morning_diary_reward_status || undefined,
      morning_diary_reward_amount: Number((row as any).morning_diary_reward_amount || 0),
      morning_diary_reward_reason: (row as any).morning_diary_reward_reason || undefined,
      evening_diary_reward_status: (row as any).evening_diary_reward_status || undefined,
      evening_diary_reward_amount: Number((row as any).evening_diary_reward_amount || 0),
      evening_diary_reward_reason: (row as any).evening_diary_reward_reason || undefined,
    }
  }

  /**
   * 迁移：将本地系统配置中的明文敏感字段转为密文
   * 在启动时调用
   */
  migrateSensitiveConfigs(): void {
    const rawRows = this._all("SELECT key, value, value_type FROM system_config WHERE key IN ('auth_token', 'ai_model_config', 'ticktick_config', 'atimelogger_config')")
    
    for (const r of rawRows) {
      const row = r as any
      if (row.value_type === 'string') {
        if (!row.value.startsWith('ENC:') && !row.value.startsWith('WEB_ENC:')) {
          this.setConfig(row.key, row.value)
        }
      } else if (row.value_type === 'json') {
        try {
          const parsed = JSON.parse(row.value)
          let needsUpdate = false
          for (const flatKey of Object.keys(CONFIG_MAPPING)) {
            const mapInfo = CONFIG_MAPPING[flatKey]
            if (mapInfo.parent === row.key && SENSITIVE_KEYS.includes(flatKey)) {
              const val = parsed[mapInfo.key]
              if (val && typeof val === 'string' && !val.startsWith('ENC:') && !val.startsWith('WEB_ENC:')) {
                parsed[mapInfo.key] = encryptString(val)
                needsUpdate = true
              }
            }
          }
          if (needsUpdate) {
            this._run("UPDATE system_config SET value = ? WHERE key = ?", [JSON.stringify(parsed), row.key])
          }
        } catch {
          // ignore
        }
      }
    }
  }

// ======================== 系统配置 ========================

  getConfig(key: string): string | null {
    const mapping = CONFIG_MAPPING[key]
    if (mapping) {
      const parentRow = this._get('SELECT value FROM system_config WHERE key = ?', [mapping.parent])
      let parentObj = { ...(CONFIG_DEFAULTS[mapping.parent] || {}) }
      if (parentRow) {
        try {
          parentObj = JSON.parse((parentRow as any).value)
        } catch {
          // ignore
        }
      }
      let val = parentObj[mapping.key]
      if (val !== undefined && SENSITIVE_KEYS.includes(key)) {
        val = decryptString(String(val))
      }
      return val !== undefined ? String(val) : null
    }

    const row = this._get('SELECT value FROM system_config WHERE key = ?', [key])
    if (row) {
      let val = (row as any).value
      if (SENSITIVE_KEYS.includes(key)) val = decryptString(val)
      return val
    }
    return null
  }

  setConfig(key: string, value: string, desc = ''): void {
    const now = this._now()
    const mapping = CONFIG_MAPPING[key]

    if (mapping) {
      const parentRow = this._get('SELECT value, description FROM system_config WHERE key = ?', [mapping.parent])
      let parentObj = { ...(CONFIG_DEFAULTS[mapping.parent] || {}) }
      let parentDesc = desc
      if (parentRow) {
        try {
          parentObj = JSON.parse((parentRow as any).value)
          parentDesc = (parentRow as any).description || desc
        } catch {
          // ignore
        }
      }

      let typedVal: any = value
      if (mapping.type === 'number') {
        typedVal = Number(value)
      } else if (mapping.type === 'boolean') {
        typedVal = (value === 'true' || value === '1')
      }

      if (SENSITIVE_KEYS.includes(key) && typeof typedVal === 'string') {
        typedVal = encryptString(typedVal)
      }

      parentObj[mapping.key] = typedVal

      const valStr = JSON.stringify(parentObj)
      this._run(
        `INSERT OR REPLACE INTO system_config (key, value, value_type, description, updated_at)
         VALUES (?, ?, 'json', ?, ?)`,
        [mapping.parent, valStr, parentDesc, now],
      )
      if (!LOCAL_SYNC_CONFIG_KEYS.has(mapping.parent) && !isDeviceLocalSetting(mapping.parent)) {
        this._enqueueFn?.('system_config', mapping.parent as any)
        const row = this.getRecordByUnique('system_config', 'key', mapping.parent)
        if (row) this._enqueueOutbox('system_config', mapping.parent, 'upsert', row, row.pushed_at ?? null)
      }
      return
    }

    let finalVal = value
    if (SENSITIVE_KEYS.includes(key)) {
      finalVal = encryptString(value)
    }

    this._run(
      `INSERT OR REPLACE INTO system_config (key, value, value_type, description, updated_at)
       VALUES (?, ?, 'string', ?, ?)`,
      [key, finalVal, desc, now],
    )
    if (!LOCAL_SYNC_CONFIG_KEYS.has(key) && !isDeviceLocalSetting(key)) {
      this._enqueueFn?.('system_config', key as any)
      const row = this.getRecordByUnique('system_config', 'key', key)
      if (row) this._enqueueOutbox('system_config', key, 'upsert', row, row.pushed_at ?? null)
    }
  }

  /** 获取所有系统配置 */
  getAllConfig(): Record<string, string> {
    const rows = this._all('SELECT key, value, value_type FROM system_config')
    const map: Record<string, string> = {}

    for (const r of rows) {
      const row = r as any
      let rawValue = row.value
      if (SENSITIVE_KEYS.includes(row.key)) {
        rawValue = decryptString(rawValue)
      }
      map[row.key] = rawValue

      if (row.value_type === 'json' || (row.key.endsWith('_config') || row.key === 'hotkeys')) {
        try {
          const parsed = JSON.parse(row.value)
          for (const flatKey of Object.keys(CONFIG_MAPPING)) {
            const mapInfo = CONFIG_MAPPING[flatKey]
            if (mapInfo.parent === row.key && parsed[mapInfo.key] !== undefined) {
              let val = String(parsed[mapInfo.key])
              if (SENSITIVE_KEYS.includes(flatKey)) {
                val = decryptString(val)
              }
              map[flatKey] = val
            }
          }
        } catch {
          // ignore
        }
      }
    }

    for (const flatKey of Object.keys(CONFIG_MAPPING)) {
      if (map[flatKey] === undefined) {
        const mapInfo = CONFIG_MAPPING[flatKey]
        const defParentObj = CONFIG_DEFAULTS[mapInfo.parent]
        if (defParentObj && defParentObj[mapInfo.key] !== undefined) {
          map[flatKey] = String(defParentObj[mapInfo.key])
        }
      }
    }
    return map
  }

  // ======================== 同步专用 ========================
  // 临时兼容层：SyncWorker -> Database 同步方法 -> pushed_at/updated_at SQL。
  // TODO：迁移到 SyncRepository，统一表白名单和字段白名单，避免动态表名继续扩大。

  /** 获取指定表 pushed_at IS NULL 的记录 */
  getPendingSync(table: string): Record<string, any>[] {
    return this._all(`SELECT * FROM ${table} WHERE pushed_at IS NULL`)
  }

  /** 标记记录已同步 */
  markSynced(table: string, id: number | string, serverTime: string): void {
    if (table === 'system_config') {
      this._run(`UPDATE ${table} SET pushed_at = ? WHERE key = ?`, [serverTime, id])
      return
    }
    this._run(`UPDATE ${table} SET pushed_at = ? WHERE id = ?`, [serverTime, id])
  }

  getGoalProgress(goal: Goal): { current: number; target: number; percent: number } {
    const today = this._beijingNow()
    let startStr = ''
    let endStr = ''
    const period = goal.period

    const formatYYYYMMDD = (d: Date) => {
      const year = d.getFullYear()
      const month = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${year}-${month}-${day}`
    }

    if (period === 'daily') {
      startStr = formatYYYYMMDD(today)
      endStr = startStr
    } else if (period === 'weekly') {
      const day = today.getDay()
      const diff = today.getDate() - day + (day === 0 ? -6 : 1) // 周一为起点
      const start = new Date(today.getTime())
      start.setDate(diff)
      startStr = formatYYYYMMDD(start)
      const end = new Date(start.getTime())
      end.setDate(end.getDate() + 6)
      endStr = formatYYYYMMDD(end)
    } else { // monthly
      const start = new Date(today.getFullYear(), today.getMonth(), 1)
      startStr = formatYYYYMMDD(start)
      const end = new Date(today.getFullYear(), today.getMonth() + 1, 0)
      endStr = formatYYYYMMDD(end)
    }

    const categoryIds = goal.category_ids?.length
      ? goal.category_ids
      : (goal.category_id == null ? [] : [goal.category_id])
    if (categoryIds.length === 0) {
      return { current: 0, target: goal.target_value, percent: 0 }
    }
    const placeholders = categoryIds.map(() => '?').join(', ')
    let current = 0
    if (goal.metric === 'duration') {
      const sql = `SELECT SUM(net_duration_minutes) as val FROM study_sessions WHERE category_id IN (${placeholders}) AND date BETWEEN ? AND ?`
      const row = this._get(sql, [...categoryIds, startStr, endStr])
      current = (row as any)?.val ?? 0
    } else {
      const sql = `SELECT COUNT(*) as val FROM study_sessions WHERE category_id IN (${placeholders}) AND date BETWEEN ? AND ?`
      const row = this._get(sql, [...categoryIds, startStr, endStr])
      current = (row as any)?.val ?? 0
    }

    const target = goal.target_value
    const percent = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0

    return { current, target, percent }
  }

  getCategoryHistory(categoryId: number, metric: 'duration' | 'count', days = 30): Record<string, number> {
    return this.getCategoriesHistory([categoryId], metric, days)
  }

  getCategoriesHistory(categoryIds: number[], metric: 'duration' | 'count', days = 30): Record<string, number> {
    const today = this._beijingNow()
    const history: Record<string, number> = {}
    const formatYYYYMMDD = (d: Date) => {
      const year = d.getFullYear()
      const month = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${year}-${month}-${day}`
    }

    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(today.getTime())
      d.setDate(today.getDate() - i)
      const dateStr = formatYYYYMMDD(d)
      history[dateStr] = 0
    }

    const startStr = formatYYYYMMDD(new Date(today.getTime() - (days - 1) * 24 * 60 * 60 * 1000))
    if (categoryIds.length === 0) return history
    const placeholders = categoryIds.map(() => '?').join(', ')
    const sql = metric === 'duration'
      ? `SELECT date, SUM(net_duration_minutes) as val FROM study_sessions WHERE category_id IN (${placeholders}) AND date >= ? GROUP BY date`
      : `SELECT date, COUNT(*) as val FROM study_sessions WHERE category_id IN (${placeholders}) AND date >= ? GROUP BY date`
    const rows = this._all(sql, [...categoryIds, startStr])
    rows.forEach(r => {
      if (r.date in history) {
        history[r.date] = r.val || 0
      }
    })
    return history
  }

  getAvailableUnlocks(unlockTaskId: string, rewardId: number | string): number {
    if (!unlockTaskId) return 0
    try {
      let achievedCount = 0
      if (unlockTaskId.startsWith('goal_')) {
        const row = this._get(
          "SELECT COUNT(*) as count FROM external_rewards WHERE ext_id LIKE ? AND coins >= 0",
          [`${unlockTaskId}_%`]
        )
        achievedCount = (row as any)?.count ?? 0
      } else {
        const row1 = this._get(
          "SELECT 1 FROM tasks WHERE ticktick_id = ? AND status = 2",
          [unlockTaskId]
        )
        if (row1) {
          achievedCount = 1
        } else {
          const row2 = this._get(
            "SELECT COUNT(*) as count FROM external_rewards WHERE ext_id = ? OR ext_id = ?",
            [`task_${unlockTaskId}`, `habit_${unlockTaskId}`]
          )
          achievedCount = (row2 as any)?.count ?? 0
        }
      }

      const row3 = this._get(
        "SELECT COUNT(*) as count FROM reward_ledger WHERE source_type = 'reward_unlock' AND source_id = ?",
        [rewardId]
      )
      const usedCount = (row3 as any)?.count ?? 0
      return Math.max(0, achievedCount - usedCount)
    } catch {
      return 0
    }
  }

  completeTask(ticktickId: string, title: string, coins = 0.1): void {
    // 幂等保护：已完成的任务不重复处理
    const existing = this._get('SELECT status FROM tasks WHERE id = ?', [ticktickId])
    if (existing && (existing as any).status === 2) return

    const now = this._now()
    this._run(`UPDATE tasks SET status = 2, updated_at = ? WHERE id = ?`, [now, ticktickId])

    this._afterWrite('tasks', ticktickId)

    // 专属奖励自动购买入背包
    const rewards = this._all(
      `SELECT id, title FROM rewards WHERE unlock_task_id = ? AND is_active = 1`,
      [ticktickId]
    )
    for (const r of rewards) {
      const ledgerId = 'ledger_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
      this._run(
        `INSERT INTO reward_ledger (id, amount, source_type, source_id, description, created_at, updated_at)
         VALUES (?, 0, 'reward_unlock', ?, ?, ?, ?)`,
        [ledgerId, r.id, `任务自动解锁兑换: ${r.title} [来自任务完成: ${title}]`, now, now]
      )
      this._afterWrite('reward_ledger', ledgerId)
    }
  }

  autoSettleGoals(): void {
    // Goal settlement is server-authoritative; retained only for legacy callers.
    return
    try {
      const today = this._beijingNow()
      const formatYYYYMMDD = (d: Date) => {
        const year = d.getFullYear()
        const month = String(d.getMonth() + 1).padStart(2, '0')
        const day = String(d.getDate()).padStart(2, '0')
        return `${year}-${month}-${day}`
      }
      const todayStr = formatYYYYMMDD(today)
      const yesterday = new Date(today.getTime())
      yesterday.setDate(today.getDate() - 1)
      const yesterdayStr = formatYYYYMMDD(yesterday)
      const now = this._now()

      const lastResetTime = this.getConfig('last_reset_time') || '2026-05-01 00:00:00'
      const goals = this.getGoals()

      for (const g of goals) {
        const gId = g.id
        const title = g.title
        const catId = g.category_id
        const period = g.period
        const metric = g.metric
        const target = g.target_value
        const operator = g.operator || '>='
        const rewardCoins = g.reward_coins
        const penaltyCoins = g.penalty_coins ?? rewardCoins
        const createdAtGoal = g.created_at || '2000-01-01 00:00:00'

        const issue = (claimId: string, isMet: boolean, val: number, targetVal: number, op: string, dateStr: string, failIfNotMet = false) => {
          const existing = this._get("SELECT 1 FROM external_rewards WHERE ext_id = ?", [claimId])
          if (existing) return

          let amount = 0
          let dateLabel = dateStr
          if (dateStr.length >= 10 && dateStr[4] === '-') dateLabel = dateStr.slice(5)
          const desc = `${title} ${dateLabel}`

          if (isMet) {
            amount = rewardCoins
          } else if (failIfNotMet) {
            amount = -Math.abs(penaltyCoins)
          } else {
            return
          }

          if (amount !== 0) {
            this._run(
              `INSERT INTO external_rewards (ext_id, item_type, item_name, coins, status, created_at)
               VALUES (?, 'goal', ?, ?, 0, ?)`,
              [claimId, desc, amount, now]
            )
            const row = this._get('SELECT id FROM external_rewards WHERE ext_id = ?', [claimId]) as any
            if (row) {
              this._afterWrite('external_rewards', row.id)
            }
          }
        }

        if (period === 'per_session') {
          const sessions = this._all(
            `SELECT id, net_duration_minutes, start_time FROM study_sessions
             WHERE category_id = ? AND date = ? AND start_time > ?`,
            [catId, todayStr, lastResetTime]
          )
          for (const s of sessions) {
            if (s.start_time < createdAtGoal) continue
            const dur = s.net_duration_minutes
            const isMet = operator === '>=' ? (dur >= target) : (dur <= target)
            issue(`goal_${gId}_session_${s.id}`, isMet, dur, target, operator, s.start_time.slice(0, 10), true)
          }
        } else if (period === 'daily') {
          for (const dateStr of [yesterdayStr, todayStr]) {
            if (dateStr < createdAtGoal.slice(0, 10)) continue
            if (dateStr < lastResetTime.slice(0, 10)) continue

            let val = 0
            if (metric === 'duration') {
              const row = this._get(
                `SELECT SUM(net_duration_minutes) as total FROM study_sessions
                 WHERE category_id = ? AND date = ? AND start_time > ?`,
                [catId, dateStr, lastResetTime]
              )
              val = (row as any)?.total ?? 0
            } else {
              const row = this._get(
                `SELECT COUNT(*) as total FROM study_sessions
                 WHERE category_id = ? AND date = ? AND start_time > ?`,
                [catId, dateStr, lastResetTime]
              )
              val = (row as any)?.total ?? 0
            }

            const isMet = operator === '>=' ? (val >= target) : (val <= target)
            const claimId = `goal_${gId}_${dateStr.replace(/-/g, '')}`

            if (dateStr === yesterdayStr) {
              issue(claimId, isMet, val, target, operator, dateStr, true)
            } else {
              if (operator === '>=' && isMet) {
                issue(claimId, true, val, target, operator, dateStr)
              } else if (operator === '<=' && !isMet) {
                issue(claimId, false, val, target, operator, dateStr, true)
              }
            }
          }
        } else if (period === 'weekly') {
          const getWeekRange = (refDate: Date) => {
            const d = new Date(refDate.getTime())
            const day = d.getDay()
            const diff = d.getDate() - day + (day === 0 ? -6 : 1)
            const start = new Date(d.setDate(diff))
            const end = new Date(start)
            end.setDate(end.getDate() + 6)
            return {
              startStr: formatYYYYMMDD(start),
              endStr: formatYYYYMMDD(end),
            }
          }
          const thisWeek = getWeekRange(today)
          const lastWeekDate = new Date(today.getTime())
          lastWeekDate.setDate(today.getDate() - 7)
          const lastWeek = getWeekRange(lastWeekDate)

          for (const weekRange of [lastWeek, thisWeek]) {
            const isPast = weekRange === lastWeek
            const { startStr, endStr } = weekRange

            if (endStr < createdAtGoal.slice(0, 10)) continue
            if (endStr < lastResetTime.slice(0, 10)) continue

            let val = 0
            if (metric === 'duration') {
              const row = this._get(
                `SELECT SUM(net_duration_minutes) as total FROM study_sessions
                 WHERE category_id = ? AND date BETWEEN ? AND ? AND start_time > ?`,
                [catId, startStr, endStr, lastResetTime]
              )
              val = (row as any)?.total ?? 0
            } else {
              const row = this._get(
                `SELECT COUNT(*) as total FROM study_sessions
                 WHERE category_id = ? AND date BETWEEN ? AND ? AND start_time > ?`,
                [catId, startStr, endStr, lastResetTime]
              )
              val = (row as any)?.total ?? 0
            }

            const isMet = operator === '>=' ? (val >= target) : (val <= target)
            const claimId = `goal_${gId}_week_${startStr.replace(/-/g, '')}`

            if (isPast) {
              issue(claimId, isMet, val, target, operator, `${startStr}~${endStr}`, true)
            } else {
              if (operator === '>=' && isMet) {
                issue(claimId, true, val, target, operator, `${startStr}~${endStr}`)
              } else if (operator === '<=' && !isMet) {
                issue(claimId, false, val, target, operator, `${startStr}~${endStr}`, true)
              }
            }
          }
        } else if (period === 'monthly') {
          const getMonthRange = (refDate: Date) => {
            const start = new Date(refDate.getFullYear(), refDate.getMonth(), 1)
            const end = new Date(refDate.getFullYear(), refDate.getMonth() + 1, 0)
            return {
              startStr: formatYYYYMMDD(start),
              endStr: formatYYYYMMDD(end),
            }
          }
          const thisMonth = getMonthRange(today)
          const lastMonthDate = new Date(today.getTime())
          lastMonthDate.setMonth(today.getMonth() - 1)
          const lastMonth = getMonthRange(lastMonthDate)

          for (const monthRange of [lastMonth, thisMonth]) {
            const isPast = monthRange === lastMonth
            const { startStr, endStr } = monthRange

            if (endStr < createdAtGoal.slice(0, 10)) continue
            if (endStr < lastResetTime.slice(0, 10)) continue

            let val = 0
            if (metric === 'duration') {
              const row = this._get(
                `SELECT SUM(net_duration_minutes) as total FROM study_sessions
                 WHERE category_id = ? AND date BETWEEN ? AND ? AND start_time > ?`,
                [catId, startStr, endStr, lastResetTime]
              )
              val = (row as any)?.total ?? 0
            } else {
              const row = this._get(
                `SELECT COUNT(*) as total FROM study_sessions
                 WHERE category_id = ? AND date BETWEEN ? AND ? AND start_time > ?`,
                [catId, startStr, endStr, lastResetTime]
              )
              val = (row as any)?.total ?? 0
            }

            const isMet = operator === '>=' ? (val >= target) : (val <= target)
            const claimId = `goal_${gId}_month_${startStr.slice(0, 7).replace(/-/g, '')}`

            if (isPast) {
              issue(claimId, isMet, val, target, operator, startStr.slice(0, 7), true)
            } else {
              if (operator === '>=' && isMet) {
                issue(claimId, true, val, target, operator, startStr.slice(0, 7))
              } else if (operator === '<=' && !isMet) {
                issue(claimId, false, val, target, operator, startStr.slice(0, 7), true)
              }
            }
          }
        }
      }

      // 自动claim领取所有未领取的目标结算奖励，直接进入流水
      const goalRewards = this._all("SELECT id FROM external_rewards WHERE item_type = 'goal' AND status = 0")
      if (goalRewards.length > 0) {
        this.claimRewards(goalRewards.map(r => r.id as string))
      }
    } catch (e) {
      console.error('目标结算失败', e)
    }
  }

  getItemReward(itemType: string, itemId: string, defaultCoins = 0.1): { reward: number; penalty: number } {
    try {
      const row = this._get(
        "SELECT coins, penalty FROM reward_config WHERE item_type = ? AND item_id = ?",
        [itemType, itemId]
      )
      if (row) {
        return {
          reward: (row as any).coins,
          penalty: (row as any).penalty !== null ? (row as any).penalty : (row as any).coins
        }
      }
      return { reward: defaultCoins, penalty: defaultCoins }
    } catch {
      return { reward: defaultCoins, penalty: defaultCoins }
    }
  }

  setItemReward(itemType: string, itemId: string, coins: number, penalty: number): void {
    const now = this._now()
    this._run(
      `INSERT OR REPLACE INTO reward_config (item_type, item_id, coins, penalty, updated_at)
       VALUES (?, ?, ?, ?, ?)`,
      [itemType, itemId, coins, penalty, now]
    )
    const row = this._get(
      "SELECT id FROM reward_config WHERE item_type = ? AND item_id = ?",
      [itemType, itemId]
    )
    if (row) {
      this._afterWrite('reward_config', (row as any).id)
    }
  }

  getSleepStatusMap(): Record<string, number> {
    try {
      const rows = this._all('SELECT date, report_status FROM huawei_sleep_data')
      const map: Record<string, number> = {}
      for (const r of rows) {
        const rec = r as any
        if (rec.date) {
          map[rec.date] = typeof rec.report_status === 'number' ? rec.report_status : 0
        }
      }
      return map
    } catch {
      return {}
    }
  }

  getMonthlyCheckins(habitId: number, monthStr: string): Record<string, number> {
    try {
      const rows = this._all(
        "SELECT checkin_date, status FROM habit_checkins WHERE habit_id = ? AND checkin_date LIKE ?",
        [habitId, `${monthStr}%`]
      )
      const map: Record<string, number> = {}
      for (const r of rows) {
        const rec = r as any
        if (rec.checkin_date) {
          map[rec.checkin_date] = typeof rec.status === 'number' ? rec.status : 0
        }
      }
      return map
    } catch {
      return {}
    }
  }

  // ======================== 运动模块 ========================

  getActiveExercisePlanVersion(): string {
    const configured = String((this._get("SELECT value FROM system_config WHERE key = 'active_exercise_plan_version'") as any)?.value || 'v0');
    if (this._isExercisePlanComplete(configured)) return configured;
    const versions = this._all('SELECT version FROM exercise_plan_versions WHERE is_active = 1 ORDER BY created_at DESC, version DESC');
    return String(versions.find((row: any) => this._isExercisePlanComplete(String(row.version)))?.version || 'v0');
  }

  private _isExercisePlanComplete(version: string): boolean {
    if (!this._get('SELECT 1 FROM exercise_plan_versions WHERE version=? AND is_active=1', [version])) return false;
    const required: Array<[string, number]> = version === 'v4' ? [
      ['exercise_plan_schedule_items', 8], ['exercise_plan_items', 23],
      ['exercise_plan_progress_items', 4], ['exercise_plan_diet_rules', 3],
      ['exercise_plan_category_rules', 3],
    ] : version === 'v2' ? [
      ['exercise_plan_schedule_items', 11], ['exercise_plan_items', 90],
      ['exercise_plan_progress_items', 4], ['exercise_plan_diet_rules', 3],
      ['exercise_plan_score_rules', 18], ['exercise_plan_category_rules', 6],
    ] : [['exercise_plan_schedule_items', 1], ['exercise_plan_score_rules', 1], ['exercise_plan_category_rules', 1], ['exercise_plan_items', 1]];
    return required.every(([table, minimum]) => Number(this._get(`SELECT COUNT(*) AS count FROM ${table} WHERE plan_version=?`, [version])?.count || 0) >= minimum);
  }

  setActiveExercisePlanVersion(version: string): { ok: boolean; error?: string } {
    if (!this._isExercisePlanComplete(version)) return { ok: false, error: 'exercise_plan_version_incomplete' };
    try {
      const now = this._now();
      this._run(
        "INSERT INTO system_config (key,value,description,updated_at) VALUES ('active_exercise_plan_version',?,'当前训练计划版本',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        [version, now],
      );
      this._afterWrite('system_config', 'active_exercise_plan_version');
      return { ok: true };
    } catch {
      return { ok: false, error: 'exercise_plan_version_switch_failed' };
    }
  }

  getExercisePlanVersions(): any[] {
    return this._all('SELECT * FROM exercise_plan_versions WHERE is_active = 1 ORDER BY created_at ASC, version ASC');
  }

  getExercisePlanDefinition(planVersion = this.getActiveExercisePlanVersion()): any {
    const version = this._get('SELECT * FROM exercise_plan_versions WHERE version = ?', [planVersion]) as any;
    const days: PlanDay[] = ['周一','周二','周三','周四','周五','六','日'];
    const weekdayDays = days;
    const scheduleRows = this._all('SELECT * FROM exercise_plan_schedule_items WHERE plan_version = ? ORDER BY schedule_type, sort_order', [planVersion]);
    const scoreRows = this._all('SELECT * FROM exercise_plan_score_rules WHERE plan_version = ? ORDER BY day_type, sort_order', [planVersion]);
    const categoryRows = this._all('SELECT * FROM exercise_plan_category_rules WHERE plan_version = ? ORDER BY sort_order', [planVersion]);
    const progressRows = this._all('SELECT * FROM exercise_plan_progress_items WHERE plan_version = ? ORDER BY sort_order', [planVersion]);
    const dietRows = this._all('SELECT * FROM exercise_plan_diet_rules WHERE plan_version = ? ORDER BY sort_order', [planVersion]);
    const exercisePlan: any = {};
    for (const day of weekdayDays) {
      const gym = this.getExercisePlanItems(day, 'gym', planVersion);
      const rain = this.getExercisePlanItems(day, 'rain', planVersion);
      const color = (gym[0] || rain[0])?.color || '#8b5cf6';
      const label = this._labelForExerciseDay(day, planVersion);
      exercisePlan[day] = {
        label,
        color,
        gym: gym.map((item: any) => this._exerciseItemFromRow(item)),
        rain: rain.map((item: any) => this._exerciseItemFromRow(item)),
      };
    }
    const removedScheduleItems = new Set(['到达图书馆', '离开图书馆', '到达体育公园', '达到体育公园', '离开体育公园', '结束户外锻炼'])
    const bySchedule = (type: string) => scheduleRows
      .filter((row: any) => row.schedule_type === type)
      .filter((row: any) => !removedScheduleItems.has(String(row.item || '').replace(/^\S+\s*/, '')) && !removedScheduleItems.has(String(row.item || '')))
      .map((row: any) => ({ time: row.time, item: row.item, note: row.note || '', accent: row.accent || 'default' }));
    const byScore = (type: string): ScoreRule[] => scoreRows
      .filter((row: any) => row.day_type === type)
      .map((row: any) => row.target_time
        ? [row.schedule_index, row.points, row.category, row.target_time] as ScoreRule
        : [row.schedule_index, row.points, row.category] as ScoreRule);
    const canRecoverLegacyV4DietKeys = planVersion === 'v4'
      && dietRows.length === V4_DIET_RULE_KEYS.length
      && dietRows.every((row: any, index: number) => {
        const key = String(row.rule_key || '').trim()
        return Number(row.sort_order) === index && (!key || key === V4_DIET_RULE_KEYS[index])
      })
    const diet = dietRows.map((row: any, index: number) => ({
      ruleKey: String(row.rule_key || '').trim() || (canRecoverLegacyV4DietKeys ? V4_DIET_RULE_KEYS[index] : undefined),
      time: row.time,
      content: row.content,
      note: row.note || '',
    }))
    const dietKeys = diet.map(rule => rule.ruleKey || '')
    const dietRulesValid = planVersion !== 'v4' || (dietKeys.length === V4_DIET_RULE_KEYS.length
      && new Set(dietKeys).size === V4_DIET_RULE_KEYS.length
      && dietKeys.every(key => V4_DIET_RULE_KEYS.includes(key)))
    return {
      version: planVersion,
      title: version?.title || '每日打卡表',
      sourceName: version?.source_name || '',
      diet,
      dietRulesValid,
      weekdaySchedule: bySchedule('weekday'),
      restSchedule: bySchedule('rest'),
      sundayExtra: bySchedule('sunday_extra')[0] || { time: '', item: '', note: '', accent: 'default' },
      exercisePlan,
      progress: progressRows.map((row: any) => ({ when: row.when_text, text: row.text })),
      weekdayScore: byScore('weekday'),
      saturdayScore: byScore('saturday'),
      sundayScore: byScore('sunday'),
      categoryOrder: categoryRows.map((row: any) => row.category),
      exercisePoints: Number(version?.exercise_points || 0),
    } satisfies ExercisePlanDefinition;
  }

  private _exerciseItemFromRow(row: any): any {
    let tags: any = {};
    try { tags = row.tags_json ? JSON.parse(row.tags_json) : {}; } catch { tags = {}; }
    return {
      ...tags,
      name: row.name,
      sets: row.sets || '',
      intensity: row.intensity || '',
      s: row.section,
      prog: row.progression ?? tags.prog,
    };
  }

  private _labelForExerciseDay(day: string, planVersion: string): string {
    const row = this._get(
      'SELECT tags_json FROM exercise_plan_items WHERE plan_version = ? AND day_key = ? AND tags_json IS NOT NULL ORDER BY sort_order LIMIT 1',
      [planVersion, day],
    ) as any;
    try {
      const parsed = row?.tags_json ? JSON.parse(row.tags_json) : null;
      if (parsed?.label) return parsed.label;
    } catch {}
    return day;
  }

  getExerciseDailyLog(date: string, planVersion = this.getActiveExercisePlanVersion()): any {
    return this._get('SELECT * FROM exercise_daily_logs WHERE date = ? AND plan_version = ?', [date, planVersion]);
  }

  getExerciseItemScores(date: string, planVersion = this.getActiveExercisePlanVersion()): any[] {
    return this._all('SELECT * FROM exercise_item_scores WHERE date=? AND plan_version=? ORDER BY item_key', [date, planVersion]);
  }

  getExerciseSettlement(date: string, planVersion = this.getActiveExercisePlanVersion()): any {
    return this._get('SELECT * FROM exercise_settlements WHERE business_date=? AND plan_version=?', [date, planVersion]);
  }

  setExerciseVariant(date: string, exerciseVariant: 'gym' | 'rain', planVersion = this.getActiveExercisePlanVersion()): void {
    if (this.isExerciseDateLocked(date)) return;
    const row = this._get('SELECT id FROM exercise_daily_logs WHERE date=? AND plan_version=?', [date, planVersion]);
    if (row) {
      this._run('UPDATE exercise_daily_logs SET exercise_variant=?,updated_at=? WHERE id=?', [exerciseVariant, this._now(), row.id]);
      this._afterWrite('exercise_daily_logs', row.id);
      return;
    }
    this.upsertExerciseDailyLog(date, this.getExerciseWeekNum(), '', undefined, 0, 0, planVersion, undefined, exerciseVariant);
  }

  isExerciseDateLocked(date: string): boolean {
    return date < this._localToday();
  }

  upsertExerciseDailyLog(date: string, weekNum: number, dayName: string, weight?: number, completedItems = 0, totalItems = 0, planVersion = this.getActiveExercisePlanVersion(), scoreSnapshot?: any, exerciseVariant = 'gym', bodyFatRate?: number): void {
    const existing = this._get('SELECT id FROM exercise_daily_logs WHERE date = ? AND plan_version = ?', [date, planVersion]);
    if (this.isExerciseDateLocked(date)) {
      if (weight === undefined && bodyFatRate === undefined) return;
      if (existing) {
        const id = (existing as any).id;
        const sets: string[] = ['updated_at = ?']; const vals: any[] = [this._now()];
        if (weight !== undefined) { sets.push('weight = ?'); vals.push(weight); }
        if (bodyFatRate !== undefined) { sets.push('body_fat_rate = ?'); vals.push(bodyFatRate); }
        vals.push(id); this._run(`UPDATE exercise_daily_logs SET ${sets.join(', ')} WHERE id = ?`, vals);
        this._afterWrite('exercise_daily_logs', id);
      } else {
        const uuid = this._generateUUID();
        this._run(
          `INSERT INTO exercise_daily_logs (id, date, plan_version, week_num, day_name, weight, body_fat_rate, completed_items, total_items, score_snapshot, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          [uuid, date, planVersion, weekNum, dayName, weight ?? null, bodyFatRate ?? null, 0, 0, null, this._now(), this._now()]
        );
        this._afterWrite('exercise_daily_logs', uuid);
      }
      return;
    }
    if (existing) {
      const id = (existing as any).id;
      const sets: string[] = ['updated_at = ?'];
      const vals: any[] = [this._now()];
      if (weight !== undefined) { sets.push('weight = ?'); vals.push(weight); }
      if (bodyFatRate !== undefined) { sets.push('body_fat_rate = ?'); vals.push(bodyFatRate); }
      sets.push('completed_items = ?'); vals.push(completedItems);
      sets.push('total_items = ?'); vals.push(totalItems);
      if (scoreSnapshot !== undefined) { sets.push('score_snapshot = ?'); vals.push(JSON.stringify(scoreSnapshot)); }
      sets.push('exercise_variant = ?'); vals.push(exerciseVariant);
      vals.push(id);
      this._run(`UPDATE exercise_daily_logs SET ${sets.join(', ')} WHERE id = ?`, vals);
      this._afterWrite('exercise_daily_logs', id);
    } else {
      const uuid = this._generateUUID();
      this._run(
        `INSERT INTO exercise_daily_logs (id, date, plan_version, week_num, day_name, weight, body_fat_rate, completed_items, total_items, exercise_variant, score_snapshot, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [uuid, date, planVersion, weekNum, dayName, weight ?? null, bodyFatRate ?? null, completedItems, totalItems, exerciseVariant, scoreSnapshot === undefined ? null : JSON.stringify(scoreSnapshot), this._now(), this._now()]
      );
      this._afterWrite('exercise_daily_logs', uuid);
    }
  }

  getExerciseCheckins(date: string, planVersion = this.getActiveExercisePlanVersion()): any[] {
    return this._all('SELECT * FROM exercise_checkins WHERE date = ? AND plan_version = ?', [date, planVersion]);
  }

  getExerciseDietCheckins(date: string, planVersion = this.getActiveExercisePlanVersion()): any[] {
    if (planVersion !== 'v4') return this._all('SELECT * FROM exercise_diet_checkins WHERE date=? AND plan_version=? ORDER BY rule_key', [date, planVersion]);
    const placeholders = V4_DIET_RULE_KEYS.map(() => '?').join(',')
    return this._all(`SELECT * FROM exercise_diet_checkins WHERE date=? AND plan_version=? AND rule_key IN (${placeholders}) ORDER BY rule_key`, [date, planVersion, ...V4_DIET_RULE_KEYS]);
  }

  discardInvalidV4DietCheckins(date: string, planVersion = this.getActiveExercisePlanVersion()): number {
    if (planVersion !== 'v4') return 0
    const placeholders = V4_DIET_RULE_KEYS.map(() => '?').join(',')
    const rows = this._all(`SELECT id FROM exercise_diet_checkins WHERE date=? AND plan_version=? AND rule_key NOT IN (${placeholders})`, [date, planVersion, ...V4_DIET_RULE_KEYS])
    for (const row of rows) {
      this._run('DELETE FROM exercise_diet_checkins WHERE id=?', [row.id])
      this._run("DELETE FROM sync_outbox WHERE table_name='exercise_diet_checkins' AND record_id=?", [String(row.id)])
    }
    return rows.length
  }

  getExerciseDeadlineFacts(date: string, planVersion = this.getActiveExercisePlanVersion()): any[] {
    return this._all('SELECT * FROM exercise_deadline_facts WHERE date=? AND plan_version=? ORDER BY fact_type', [date, planVersion]);
  }

  toggleExerciseDietCheckin(date: string, ruleKey: string, status: 'pending' | 'completed' | 'failed' | boolean, planVersion = this.getActiveExercisePlanVersion()): void {
    if (this.isExerciseDateLocked(date) || planVersion !== 'v4' || !V4_DIET_RULE_KEYS.includes(ruleKey)) return;
    if (typeof status === 'boolean') status = status ? 'completed' : 'pending';
    const now = this._now(); const id = `diet:${date}:${planVersion}:${ruleKey}`;
    const deadline = new Date(`${date}T00:00:00+08:00`); deadline.setDate(deadline.getDate() + 1);
    this._run(`INSERT INTO exercise_diet_checkins
      (id,date,plan_version,rule_key,status,occurred_at,deadline_at,failure_reason,penalty_source_id,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(date,plan_version,rule_key) DO UPDATE SET
      status=excluded.status,occurred_at=excluded.occurred_at,failure_reason=excluded.failure_reason,
      penalty_source_id=excluded.penalty_source_id,updated_at=excluded.updated_at`,
      [id,date,planVersion,ruleKey,status,status === 'pending' ? null : now,deadline.toISOString(),status === 'failed' ? 'user_marked_failed' : null,null,now,now]);
    const saved = this._get('SELECT id FROM exercise_diet_checkins WHERE date=? AND plan_version=? AND rule_key=?', [date, planVersion, ruleKey]);
    if (saved?.id) this._afterWrite('exercise_diet_checkins', saved.id);
  }

  getExerciseCheckinTitle(date: string, sourceId: string | number | null | undefined): string | null {
    if (!date || sourceId == null || sourceId === '') return null
    const row = this._get(
      `SELECT item_name FROM exercise_checkins WHERE date=? AND (id=? OR plan_item_id=?)
       AND COALESCE(item_name, '') != '' ORDER BY updated_at DESC LIMIT 1`,
      [date, String(sourceId), String(sourceId)],
    )
    return row?.item_name ? String(row.item_name) : null
  }

  getExercisePlanItems(dayKey: string, variant: string, planVersion = this.getActiveExercisePlanVersion()): any[] {
    return this._all('SELECT * FROM exercise_plan_items WHERE plan_version=? AND day_key=? AND variant=? AND is_active=1 ORDER BY sort_order', [planVersion, dayKey, variant]);
  }

  upsertExercisePlanItem(item: any): void {
    const now=this._now();
    const version = item.plan_version || 'v0';
    this._run(`INSERT INTO exercise_plan_items (id,plan_version,day_key,variant,section,sort_order,name,sets,intensity,tags_json,progression,color,is_active,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET plan_version=excluded.plan_version,day_key=excluded.day_key,variant=excluded.variant,section=excluded.section,sort_order=excluded.sort_order,name=excluded.name,sets=excluded.sets,intensity=excluded.intensity,tags_json=excluded.tags_json,progression=excluded.progression,color=excluded.color,updated_at=excluded.updated_at`, [item.id,version,item.day_key,item.variant,item.section,item.sort_order,item.name,item.sets,item.intensity,item.tags_json,item.progression,item.color,1,now,now]);
    this._afterWrite('exercise_plan_items', item.id);
  }

  getExerciseDailyLogs(limit = 8, planVersion = this.getActiveExercisePlanVersion()): any[] {
    return this._all(`SELECT logs.*, settlement.score_total AS settlement_score_total,
      settlement.coin_amount AS settlement_coin_amount, settlement.settlement_status,
      settlement.reason_code AS settlement_reason_code
      FROM exercise_daily_logs logs
      LEFT JOIN exercise_settlements settlement
        ON settlement.business_date=logs.date AND settlement.plan_version=logs.plan_version
      WHERE logs.plan_version = ? ORDER BY logs.date DESC LIMIT ?`, [planVersion, limit]);
  }

  getExerciseWeekNum(): number {
    return Number((this._get("SELECT value FROM system_config WHERE key = 'exercise_week_num'") as any)?.value || 1);
  }

  setExerciseWeekNum(value: number): void {
    const now = this._now();
    this._run("INSERT INTO system_config (key,value,description,updated_at) VALUES ('exercise_week_num',?,'运动打卡内部周次',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", [String(value), now]);
    this._afterWrite('system_config', 'exercise_week_num');
  }

  resetExerciseCheckins(date?: string, planVersion = this.getActiveExercisePlanVersion()): void {
    if (date && this.isExerciseDateLocked(date)) return;
    const rows = date ? this._all('SELECT id FROM exercise_checkins WHERE date = ? AND plan_version = ?', [date, planVersion]) : this._all('SELECT id FROM exercise_checkins WHERE plan_version = ?', [planVersion]);
    this._run(date ? 'DELETE FROM exercise_checkins WHERE date = ? AND plan_version = ?' : 'DELETE FROM exercise_checkins WHERE plan_version = ?', date ? [date, planVersion] : [planVersion]);
    rows.forEach((row: any) => this._afterWrite('exercise_checkins', row.id));
  }

  toggleExerciseCheckin(date: string, itemKey: string, status: number, note?: string, completedTime?: string | null, planItemId?: string | null, itemName?: string | null, planVersion = this.getActiveExercisePlanVersion()): void {
    if (this.isExerciseDateLocked(date)) return;
    const existing = this._get('SELECT id, note, locked_at FROM exercise_checkins WHERE date = ? AND plan_version = ? AND item_key = ?', [date, planVersion, itemKey]);
    if ((existing as any)?.locked_at) return;
    if (existing) {
      const id = (existing as any).id;
      const mergedNote = note !== undefined ? note : (existing as any).note;
      this._run('UPDATE exercise_checkins SET status=?,note=?,completed_time=?,plan_item_id=COALESCE(?,plan_item_id),item_name=COALESCE(?,item_name),updated_at=? WHERE id=?', [status,mergedNote,completedTime??null,planItemId??null,itemName??null,this._now(),id]);
      this._afterWrite('exercise_checkins', id);
    } else {
      const uuid = this._generateUUID();
      this._run(
        `INSERT INTO exercise_checkins (id,date,plan_version,item_key,status,note,completed_time,plan_item_id,item_name,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
        [uuid,date,planVersion,itemKey,status,note||null,completedTime??null,planItemId??null,itemName??null,this._now(),this._now()]
      );
      this._afterWrite('exercise_checkins', uuid);
    }
  }

}
