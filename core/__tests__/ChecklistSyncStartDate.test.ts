import { describe, expect, it } from 'vitest'
import {
  DEFAULT_CHECKLIST_SYNC_START_DATE,
  resolveChecklistSyncStartDate,
} from '../core/ChecklistSyncStartDate'

describe('resolveChecklistSyncStartDate', () => {
  it.each([undefined, null, '', 'invalid', '2026-02-30'])('falls back for %s', value => {
    expect(resolveChecklistSyncStartDate(value).date).toBe(DEFAULT_CHECKLIST_SYNC_START_DATE)
  })

  it('derives Beijing and TickTick date formats', () => {
    expect(resolveChecklistSyncStartDate('2026-07-01')).toEqual({
      date: '2026-07-01',
      compactDate: '20260701',
      beijingStartDateTime: '2026-07-01 00:00:00',
      utcStartForTickTickCompleted: '2026-06-30T16:00:00+0000',
    })
  })
})
