const BEIJING_TIME_ZONE = 'Asia/Shanghai'
const BEIJING_OFFSET_HOURS = 8

function beijingParts(date: Date): Record<string, string> {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: BEIJING_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
  return Object.fromEntries(formatter.formatToParts(date).map(part => [part.type, part.value]))
}

export function formatBeijingDate(date = new Date()): string {
  const parts = beijingParts(date)
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function formatBeijingDateTime(date = new Date()): string {
  const parts = beijingParts(date)
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}

export function formatBeijingDateTimeLocalSeconds(date = new Date()): string {
  return formatBeijingDateTime(date).replace(' ', 'T')
}

export function beijingDayName(date = new Date()): string {
  const dayNames = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']
  const parts = beijingParts(date)
  return dayNames[new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day))).getUTCDay()]
}

export function parseBeijingDateTimeMs(value?: string | null): number {
  if (!value) return NaN
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:T|\s)(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z)?$/)
  if (!match) return Date.parse(value)
  if (match[7]) return Date.parse(value)
  const [, year, month, day, hour, minute, second = '00'] = match
  return Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour) - BEIJING_OFFSET_HOURS,
    Number(minute),
    Number(second),
  )
}

export function beijingDateTimeToUtcIso(value: string): string {
  if (value.endsWith('Z')) return value
  return new Date(parseBeijingDateTimeMs(value)).toISOString()
}

