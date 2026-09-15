const SHANGHAI_TIME_ZONE = 'Asia/Shanghai'

function normalizeOffset(value: string): string {
  if (value.endsWith('+0000')) return `${value.slice(0, -5)}+00:00`
  if (/([+-]\d{2})(\d{2})$/.test(value)) return value.replace(/([+-]\d{2})(\d{2})$/, '$1:$2')
  return value.replace('Z', '+00:00')
}

function partsInShanghai(date: Date): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: SHANGHAI_TIME_ZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date).map(part => [part.type, part.value]),
  )
}

export function dateToShanghaiDateTimeString(date: Date): string {
  const parts = partsInShanghai(date)
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}

export function nowShanghaiDateTimeString(): string {
  return dateToShanghaiDateTimeString(new Date())
}

export function normalizeShanghaiDateTime(value: string | null | undefined): string {
  if (!value) return ''
  const text = String(value).trim()
  if (!text) return ''
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) return text
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return `${text} 00:00:00`
  const date = new Date(normalizeOffset(text))
  if (Number.isNaN(date.getTime())) return text
  return dateToShanghaiDateTimeString(date)
}

export function normalizeTaskTimeFields(task: Record<string, any>): Record<string, any> {
  const result = normalizeTaskRecordForDb(task)
  return result
}

export function normalizeTaskRecordForDb(task: Record<string, any>): Record<string, any> {
  const result = { ...task }
  for (const [field, value] of Object.entries(result)) {
    if (value && typeof value === 'string' && isTimeField(field)) {
      result[field] = normalizeShanghaiDateTime(value)
    }
  }
  const rawDueDate = result.due_date || result.dueDate
  if (rawDueDate) result.due_date = normalizeShanghaiDateTime(rawDueDate)
  if ('tags' in result) {
    result.tags = normalizeTaskTagsForDb(result.tags)
  }
  if (result.raw_json) {
    result.raw_json = normalizeTaskRawJson(result.raw_json)
  }
  return result
}

export function normalizeTaskTagsForDb(value: any): string {
  if (Array.isArray(value)) return JSON.stringify(value.map(String).filter(Boolean))
  if (value == null || value === '') return JSON.stringify([])
  if (typeof value !== 'string') return JSON.stringify([])
  const text = value.trim()
  if (!text) return JSON.stringify([])
  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) return JSON.stringify(parsed.map(String).filter(Boolean))
    if (typeof parsed === 'string') return JSON.stringify(parsed ? [parsed] : [])
    return JSON.stringify([])
  } catch {
    return JSON.stringify(text.split(',').map(tag => tag.trim()).filter(Boolean))
  }
}

export function normalizeTaskRawJson(value: any): string {
  if (!value) return value == null ? '' : String(value)
  try {
    const payload = typeof value === 'string' ? JSON.parse(value) : { ...value }
    const normalized = { ...payload }
    for (const [field, fieldValue] of Object.entries(normalized)) {
      if (fieldValue && typeof fieldValue === 'string' && isTimeField(field)) {
        normalized[field] = normalizeShanghaiDateTime(fieldValue)
      }
    }
    const rawDueDate = normalized.due_date || normalized.dueDate
    if (rawDueDate) normalized.due_date = normalizeShanghaiDateTime(rawDueDate)
    return JSON.stringify(normalized)
  } catch {
    return String(value)
  }
}

const TIME_FIELD_EXCLUDES = new Set(['timeZone', 'timezone', 'isAllDay'])

function isTimeField(field: string): boolean {
  if (TIME_FIELD_EXCLUDES.has(field)) return false
  const lowered = field.toLowerCase()
  return (
    lowered.endsWith('date') ||
    lowered.endsWith('time') ||
    lowered.endsWith('_at') ||
    lowered.endsWith('_time') ||
    lowered.endsWith('_date')
  )
}
