import type { IDatabaseAdapter } from '../db'
export type AndroidBulkOperation = { sql: string; params?: any[] }
export type AndroidBulkCapability = {
  query: (sql: string, params?: any[]) => any[]
  transaction: (operations: AndroidBulkOperation[]) => void
  yieldToUi: () => Promise<void>
}
export type AndroidBulkDatabaseAdapter = IDatabaseAdapter & { androidBulk: AndroidBulkCapability }
export const getAndroidBulkCapability = (value: unknown): AndroidBulkCapability | undefined =>
  (value as { androidBulk?: AndroidBulkCapability } | null)?.androidBulk
type NativeBridge = {
  open(name: string): string
  execute(sql: string, parametersJson: string): string
  query(sql: string, parametersJson: string): string
  transaction(operationsJson: string): string
}
type BridgeResult = { ok: boolean; error?: string; rows?: any[]; operation?: string; index?: number; error_category?: string }
type BridgeHost = { MyTimeLoggerSqlite?: NativeBridge }
export class SqliteBridgeError extends Error {
  readonly operation?: string
  readonly index?: number
  readonly errorCategory: string
  constructor(result: BridgeResult) {
    const category = result.error_category || 'unknown'
    super(`${result.error || 'sqlite_bridge_failed'}:${category}`)
    this.name = 'SqliteBridgeError'
    this.operation = result.operation
    this.index = result.index
    this.errorCategory = category
  }
}
export function accountDatabaseName(storageKey: string): string {
  if (!/^acct-[a-f0-9]{32}$/i.test(storageKey)) throw new Error('invalid_account_storage_key')
  return `mtl-${storageKey.toLowerCase()}.db`
}
const decode = (raw: string): BridgeResult => {
  const result = JSON.parse(raw) as BridgeResult
  if (!result.ok) throw new SqliteBridgeError(result)
  return result
}

export function createCapacitorDatabaseAdapter(host: BridgeHost = window as unknown as BridgeHost, name = 'mtl-bootstrap.db'): AndroidBulkDatabaseAdapter {
  const bridge = host.MyTimeLoggerSqlite
  if (!bridge) throw new Error('sqlite_bridge_unavailable')
  decode(bridge.open(name))
  const query = (sql: string, params: any[] = []) => decode(bridge.query(sql, JSON.stringify(params))).rows ?? []
  return {
    run: (sql, params = []) => { decode(bridge.execute(sql, JSON.stringify(params))) },
    exec: sql => { decode(bridge.execute(sql, '[]')) },
    prepare: sql => {
      let rows: any[] = []; let cursor = 0; let bound = false
      const bind = (params: any[] = []) => { rows = query(sql, params); cursor = 0; bound = true }
      return {
        bind,
        step: () => { if (!bound) bind(); return cursor < rows.length },
        getAsObject: () => rows[cursor++],
        free: () => { rows = []; bound = false },
      }
    },
    androidBulk: {
      query,
      transaction: operations => { decode(bridge.transaction(JSON.stringify(operations))) },
      yieldToUi: () => new Promise(resolve => setTimeout(resolve, 0)),
    },
  }
}
