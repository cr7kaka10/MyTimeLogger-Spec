import { describe, expect, it } from 'vitest'
import { sessionBusinessDate } from '../core/SessionBusinessDate'

describe('sessionBusinessDate', () => {
  it('attributes a cross-day session to the Beijing day with longer coverage', () => {
    expect(sessionBusinessDate('2026-08-30 22:30:00+08:00', '2026-08-31 08:30:00+08:00', 'old')).toBe('2026-08-31')
    expect(sessionBusinessDate('2026-08-30 12:00:00+08:00', '2026-08-31 08:00:00+08:00', 'old')).toBe('2026-08-30')
    expect(sessionBusinessDate('2026-08-30 20:00:00+08:00', '2026-08-31 04:00:00+08:00', 'old')).toBe('2026-08-31')
  })

  it('uses Beijing time for UTC input and retains fallback on invalid input', () => {
    expect(sessionBusinessDate('2026-08-30T15:00:00Z', '2026-09-01T16:00:00Z', 'old')).toBe('2026-09-01')
    expect(sessionBusinessDate('broken', '2026-08-31 08:30:00+08:00', '2026-08-30')).toBe('2026-08-30')
    expect(sessionBusinessDate('2026-08-31 08:30:00+08:00', '2026-08-31 08:30:00+08:00', '2026-08-30')).toBe('2026-08-30')
  })
})
