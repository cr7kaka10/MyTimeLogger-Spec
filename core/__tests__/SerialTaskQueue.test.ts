import { describe, expect, it } from 'vitest'
import { SerialTaskQueue } from '../core/SerialTaskQueue'

describe('SerialTaskQueue priorities', () => {
  it('runs one task at a time and preserves same-priority FIFO', async () => {
    const queue = new SerialTaskQueue(); const order: string[] = []; let release!: () => void
    const gate = new Promise<void>(resolve => { release = resolve })
    const first = queue.enqueueMaintenance(async () => { order.push('m1-start'); await gate; order.push('m1-end') })
    const second = queue.enqueueMaintenance(async () => { order.push('m2') })
    await Promise.resolve(); expect(order).toEqual(['m1-start']); release(); await Promise.all([first, second])
    expect(order).toEqual(['m1-start', 'm1-end', 'm2'])
  })

  it('runs interactive work before the next maintenance item', async () => {
    const queue = new SerialTaskQueue(); const order: string[] = []; let release!: () => void
    const gate = new Promise<void>(resolve => { release = resolve })
    const m1 = queue.enqueueMaintenance(async () => { order.push('m1'); await gate })
    const m2 = queue.enqueueMaintenance(async () => { order.push('m2') })
    const live = queue.enqueueInteractive(async () => { order.push('stop') })
    release(); await Promise.all([m1, m2, live]); expect(order).toEqual(['m1', 'stop', 'm2'])
  })

  it('continues after a rejected task', async () => {
    const queue = new SerialTaskQueue(); const order: string[] = []
    const failed = queue.enqueueInteractive(async () => { throw new Error('expected') }).catch(() => order.push('failed'))
    const next = queue.enqueueInteractive(async () => { order.push('next') })
    await Promise.all([failed, next]); expect(order.sort()).toEqual(['failed', 'next'])
  })

  it('keeps live stop and note ahead of a sixteen-item backlog without concurrency', async () => {
    const queue = new SerialTaskQueue(); const order: string[] = []; let running = 0; let maxRunning = 0; let release!: () => void
    const gate = new Promise<void>(resolve => { release = resolve })
    const maintenance = Array.from({ length: 16 }, (_, index) => queue.enqueueMaintenance(async () => {
      running++; maxRunning = Math.max(maxRunning, running); order.push(`m${index}`)
      if (index === 0) await gate
      running--
    }))
    await Promise.resolve()
    const stop = queue.enqueueInteractive(async () => { running++; maxRunning = Math.max(maxRunning, running); order.push('stop'); running-- })
    const note = queue.enqueueInteractive(async () => { order.push('note') })
    release(); await Promise.all([...maintenance, stop, note])
    expect(order.slice(0, 4)).toEqual(['m0', 'stop', 'note', 'm1']); expect(maxRunning).toBe(1)
  })
})
