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

export function dateToShanghaiDateString(date: Date): string {
  const parts = partsInShanghai(date)
  return `${parts.year}-${parts.month}-${parts.day}`
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

export function normalizeShanghaiDate(value: string | null | undefined): string {
  if (!value) return ''
  const normalized = normalizeShanghaiDateTime(value)
  return normalized ? normalized.slice(0, 10) : ''
}

export function normalizeTaskTimeFields(task: Record<string, any>): Record<string, any> {
  const result = { ...task }
  const fields = ['dueDate', 'completedTime', 'modifiedTime', 'startDate']
  for (const field of fields) {
    if (result[field]) result[field] = normalizeShanghaiDateTime(result[field])
  }
  if (result.due_date) result.due_date = normalizeShanghaiDateTime(result.due_date)
  return result
}

export function tickTickDateToShanghaiDateString(value: string): string {
  if (!value) return ''
  if (!value.includes('T')) return value.slice(0, 10)
  const date = new Date(normalizeOffset(value))
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  return dateToShanghaiDateString(date)
}

export function formatTickTickDueDate(value: string): string {
  if (!value) return ''
  try {
    const normalized = normalizeShanghaiDateTime(value)
    const date = new Date(normalized.includes(' ') ? normalized.replace(' ', 'T') + '+08:00' : normalizeOffset(normalized))
    if (Number.isNaN(date.getTime())) return value
    const parts = partsInShanghai(date)
    const today = dateToShanghaiDateString(new Date())
    const dueDate = `${parts.year}-${parts.month}-${parts.day}`
    const hasTime = !(parts.hour === '00' && parts.minute === '00' && parts.second === '00')
    const prefix = dueDate === today ? '今天' : `${Number(parts.month)}/${Number(parts.day)}`
    return hasTime ? `${prefix} ${parts.hour}:${parts.minute}` : `${prefix} 全天`
  } catch {
    return value
  }
}
