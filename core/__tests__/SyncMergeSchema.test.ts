import { describe, expect, it } from 'vitest'
import { filterMergePayload, validateMergeSchema } from '../core/SyncMergeSchema'

describe('SyncMergeSchema', () => {
  it('rejects missing required columns before SQL generation', () => {
    expect(validateMergeSchema(new Set(['id', 'date']), ['id', 'pulled_at'])).toEqual({
      ok: false,
      error: 'schema_missing_required_column',
      missingColumns: ['pulled_at'],
    })
  })

  it('filters unknown payload columns without retaining their values', () => {
    const result = filterMergePayload(
      { id: 7, title: 'safe', future_field: 'private-value' },
      new Set(['id', 'title', 'pulled_at']),
    )
    expect(result.row).toEqual({ id: 7, title: 'safe' })
    expect(result.filteredColumns).toEqual(['future_field'])
    expect(JSON.stringify(result)).not.toContain('private-value')
  })
})
