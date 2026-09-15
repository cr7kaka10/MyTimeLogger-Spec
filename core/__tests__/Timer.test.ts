import { describe, it, expect } from 'vitest'
import { Timer } from '../core/Timer'

describe('Timer', () => {
  it('倒计时: 正常结束触发 onFinish', async () => {
    const timer = new Timer()
    const result = await new Promise<{ finished: boolean; remaining: number }>(resolve => {
      timer.start(300, 'countdown', {
        onTick: () => {},
        onFinish: () => resolve({ finished: true, remaining: 0 }),
      })
      // 300ms 后应触发 finish
      setTimeout(() => resolve({ finished: false, remaining: timer.getElapsed() }), 500)
    })

    expect(result.finished).toBe(true)
  })

  it('正计时: 不会自动结束', async () => {
    const timer = new Timer()
    const ticks: number[] = []
    await new Promise<void>(resolve => {
      timer.start(0, 'countup', {
        onTick: (elapsed) => { ticks.push(elapsed) },
        onFinish: () => {},
      })
      setTimeout(() => {
        timer.stop()
        resolve()
      }, 300)
    })
    expect(ticks.length).toBeGreaterThanOrEqual(1)
    expect(ticks[ticks.length - 1]).toBeGreaterThan(0)
  })

  it('pause/resume: 暂停恢复精度', async () => {
    const timer = new Timer()
    timer.start(5000, 'countdown', {
      onTick: () => {},
      onFinish: () => {},
    })
    await delay(100)
    timer.pause()
    const afterPause = timer.getElapsed()

    await delay(100)
    // 暂停期间计时不应增长
    expect(timer.getElapsed()).toBe(afterPause)

    timer.resume()
    await delay(100)
    expect(timer.getElapsed()).toBeGreaterThan(afterPause)
    timer.stop()
  })

  it('stop: 返回经过时间', () => {
    const timer = new Timer()
    timer.start(5000, 'countdown', { onTick: () => {}, onFinish: () => {} })
    const { elapsedMs } = timer.stop()
    expect(elapsedMs).toBeGreaterThanOrEqual(0)
    expect(timer.running).toBe(false)
  })
})

function delay(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms))
}
