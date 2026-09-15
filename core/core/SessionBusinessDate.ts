import { formatBeijingDate, parseBeijingDateTimeMs } from './BeijingTime'

const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000

const nextBeijingMidnightMs = (value: number): number => {
  const beijing = new Date(value + BEIJING_OFFSET_MS)
  return Date.UTC(beijing.getUTCFullYear(), beijing.getUTCMonth(), beijing.getUTCDate() + 1) - BEIJING_OFFSET_MS
}

/** Return the Beijing date covered for the longest duration; a tie belongs to the later day. */
export function sessionBusinessDate(startTime: string, endTime: string, fallback = ''): string {
  const start = parseBeijingDateTimeMs(startTime)
  const end = parseBeijingDateTimeMs(endTime)
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return fallback

  const coverage = new Map<string, number>()
  for (let cursor = start; cursor < end;) {
    const segmentEnd = Math.min(end, nextBeijingMidnightMs(cursor))
    const date = formatBeijingDate(new Date(cursor))
    coverage.set(date, (coverage.get(date) ?? 0) + segmentEnd - cursor)
    cursor = segmentEnd
  }
  return [...coverage.keys()].reduce((winner, date) => {
    const winnerDuration = coverage.get(winner) ?? 0
    const duration = coverage.get(date) ?? 0
    return duration > winnerDuration || (duration === winnerDuration && date > winner) ? date : winner
  })
}
