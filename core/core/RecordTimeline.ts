import { parseBeijingDateTimeMs } from './BeijingTime'

type TimelineRecord = { start_time?: unknown; end_time?: unknown; id?: unknown }

const timeValue = (value: unknown): number => {
  if (typeof value !== 'string' || !value.trim()) return Number.NEGATIVE_INFINITY
  const parsed = parseBeijingDateTimeMs(value)
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY
}

export function recordOnlyTimeline<T extends TimelineRecord>(sessions: T[]): T[] {
  return [...sessions].sort((a, b) =>
    timeValue(b.start_time) - timeValue(a.start_time)
    || timeValue(b.end_time) - timeValue(a.end_time)
    || String(b.id ?? '').localeCompare(String(a.id ?? ''), undefined, { numeric: true }),
  )
}
