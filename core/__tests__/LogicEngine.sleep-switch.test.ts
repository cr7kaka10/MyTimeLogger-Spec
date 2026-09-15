import { describe, expect, it } from 'vitest'
import { LogicEngine } from '../core/LogicEngine'

describe('LogicEngine sleep switch', () => {
  it('收束运行会话后只按同一命令启动一次睡觉计时', () => {
    const engine = new LogicEngine()
    const committed: unknown[] = []
    engine.setCallbacks({ onStateChange: () => {}, onTick: () => {}, onAudioCue: () => {},
      onSummaryRequested: () => {}, onPauseReasonRequested: () => {}, onSessionCommitted: item => committed.push(item) })
    engine.start(3, '娱乐')

    expect(engine.applySleepSwitch('sleep-command:1:2026-08-28', 14)).toMatchObject({ ok: true, replayed: false })
    expect(engine).toMatchObject({ state: 'countup_studying', currentCategoryId: 14, currentCategoryName: '睡觉' })
    expect(committed).toHaveLength(1)
    expect(engine.applySleepSwitch('sleep-command:1:2026-08-28', 14)).toMatchObject({ ok: true, replayed: true })
    expect(committed).toHaveLength(1)
  })
})
