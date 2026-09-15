import { attachAndroidBulkCapability, attachAndroidCredentialFacade, createDatabaseFacade, formatSyncProgress } from './db'
import { createSecureCredentialsService, loadSecureCredentialView, setSecureCredential } from './platform/credentials'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }

let creates = 0
let release!: () => void
const ready = new Promise<void>(resolve => { release = resolve })
const expected = {}
const getDatabase = createDatabaseFacade(async () => {
  creates += 1
  await ready
  return expected
})

const first = getDatabase()
const second = getDatabase()
assert(creates === 1, 'concurrent calls should initialize once')
release()
assert(await first === expected && await second === expected, 'concurrent calls should resolve the same instance')
assert(await getDatabase() === expected && creates === 1, 'later calls should reuse the cached instance')
const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const dbSource = fs.readFileSync(new URL('./db.ts', import.meta.url), 'utf8') as string
assert(!dbSource.includes('schema.initDatabase'), 'Database constructor must be the only Schema initialization owner')
assert(dbSource.includes('if (!_syncWorker) await getDatabase().catch(() => {})') && dbSource.includes('if (!_syncWorker && _syncWorkerInitPromise) await _syncWorkerInitPromise.catch(() => {})'), 'first sync must wait for database and SyncWorker initialization')
assert(dbSource.indexOf("db.setConfig('account_identity_key', activeAccountStorageKey)") < dbSource.indexOf('await refreshSyncConfiguration(db)'), 'account identity must exist before SyncWorker initialization')
assert(dbSource.includes('readActiveAccountStorageKey()') && dbSource.includes('accountDatabaseName(accountStorageKey)') && dbSource.includes('await loadScopedCredentialView(accountStorageKey)'), 'Android cold start must restore the active account database and its scoped token before configuration reads')
const settingsSource = fs.readFileSync(new URL('./hooks/useSettings.ts', import.meta.url), 'utf8') as string
assert(settingsSource.includes("!db.getConfig('account_identity_key')") && settingsSource.includes('activateAccountStorage(createAccountIdentity(activeProfile.serverUrl, userId))'), 'Android saved sessions must restore the account database before syncing')
assert(settingsSource.includes('writeActiveAccountStorageKey(createAccountIdentity(url, userId).storageKey)') && settingsSource.includes('clearActiveAccountStorageKey()'), 'Android login and logout must manage the account recovery pointer')
const retryAt = Date.UTC(2026, 6, 21, 5, 52, 20)
const backoff = formatSyncProgress({ error: 'local_merge_backoff', diagnostics: { stage: 'backoff', retry_at: retryAt } })
assert(backoff === '下次 13:52:20' && !backoff.includes('0/0'), 'backoff must show only the truthful Beijing retry time')
const attempted = formatSyncProgress({ diagnostics: { merge: { applied: 3, failed: 1, conflicts: ['one'], retry_at: retryAt } } })
assert(attempted === '合并失败 · 下次 13:52:20', 'failed merge must not present attempted rows as failed work')
const resetFailure = formatSyncProgress({ error: 'sync_failed', diagnostics: { merge: { applied: 112 } } })
assert(resetFailure === '合并失败', 'reset deletion count must never be presented as a failed task count')
for (const file of ['./hooks/useTimeBook.ts', './hooks/useChecklist.ts']) {
  const source = fs.readFileSync(new URL(file, import.meta.url), 'utf8') as string
  assert(source.includes('上一轮本地合并失败，等待自动重试'), `${file} must explain why automatic retry is waiting`)
}

const bulk = { query: () => [], transaction: () => {}, yieldToUi: async () => {} }
const androidBulkDb: any = {}
attachAndroidBulkCapability(androidBulkDb, { androidBulk: bulk })
assert(androidBulkDb.androidBulk === bulk, 'Android Database instance must expose adapter bulk capability')
const electronDb: any = {}
attachAndroidBulkCapability(electronDb, { run() {}, exec() {}, prepare() { throw new Error('unused') } })
assert(electronDb.androidBulk === undefined, 'Electron Database instance must not gain Android bulk capability')

const stored = new Map<string, string>()
let rejectSecureWrite = false
const storage = { getItem: async (key: string) => stored.get(key) ?? null, setItem: async (key: string, value: string) => { if (rejectSecureWrite) throw new Error('storage failed'); stored.set(key, value) }, removeItem: async (key: string) => { stored.delete(key) } }
await loadSecureCredentialView(createSecureCredentialsService('capacitor-android', storage as any))
await setSecureCredential('env_development_auth_token', 'keystore-token')
const writes: Array<{ sql: string, params: any[] }> = []
let ordinaryWrite = ''
const androidDb: any = {
  runInTransaction: (fn: () => void) => fn(),
  allRaw: (sql: string, params: any[] = []) => sql.includes('sync_outbox')
    ? [{ id: 1, record_id: 'env_development_auth_token', payload_json: '{}' }, { id: 2, record_id: 'atimelogger_config', payload_json: JSON.stringify({ value: JSON.stringify({ username: 'u', password: 'WEB_ENC:secret' }) }) }]
    : params[0] === 'atimelogger_config' ? [{ value: JSON.stringify({ username: 'u', password: 'WEB_ENC:secret' }) }] : [],
  runRaw: (sql: string, params: any[] = []) => { writes.push({ sql, params }) },
  getConfig: (key: string) => key === 'theme' ? 'dark' : 'sqlite-secret',
  getAllConfig: () => ({ theme: 'dark', env_development_auth_token: 'sqlite-secret' }),
  setConfig: (key: string) => { ordinaryWrite = key },
}
attachAndroidCredentialFacade(androidDb)
assert(androidDb.getConfig('env_development_auth_token') === 'keystore-token', 'Android getConfig must read credential view')
assert(androidDb.getAllConfig().env_development_auth_token === 'keystore-token' && androidDb.getAllConfig().theme === 'dark', 'Android getAllConfig must merge secure values')
androidDb.setConfig('theme', 'light'); assert(ordinaryWrite === 'theme', 'ordinary settings must keep Database behavior')
await androidDb.setSecureConfig('env_development_auth_token', 'rotated-token')
assert(stored.get('mtl.credential.env_development_auth_token') === 'rotated-token', 'awaited secure writes must finish before session commit')
rejectSecureWrite = true; let secureWriteRejected = false
try { await androidDb.setSecureConfig('env_development_auth_token', 'not-persisted') } catch { secureWriteRejected = true }
assert(secureWriteRejected && androidDb.getConfig('env_development_auth_token') === 'rotated-token', 'failed secure writes must not mark the new session recoverable')
assert(writes.some(write => write.sql.includes('DELETE FROM sync_outbox') && write.params[0] === 1), 'legacy sensitive outbox row must be deleted')
assert(writes.filter(write => write.sql.includes('UPDATE')).every(write => !JSON.stringify(write.params).includes('WEB_ENC:secret')), 'legacy parent JSON and outbox payload must be scrubbed')
assert(dbSource.includes('mtl.runtime.widget.active_database_name'), 'initDatabase must write the active database name to Preferences for the Android widget')

console.log('database facade tests passed')
