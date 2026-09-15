import { describe, expect, it } from 'vitest'
import { applyBulkWithIsolation, planBulkMerge } from '../core/SyncBulkMerge'
import { resolve, SyncAction } from '../core/SyncResolver'

describe('SyncBulkMerge', () => {
  it('matches the existing per-record resolver for ordinary tables', () => {
    const cases = [
      { local: null, server: { id: 1 } },
      { local: { id: 2 }, server: { id: 2 } },
      { local: { id: 3 }, server: { id: 3 }, hasPendingOutbox: true },
    ]
    expect(planBulkMerge(cases).map(item => item.action)).toEqual(
      cases.map(item => resolve(item.local, item.server, item.hasPendingOutbox)),
    )
  })

  it('always pulls server-owned records', () => {
    expect(planBulkMerge([{ local: { id: 1 }, server: { id: 1 }, serverOwned: true, hasPendingOutbox: true }])[0].action)
      .toBe(SyncAction.PULL)
  })

  it('rolls back failed batches, isolates bad records, and redacts payloads', async () => {
    const committed: string[] = []
    const operations = ['good-1', 'bad', 'good-2'].map(recordId => ({
      table: 'tasks', recordId, sql: 'INSERT', params: [`private-token-${recordId}`],
    }))
    const result = await applyBulkWithIsolation(operations, batch => {
      if (batch.some(item => item.recordId === 'bad')) throw new Error('constraint failed with Authorization private-token-bad')
      committed.push(...batch.map(item => item.recordId))
    })
    expect(committed).toEqual(['good-1', 'good-2'])
    expect(result).toEqual({ applied: 2, failures: [{ table: 'tasks', recordId: 'bad', category: 'constraint' }] })
    expect(JSON.stringify(result)).not.toContain('private-token')
    expect(JSON.stringify(result)).not.toContain('Authorization')
  })
})
