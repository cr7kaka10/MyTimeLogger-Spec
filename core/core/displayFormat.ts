import { parseBeijingDateTimeMs } from './BeijingTime'

export function formatHoursMinutes(totalMinutes: number): string {
  const rounded = Math.max(0, Math.round(Number.isFinite(totalMinutes) ? totalMinutes : 0))
  return `${Math.floor(rounded / 60)}h ${rounded % 60}min`
}

export function formatClockTime(value?: string | null): string {
  if (!value) return ''
  const match = value.match(/(?:T|\s)(\d{2}:\d{2})(?::(\d{2}))?/)
  return match ? `${match[1]}:${match[2] ?? '00'}` : value.slice(-8)
}

export function resolveSessionDurationSeconds(session: {
  net_duration_seconds?: number | null
  start_time?: string | null
  end_time?: string | null
  net_duration_minutes?: number | null
}): number {
  if (Number.isFinite(session.net_duration_seconds)) return Math.max(0, Math.round(session.net_duration_seconds!))
  const start = parseBeijingDateTimeMs(session.start_time)
  const end = parseBeijingDateTimeMs(session.end_time)
  if (Number.isFinite(start) && Number.isFinite(end) && end >= start) return Math.floor((end - start) / 1000)
  return Math.max(0, Math.round((session.net_duration_minutes || 0) * 60))
}

export function formatDurationHms(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(Number.isFinite(totalSeconds) ? totalSeconds : 0))
  const hh = String(Math.floor(seconds / 3600)).padStart(2, '0')
  const mm = String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

export function elapsedWholeSeconds(elapsedMs: number): number {
  return Math.max(0, Math.floor((Number.isFinite(elapsedMs) ? elapsedMs : 0) / 1000))
}
