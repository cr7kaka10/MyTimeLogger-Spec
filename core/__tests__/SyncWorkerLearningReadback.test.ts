import { describe, expect, it, vi } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

describe('learning command readback', () => {
  it('pulls a newly saved KR even inside the passive dedupe window', async () => {
    const remote = [{ id: 'new-kr', title: '新 KR' }]
    const local: typeof remote = []
    const worker = new SyncWorker({ enableSSE: false }) as any
    worker._api = {}
    worker._db = {}
    worker._lastPassivePullAt = Date.now()
    worker._pullAndMergeResult = vi.fn(async () => {
      local.push(...remote)
      return { ok: true, merged: remote.length }
    })

    const passive = await worker.pullAndMergeResult(false, { scope: 'core', reason: 'server-readback' })
    expect(passive.diagnostics?.reason).toBe('dedupe_window')
    expect(local).toEqual([])

    const action = await worker.pullAndMergeResult(false, { scope: 'core', reason: 'user-action' })
    expect(action).toMatchObject({ ok: true, merged: 1 })
    expect(worker._pullAndMergeResult).toHaveBeenCalledTimes(1)
    expect(local).toEqual(remote)
  })
})
