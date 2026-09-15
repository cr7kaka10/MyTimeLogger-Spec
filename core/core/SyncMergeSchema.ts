export type SchemaFailure = {
  ok: false
  error: 'schema_missing_required_column'
  missingColumns: string[]
}

export type FilteredPayload = {
  ok: true
  row: Record<string, any>
  filteredColumns: string[]
}

export function validateMergeSchema(
  columns: Set<string> | null,
  requiredColumns: readonly string[],
): SchemaFailure | { ok: true } {
  if (columns === null) return { ok: true }
  const missingColumns = requiredColumns.filter(column => !columns.has(column))
  return missingColumns.length
    ? { ok: false, error: 'schema_missing_required_column', missingColumns }
    : { ok: true }
}

export function filterMergePayload(
  source: Record<string, any>,
  columns: Set<string> | null,
): FilteredPayload {
  if (columns === null) return { ok: true, row: { ...source }, filteredColumns: [] }
  const row: Record<string, any> = {}
  const filteredColumns: string[] = []
  for (const [key, value] of Object.entries(source)) {
    if (columns.has(key)) row[key] = value
    else filteredColumns.push(key)
  }
  return { ok: true, row, filteredColumns }
}
