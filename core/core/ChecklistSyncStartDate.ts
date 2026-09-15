export const DEFAULT_STATISTICS_START_DATE = '2026-08-17'
export const DEFAULT_CHECKLIST_SYNC_START_DATE = DEFAULT_STATISTICS_START_DATE

export interface ChecklistSyncStartDate {
  date: string
  compactDate: string
  beijingStartDateTime: string
  utcStartForTickTickCompleted: string
}

const parseValidDate = (value: unknown): string | null => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) return null
  return value
}

const formatTickTickUtc = (date: string): string => {
  const [year, month, day] = date.split('-').map(Number)
  const utcMillis = Date.UTC(year, month - 1, day) - 8 * 60 * 60 * 1000
  return new Date(utcMillis).toISOString().replace('.000Z', '+0000')
}

export const resolveChecklistSyncStartDate = (value: unknown): ChecklistSyncStartDate => {
  const date = parseValidDate(value) ?? DEFAULT_STATISTICS_START_DATE
  return {
    date,
    compactDate: date.replaceAll('-', ''),
    beijingStartDateTime: `${date} 00:00:00`,
    utcStartForTickTickCompleted: formatTickTickUtc(date),
  }
}

export const resolveStatisticsStartDate = resolveChecklistSyncStartDate
