export type HabitSql = { sql: string; params: any[]; table?: string; recordId?: string; internal?: boolean }
export type HabitQuery = (sql: string, params?: any[]) => any[]

export function terminateHabitOutbox(query: HabitQuery, id: string, version: number, now: string): HabitSql[] {
  const rows = query(`SELECT * FROM sync_outbox WHERE status IN ('pending','failed','sending') AND
    ((table_name='habits' AND record_id=?) OR (table_name='habit_checkins' AND
    (record_id IN (SELECT id FROM habit_checkins WHERE habit_id=?) OR
    CASE WHEN json_valid(payload_json) THEN json_extract(payload_json,'$.habit_id') END=?)))`, [id,id,id])
  return rows.flatMap(row => [
    { sql: 'INSERT OR IGNORE INTO habit_lifecycle_outbox_audit VALUES(?,?,?,?,?,?)',
      params: [row.id,id,JSON.stringify(row),'provider_lifecycle',version,now], internal: true },
    { sql: "UPDATE sync_outbox SET status='terminated',last_error='provider_lifecycle',updated_at=? WHERE id=?",
      params: [now,row.id], internal: true },
  ])
}
