import { afterEach, describe, expect, it, vi } from 'vitest'
import { createUserActionSyncScheduler } from '../../ui/src/utils/userActionSync'

describe('user action core sync scheduler', () => {
  afterEach(() => vi.useRealTimers())

  it('coalesces navigation, ledger opening, click, change and submit bursts', async () => {
    vi.useFakeTimers()
    const synchronize = vi.fn(async () => undefined)
    const scheduler = createUserActionSyncScheduler(synchronize)
    for (const _action of ['tab', 'ledger', 'click', 'change', 'submit']) scheduler.request()
    await vi.advanceTimersByTimeAsync(350)
    expect(synchronize).toHaveBeenCalledTimes(1)
    scheduler.dispose()
  })

  it('runs one trailing sync for actions during an in-flight request', async () => {
    vi.useFakeTimers()
    let complete: (() => void) | undefined
    const synchronize = vi.fn()
      .mockImplementationOnce(() => new Promise<void>(resolve => { complete = resolve }))
      .mockResolvedValue(undefined)
    const scheduler = createUserActionSyncScheduler(synchronize)
    scheduler.request()
    await vi.advanceTimersByTimeAsync(350)
    scheduler.request(); scheduler.request()
    await vi.advanceTimersByTimeAsync(350)
    expect(synchronize).toHaveBeenCalledTimes(1)
    complete?.()
    await vi.advanceTimersByTimeAsync(0)
    expect(synchronize).toHaveBeenCalledTimes(2)
    scheduler.dispose()
  })
})
