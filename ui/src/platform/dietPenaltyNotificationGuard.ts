type DietRow = { rule_key: string; status: string; occurred_at?: string }
type OutboxRow = { table_name: string; record_id: string; payload_json: string }
type LedgerRow = { source_type: string; source_id?: string; id?: string; target_date?: string }

export function hasEarlierLocalDietCheckin(fact: LedgerRow, rows: DietRow[], outbox: OutboxRow[]): boolean {
  if (fact.source_type !== 'exercise_diet_penalty') return false
  const parts = String(fact.source_id || fact.id || '').split(':')
  const rule = parts.at(-1) || ''; const date = fact.target_date || parts[2]
  const cutoff = ({ breakfast_on_time: '08:30:00', lunch_on_time: '13:31:00', dinner_on_time: '19:01:00' } as Record<string, string>)[rule]
  if (!date || !cutoff) return false
  const valid = (row: DietRow) => row.rule_key === rule && row.status === 'completed'
    && Boolean(row.occurred_at && row.occurred_at.replace('T', ' ') < `${date} ${cutoff}`)
  if (rows.some(valid)) return true
  const recordId = `diet:${parts[1]}:${date}:${parts[3]}:${rule}`
  return outbox.some(entry => {
    if (entry.table_name !== 'exercise_diet_checkins' || entry.record_id !== recordId) return false
    try { return valid(JSON.parse(entry.payload_json)) } catch { return false }
  })
}
