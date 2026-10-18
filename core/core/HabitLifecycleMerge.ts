import { terminateHabitOutbox, type HabitQuery, type HabitSql } from './HabitLifecycleOutbox'

export function planHabitLifecycle(query: HabitQuery, row: any, upsert: HabitSql | null, now: string): HabitSql[] | null | undefined {
  const id = String(row.id)
  const local = query('SELECT * FROM habits WHERE id=?', [id])[0]
  const tomb = query('SELECT * FROM habit_tombstones WHERE habit_id=?', [id])[0]
  const version = Number(row.lifecycle_version ?? row.server_version ?? 0)
  const deleted = (row._sync_operation || row.operation) === 'delete'
  const restore = row._lifecycle_restore === true || Number(row.restored_version || 0) > Number(tomb?.server_version || 0)
  if (tomb && !deleted && !restore) return null
  if (version < Number(local?.lifecycle_version || 0)) return null
  if (row.source !== 'ticktick' || !Number.isSafeInteger(version) || version <= 0) return undefined
  if (local?.source === 'local') throw new Error('habit_source_conflict')
  if (deleted && (!row.provider_binding_id || !row.provider_id || !row.evidence)) throw new Error('habit_delete_evidence_missing')
  if (version < Number(tomb?.server_version || 0)) return null
  if (deleted && tomb?.server_version === version && !local) return null
  if (!deleted && version === Number(local?.lifecycle_version || 0)) return null
  const reason = row.archive_reason === 'provider_habit_sync_disabled' ? row.archive_reason : 'provider_lifecycle'
  const operations = deleted || Number(row.is_active) === 1 ? terminateHabitOutbox(query, id, version, now, reason) : []
  if (!deleted) {
    if (!upsert) throw new Error('invalid_habit_upsert')
    if (tomb && restore) operations.push({ sql: 'DELETE FROM habit_tombstones WHERE habit_id=?', params: [id], internal: true })
    return [...operations, upsert]
  }
  return [...operations,
    { sql: 'DELETE FROM habit_checkins WHERE habit_id=?', params: [id], internal: true },
    { sql: `INSERT INTO habit_tombstones VALUES(?,?,?,?,?,?) ON CONFLICT(habit_id) DO UPDATE SET
      binding_id=excluded.binding_id,provider_id=excluded.provider_id,deleted_at=excluded.deleted_at,
      evidence=excluded.evidence,server_version=excluded.server_version`,
      params: [id,row.provider_binding_id,row.provider_id,row.deleted_at || now,row.evidence,version], internal: true },
    { sql: 'DELETE FROM habits WHERE id=?', params: [id], table: 'habits', recordId: id },
  ]
}
