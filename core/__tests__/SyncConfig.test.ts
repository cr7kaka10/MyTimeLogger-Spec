import { describe, expect, it } from 'vitest'
import { SYNC_CONFIG } from '../core/SyncConfig'

describe('SYNC_CONFIG', () => {
  it('exposes sync API endpoints', () => {
    expect(SYNC_CONFIG.api.push).toBe('/api/sync/push')
    expect(SYNC_CONFIG.api.pull).toBe('/api/sync/pull')
    expect(SYNC_CONFIG.api.events).toBe('/api/sync/events')
  })

  it('matches SyncWorker timeout and retry values', () => {
    expect(SYNC_CONFIG.timeout.default).toBe(5_000)
    expect(SYNC_CONFIG.timeout.push).toBe(20_000)
    expect(SYNC_CONFIG.timeout.pull).toBe(30_000)
    expect(SYNC_CONFIG.timeout.refresh).toBe(45_000)
    expect(SYNC_CONFIG.dedupe.passivePullMs).toBe(15_000)
    expect(SYNC_CONFIG.retry.maxAttempts).toBe(5)
    expect(SYNC_CONFIG.retry.backoffMs).toBe(1_000)
  })
})
