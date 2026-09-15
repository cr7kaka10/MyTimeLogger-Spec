// @ts-ignore JSON metadata is shared with the Python sync allowlist.
import registryJson from '../../shared/protocol/sync-entities.json'

export type SyncEntityOwnership = 'client_writable' | 'server_owned' | 'mixed'
export type SyncEntityDirection = 'bidirectional' | 'pull_only'

export interface SyncEntity {
  name: string
  clientTable: string
  serverTable: string
  primaryKey: string
  naturalKeys: string[]
  ownership: SyncEntityOwnership
  direction: SyncEntityDirection
  outbox: boolean
  deletePolicy: 'tombstone' | 'hard_delete' | 'no_delete'
  serverFields: string[]
}

const registry = registryJson as { version: number; entities: SyncEntity[] }

export const SYNC_ENTITIES = registry.entities
export const SYNC_ENTITY_NAMES = SYNC_ENTITIES.map(entity => entity.clientTable)
export const clientSyncTables = (): string[] => [...SYNC_ENTITY_NAMES]

const BY_CLIENT_TABLE = new Map(SYNC_ENTITIES.map(entity => [entity.clientTable, entity]))

export function syncEntityForTable(table: string): SyncEntity {
  const entity = BY_CLIENT_TABLE.get(table)
  if (!entity) throw new Error(`Unsupported sync table: ${table}`)
  return entity
}

export function primaryKeyForTable(table: string): string {
  return syncEntityForTable(table).primaryKey
}

export function localLookupKeyForTable(table: string): string {
  const entity = syncEntityForTable(table)
  if (table === 'huawei_sleep_data' && entity.naturalKeys.includes('date')) return 'date'
  return entity.primaryKey
}

export function naturalKeysForTable(table: string): string[] {
  return [...syncEntityForTable(table).naturalKeys]
}

export function naturalKeyForRecord(table: string, row: Record<string, any>): string | null {
  const keys = naturalKeysForTable(table)
  if (keys.length === 0 || keys.some(key => row[key] == null || String(row[key]) === '')) return null
  return keys.map(key => `${key}=${String(row[key])}`).join('\u001f')
}

export function isServerOwnedTable(table: string): boolean {
  const entity = syncEntityForTable(table)
  return entity.ownership === 'server_owned' || entity.direction === 'pull_only'
}

export function isOutboxEnabledTable(table: string): boolean {
  return BY_CLIENT_TABLE.get(table)?.outbox === true
}
