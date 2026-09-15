import { describe, expect, it } from 'vitest'
import { ApiClient } from '../core/ApiClient'
import { SyncWorker } from '../core/SyncWorker'

describe('account-bound SyncWorker', () => {
  it('refuses a database whose account identity differs from the worker', async () => {
    const worker = new SyncWorker({ identityKey: 'acct-0123456789abcdef0123456789abcdef' })
    const db = {
      getConfig: () => 'acct-fedcba9876543210fedcba9876543210',
      setEnqueue: () => undefined,
    }
    worker.bind(new ApiClient('https://server.example', 'temporary-token'), db as any)
    await expect(worker.pushOnly()).resolves.toMatchObject({ ok: false, error: 'account_identity_mismatch' })
  })
})
