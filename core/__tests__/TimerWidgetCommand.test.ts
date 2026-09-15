import { describe, expect, it } from 'vitest'
import { parseTimerWidgetCommand } from '../core/TimerWidgetCommand'

const valid = { action: 'start', commandId: 'widget-1', categoryId: 7, eventEpochMs: 1_721_337_600_000 }

describe('TimerWidgetCommand', () => {
  it.each(['start', 'switch', 'stop'] as const)('accepts %s only with the whitelisted fields', action => {
    expect(parseTimerWidgetCommand({ ...valid, action })).toEqual({ ok: true, command: { ...valid, action } })
  })

  it.each([
    { ...valid, action: 'pause' },
    { commandId: valid.commandId, categoryId: valid.categoryId, eventEpochMs: valid.eventEpochMs },
    { ...valid, note: 'secret' },
    { ...valid, URL: 'https://invalid.example' },
    { ...valid, SQL: 'DELETE FROM study_sessions' },
  ])('rejects unknown, missing or extra input: %j', candidate => {
    expect(parseTimerWidgetCommand(candidate)).toEqual({ ok: false, reason: 'invalid-command' })
  })
})
