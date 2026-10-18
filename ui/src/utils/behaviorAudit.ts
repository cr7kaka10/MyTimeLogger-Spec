import { detectPlatformRuntime } from '../platform'
import { getDatabase } from '../db'
import { setPlatformFetchAuditSink } from '../platform/fetch'
import { BEHAVIOR_EVENT_FIELDS, isBehaviorAction } from './behaviorEventCatalog'

type Runtime = { serverUrl: string; authToken: string }
let runtime: Runtime | null = null
let flushing = false
let retryTimer: ReturnType<typeof setTimeout> | null = null
let intentAt = 0
const sensitive = /token|password|secret|cookie|authorization|content|text|note|body|bearer\s+/i
const excludedRequest = /\/api\/v1\/behavior-events|\/health|\/events(?:\?|$)|\/sync(?:\/|\?|$)|\/poll(?:\/|\?|$)/i
export const configureBehaviorAudit = (next: Runtime | null) => { runtime = next; if (retryTimer) clearTimeout(retryTimer); retryTimer = null }
export const sanitizeBehaviorMetadata = (value: Record<string, unknown> = {}, action?: string) => {
  const allowed = action && isBehaviorAction(action) ? new Set<string>(BEHAVIOR_EVENT_FIELDS[action]) : null
  return Object.fromEntries(Object.entries(value).filter(([key, item]) => (!allowed || allowed.has(key)) && !sensitive.test(key) && !sensitive.test(String(item)) && ['string', 'number', 'boolean'].includes(typeof item) && (typeof item !== 'string' || item.length <= 120)).sort(([a], [b]) => a.localeCompare(b)).slice(0, 20))
}
const stableEventId = (action: string, key: string) => `audit:${[...`${action}:${key}`].reduce((hash, char) => ((hash * 33 + char.charCodeAt(0)) >>> 0), 5381).toString(16)}`
export const recordBehavior = (action: string, metadata: Record<string, unknown> = {}, dedupeKey = '') => {
  if (!isBehaviorAction(action) || action.startsWith('audit.')) return
  if (!action.startsWith('api.')) intentAt = Date.now()
  void getDatabase().then(db => { const event = { event_id: dedupeKey ? stableEventId(action, dedupeKey) : crypto.randomUUID(), occurred_at: new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }), device_id: db.getConfig('device_id') || 'unknown', runtime: detectPlatformRuntime(), page: location.pathname, event_type: 'interaction', action, result: String(metadata.result || 'accepted'), metadata: sanitizeBehaviorMetadata(metadata, action) }; db.addBehaviorEvent(event); db.trimBehaviorEvents(); return flushBehaviorEvents() }).catch(() => {})
}

setPlatformFetchAuditSink(detail => { if (Date.now() - intentAt > 5000 || excludedRequest.test(detail.url)) return; const path = (() => { try { return new URL(detail.url, location.origin).pathname } catch { return '' } })(); recordBehavior('api.request_result', { method: detail.method, path, status: detail.status, result: detail.ok ? 'succeeded' : 'failed', error_code: detail.errorCode || '' }) })

export async function flushBehaviorEvents(): Promise<void> {
  if (flushing || !runtime?.serverUrl || !runtime.authToken) return
  flushing = true
  try { const current = runtime; const db = await getDatabase(); const rows = db.listBehaviorEvents(50); if (!rows.length || !current) return; const response = await fetch(`${current.serverUrl.replace(/\/$/, '')}/api/v1/behavior-events/batch`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${current.authToken}` }, body: JSON.stringify({ events: rows.map((row: any) => ({ ...row, metadata: JSON.parse(row.metadata_json || '{}') })) }) }); if (!response.ok || runtime !== current) throw new Error('audit_upload_failed'); const body = await response.json(); db.deleteBehaviorEvents(body.accepted || []) } catch { if (!retryTimer && runtime) retryTimer = setTimeout(() => { retryTimer = null; void flushBehaviorEvents() }, 5000) } finally { flushing = false }
}
