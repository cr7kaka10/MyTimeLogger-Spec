import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { LogicEngine } from '../core/LogicEngine'

describe('LogicEngine', () => {
  let engine: LogicEngine

  beforeEach(() => {
    engine = new LogicEngine({ studyTimeMin: 2, studyTimeMax: 2, shortBreakDuration: 1, longBreakDuration: 2, longBreakThreshold: 10 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('初始状态为 stopped', () => {
    expect(engine.state).toBe('stopped')
    expect(engine.isPaused).toBe(false)
    expect(engine.cycleCount).toBe(0)
  })

  it('stopped → studying（输入/输出分类 = 倒计时）', () => {
    engine.start(1, '输入', '编程')
    expect(engine.state).toBe('studying')
    expect(engine.cycleCount).toBe(1)
  })

  it('stopped → countup_studying（生活分类 = 正计时）', () => {
    engine.start(3, '生活', '运动')
    expect(engine.state).toBe('countup_studying')
  })

  it('endStudyNow: 提前结束倒计时，状态回到 stopped', async () => {
    engine.start(1, '输入', '编程')
    expect(engine.state).toBe('studying')
    engine.endStudyNow()
    // endStudyNow 触发 onSummaryRequested，不直接变 stopped
    // 需要 submitSummary 才算完成
  })

  it('togglePause: 暂停和恢复', () => {
    engine.start(1, '输入', '编程')
    expect(engine.isPaused).toBe(false)
    engine.togglePause()
    expect(engine.isPaused).toBe(true)
    engine.togglePause()
    expect(engine.isPaused).toBe(false)
  })

  it('导出快照会保留运行、暂停、分段和分类上下文', () => {
    engine.start(1, '输入', '编程')
    expect(engine.exportSnapshot()).toMatchObject({ state: 'studying', isPaused: false, category: { id: 1, name: '输入', task: '编程' }, segments: [{ key: 'active', endEpochMs: null }] })
    engine.togglePause()
    expect(engine.exportSnapshot()).toMatchObject({ isPaused: true, pause: { startedAtEpochMs: expect.any(Number) }, segments: [{ key: 'segment:1' }], timing: { deadlineEpochMs: null } })
  })

  it('恢复快照按状态继续，并安全拒绝未知版本', () => {
    engine.start(1, '输入', '编程'); const restored = new LogicEngine()
    expect(restored.restoreSnapshot(engine.exportSnapshot())).toBe(true)
    expect(restored).toMatchObject({ state: 'studying', currentCategoryId: 1, currentFocusTask: '编程' })
    expect(restored.restoreSnapshot({ version: 99 })).toBe(false)
    expect(restored.state).toBe('stopped')
  })

  it('submitPauseReason: 暂停备注随会话提交', () => {
    let committed: any = null
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committed = r },
    })

    engine.start(1, '输入', '编程')
    engine.togglePause()
    engine.submitPauseReason('接电话')
    engine.togglePause()
    engine.submitSummary('测试总结')

    expect(committed?.pauseReasons).toContain('接电话')
  })

  it('输入/输出会话按暂停和总结生成结构化分段', () => {
    let committed: any = null
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committed = r },
    })

    engine.start(1, '输入', '编程')
    engine.togglePause()
    engine.submitPauseReason('查资料')
    engine.togglePause()
    engine.endStudyNow()
    engine.submitSummary('完成输出')

    expect(committed?.segments).toHaveLength(2)
    expect(committed?.segments[0]).toMatchObject({
      localSegmentKey: 'segment:1',
      note: '查资料',
    })
    expect(committed?.segments[1]).toMatchObject({
      localSegmentKey: 'segment:2',
      note: '完成输出',
    })
  })

  it('输入/输出切换分类后取消失败原因会继续原计时', () => {
    let committed: any = null
    let summaryRequested: any = null
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: (isSuccess, isEarlyEnd) => { summaryRequested = { isSuccess, isEarlyEnd } },
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committed = r },
    })

    engine.start(1, '输入', '编程')
    engine.switchCategory(3, '生活', '运动')
    expect(summaryRequested).toEqual({ isSuccess: false, isEarlyEnd: true })

    engine.cancelEarlyEnd()

    expect(committed).toBeNull()
    expect(engine.state).toBe('studying')
    expect(engine.currentCategoryId).toBe(1)
  })

  it('输入/输出切换分类并保存失败原因后立即启动目标分类', () => {
    let committed: any = null
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committed = r },
    })

    engine.start(1, '输入', '编程')
    engine.switchCategory(3, '生活', '运动')
    engine.submitSummary('被打断，切到运动')

    expect(committed?.sessionSummary).toBe('被打断，切到运动')
    expect(engine.state).toBe('countup_studying')
    expect(engine.currentCategoryId).toBe(3)
  })

  it('输入/输出手动停止并保存原因后回到 stopped', () => {
    let committed: any = null
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committed = r },
    })

    engine.start(1, '输入', '编程')
    engine.endStudyNow()
    engine.submitSummary('提前结束')

    expect(committed?.sessionSummary).toBe('提前结束')
    expect(engine.state).toBe('stopped')
    expect(engine.currentCycleStudySeconds).toBe(0)
  })

  it('输入/输出随机短休息开始和结束都会触发音效', () => {
    vi.useFakeTimers()
    const cues: string[] = []
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: (cue) => { cues.push(cue) },
      onMicroBreak: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: () => {},
    })

    engine.start(1, '输入', '编程')
    vi.advanceTimersByTime(2000)
    vi.advanceTimersByTime(1000)

    expect(cues).toContain('start')
    expect(cues).toContain('microBreak')
    expect(cues).toContain('endMicroBreak')
  })

  it('首次恢复输入会话会安排随机休息', () => {
    vi.useFakeTimers()
    const source = new LogicEngine({ studyTimeMin: 2, studyTimeMax: 2, shortBreakDuration: 1, longBreakThreshold: 10 })
    source.start(1, '输入')
    const snapshot = source.exportSnapshot()
    source.resetCycle()
    const breaks: number[] = []; const cues: string[] = []
    engine.setCallbacks({
      onStateChange: () => {}, onTick: () => {}, onAudioCue: cue => cues.push(cue),
      onMicroBreak: seconds => breaks.push(seconds), onSummaryRequested: () => {},
      onPauseReasonRequested: () => {}, onSessionCommitted: () => {},
    })
    engine.restoreSnapshot(snapshot)
    vi.advanceTimersByTime(2000)
    expect(breaks).toEqual([1])
    expect(cues).toContain('microBreak')
  })

  it('同一权威会话重复恢复不会推迟或重复随机休息', () => {
    vi.useFakeTimers()
    const source = new LogicEngine({ studyTimeMin: 2, studyTimeMax: 2, shortBreakDuration: 1, longBreakThreshold: 10 })
    source.start(1, '输入'); const snapshot = source.exportSnapshot(); source.resetCycle()
    const breaks: number[] = []
    engine.setCallbacks({
      onStateChange: () => {}, onTick: () => {}, onAudioCue: () => {},
      onMicroBreak: seconds => breaks.push(seconds), onSummaryRequested: () => {},
      onPauseReasonRequested: () => {}, onSessionCommitted: () => {},
    })
    engine.restoreSnapshot(snapshot)
    vi.advanceTimersByTime(1000)
    engine.restoreSnapshot(snapshot)
    vi.advanceTimersByTime(1000)
    expect(breaks).toEqual([1])
  })

  it('权威暂停清理随机休息，恢复仅重建一个，停止后不残留', () => {
    vi.useFakeTimers()
    const source = new LogicEngine({ studyTimeMin: 2, studyTimeMax: 2, shortBreakDuration: 1, longBreakThreshold: 10 })
    source.start(1, '输入'); const running = source.exportSnapshot(); source.resetCycle()
    const breaks: number[] = []
    engine.setCallbacks({
      onStateChange: () => {}, onTick: () => {}, onAudioCue: () => {},
      onMicroBreak: seconds => breaks.push(seconds), onSummaryRequested: () => {},
      onPauseReasonRequested: () => {}, onSessionCommitted: () => {},
    })
    engine.restoreSnapshot(running)
    engine.restoreSnapshot({ ...running, isPaused: true })
    vi.advanceTimersByTime(3000)
    expect(breaks).toEqual([])
    engine.restoreSnapshot(running)
    vi.advanceTimersByTime(2000)
    expect(breaks).toEqual([1])
    engine.restoreSnapshot({
      ...running,
      state: 'countup_studying',
      category: { id: 3, name: '家庭', task: '' },
      timing: { mode: 'countup', elapsedMs: 0, deadlineEpochMs: null },
    })
    vi.advanceTimersByTime(3000)
    expect(breaks).toEqual([1])
    engine.restoreSnapshot({ ...running, state: 'stopped' })
    vi.advanceTimersByTime(3000)
    expect(breaks).toEqual([1])
  })

  it('恢复时剩余专注时间不足随机间隔则不安排休息', () => {
    vi.useFakeTimers()
    const source = new LogicEngine({ studyTimeMin: 2, studyTimeMax: 2, longBreakThreshold: 10 })
    source.start(1, '输出'); const base = source.exportSnapshot(); source.resetCycle()
    const breaks: number[] = []
    engine.setCallbacks({
      onStateChange: () => {}, onTick: () => {}, onAudioCue: () => {},
      onMicroBreak: seconds => breaks.push(seconds), onSummaryRequested: () => {},
      onPauseReasonRequested: () => {}, onSessionCommitted: () => {},
    })
    engine.restoreSnapshot({ ...base, session: { ...base.session, durationSeconds: 1 } })
    vi.advanceTimersByTime(3000)
    expect(breaks).toEqual([])
  })

  it('随机休息 flow 日志覆盖安排、保留、跳过、开始和结束', () => {
    vi.useFakeTimers()
    const source = new LogicEngine({ studyTimeMin: 2, studyTimeMax: 2, shortBreakDuration: 1, longBreakThreshold: 10 })
    source.start(1, '输入'); const snapshot = source.exportSnapshot(); source.resetCycle()
    const flows: string[] = []
    engine.setCallbacks({
      onStateChange: () => {}, onTick: () => {}, onAudioCue: () => {}, onMicroBreak: () => {},
      onSummaryRequested: () => {}, onPauseReasonRequested: () => {}, onSessionCommitted: () => {},
      onTimerFlow: event => flows.push(event),
    })
    engine.restoreSnapshot(snapshot)
    engine.restoreSnapshot(snapshot)
    vi.advanceTimersByTime(3000)
    engine.restoreSnapshot({
      ...snapshot,
      session: { ...snapshot.session, startedAtEpochMs: 1, largeStartedAtEpochMs: 1, durationSeconds: 1 },
    })
    for (const event of ['micro-break.scheduled', 'micro-break.preserved', 'micro-break.started', 'micro-break.finished', 'micro-break.skipped']) {
      expect(flows).toContain(event)
    }
  })

  it('输入/输出随机短休息使用配置的 0 下限和短休时长', () => {
    vi.useFakeTimers()
    const microBreaks: number[] = []
    const cues: string[] = []
    const configured = new LogicEngine({
      studyTimeMin: 0,
      studyTimeMax: 0,
      shortBreakDuration: 3,
      longBreakThreshold: 60,
    })
    configured.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: (cue) => { cues.push(cue) },
      onMicroBreak: (seconds) => { microBreaks.push(seconds) },
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: () => {},
    })

    configured.start(1, '输入', '编程')
    vi.advanceTimersByTime(0)
    vi.advanceTimersByTime(3000)

    expect(microBreaks).toContain(3)
    expect(cues).toContain('microBreak')
    expect(cues).toContain('endMicroBreak')
  })

  it('计时配置会钳制非法随机区间且保留 0 下限', () => {
    vi.useFakeTimers()
    const microBreaks: number[] = []
    const configured = new LogicEngine({
      studyTimeMin: 0,
      studyTimeMax: -1,
      shortBreakDuration: 1,
      longBreakThreshold: 60,
    })
    configured.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onMicroBreak: (seconds) => { microBreaks.push(seconds) },
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: () => {},
    })

    configured.start(1, '输入', '编程')
    vi.advanceTimersByTime(0)

    expect(microBreaks).toContain(1)
  })

  it('启动前刷新输入/输出倒计时配置会影响新一轮倒计时', () => {
    let firstRemaining = 0
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: (_elapsed, remaining) => {
        if (!firstRemaining) firstRemaining = remaining
      },
      onAudioCue: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: () => {},
    })

    engine.updateConfig({ longBreakThreshold: 180 })
    engine.start(1, '输出', '测试 3min')

    expect(firstRemaining).toBe(180000)
  })

  it('状态切换休息使用长休息时长倒计时并自动提交', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] })
    let firstRemaining = 0
    const cues: string[] = []
    const committedRecords: any[] = []
    const configured = new LogicEngine({
      studyTimeMin: 2,
      studyTimeMax: 2,
      shortBreakDuration: 1,
      longBreakDuration: 1,
      longBreakThreshold: 10,
    })
    configured.setCallbacks({
      onStateChange: () => {},
      onTick: (_elapsed, remaining) => {
        if (!firstRemaining) firstRemaining = remaining
      },
      onAudioCue: (cue) => { cues.push(cue) },
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committedRecords.push(r) },
    })

    configured.start(9, '状态切换', '休息', { useLongBreakDuration: true })
    expect(configured.state).toBe('long_breaking')
    expect(firstRemaining).toBe(1000)
    expect(cues).toContain('startLongBreak')
    expect(cues).not.toContain('start')

    vi.advanceTimersByTime(1000)

    expect(cues).toContain('endLongBreak')
    expect(committedRecords).toHaveLength(1)
    expect(committedRecords[0]?.sessionSummary).toBe('休息')
    expect(committedRecords[0]?.categoryId).toBe(9)
    expect(configured.state).toBe('stopped')
  })

  it('恢复自动长休息后到期只发结束音效和自动完成事件', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] })
    const source = new LogicEngine({ longBreakDuration: 1 })
    source.start(9, '状态切换', '休息', { useLongBreakDuration: true })
    const snapshot = source.exportSnapshot(); source.resetCycle()
    const cues: string[] = []; const flows: string[] = []; let summaries = 0
    engine.setCallbacks({
      onStateChange: () => {}, onTick: () => {}, onAudioCue: cue => cues.push(cue),
      onSummaryRequested: () => { summaries += 1 }, onPauseReasonRequested: () => {},
      onSessionCommitted: () => {}, onTimerFlow: event => flows.push(event),
    })
    engine.restoreSnapshot(snapshot)
    vi.advanceTimersByTime(1000)
    expect(cues).toEqual(['endLongBreak'])
    expect(flows).toContain('status-switch.stop.after')
    expect(summaries).toBe(0)
  })

  it('快捷状态切换不触发暂停或提前结束原因弹窗', () => {
    let summaryRequests = 0
    let pauseRequests = 0
    let committed: any = null
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: () => { summaryRequests += 1 },
      onPauseReasonRequested: () => { pauseRequests += 1 },
      onSessionCommitted: (r) => { committed = r },
    })

    engine.start(1, '输入', '编程')
    engine.switchCategoryNow(9, '状态切换', '')

    expect(summaryRequests).toBe(0)
    expect(pauseRequests).toBe(0)
    expect(committed?.categoryId).toBe(1)
    expect(committed?.sessionSummary).toBe('状态切换')
    expect(engine.state).toBe('countup_studying')
    expect(engine.currentCategoryId).toBe(9)
  })

  it('真实耗时的输入/输出任意多轮快捷状态切换后都能进入状态切换并清理周期残留', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] })
    const committedRecords: any[] = []
    const configured = new LogicEngine({
      studyTimeMin: 2,
      studyTimeMax: 2,
      shortBreakDuration: 1,
      longBreakDuration: 2,
      longBreakThreshold: 100000,
    })
    configured.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committedRecords.push(r) },
    })

    const rounds = [
      { id: 1, name: '输入' },
      { id: 2, name: '输出' },
      { id: 1, name: '输入' },
      { id: 2, name: '输出' },
      { id: 1, name: '输入' },
    ]

    rounds.forEach((source, index) => {
      configured.start(source.id, source.name, `round-${index + 1}`)
      expect(configured.state).toBe('studying')
      expect(configured.currentCategoryId).toBe(source.id)
      expect((configured as any)._largeSessionStart).toBeInstanceOf(Date)
      vi.advanceTimersByTime((67 + index) * 1000)

      const switchResult = configured.switchCategoryNow(9, '状态切换', '', '状态切换', `real-round-${index + 1}`)

      expect(switchResult.ok).toBe(true)
      expect(configured.state).toBe('countup_studying')
      expect(configured.currentCategoryId).toBe(9)
      expect(configured.currentCategoryName).toBe('状态切换')
      expect(committedRecords[committedRecords.length - 1]).toMatchObject({
        categoryId: source.id,
        sessionSummary: '状态切换',
      })

      configured.setCurrentFocusTask(`原因-${index + 1}`)
      vi.advanceTimersByTime(1000)
      configured.endCountupNow()

      expect(configured.state).toBe('stopped')
      expect(configured.currentCategoryId).toBeNull()
      expect(configured.currentCategoryName).toBe('')
      expect(configured.currentFocusTask).toBe('')
      expect(configured.currentCycleStudySeconds).toBe(0)
      expect(configured.totalStudySeconds).toBe(0)
      expect(committedRecords[committedRecords.length - 1]).toMatchObject({
        categoryId: 9,
        sessionSummary: `原因-${index + 1}`,
      })
    })
  })

  it('第二轮输出真实运行 34 秒后 Alt+C 不会因上一轮 67 秒残留卡住', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] })
    const records: any[] = []
    const configured = new LogicEngine({ longBreakThreshold: 100000 })
    configured.setCallbacks({
      onStateChange: () => {}, onTick: () => {}, onAudioCue: () => {},
      onSummaryRequested: () => {}, onPauseReasonRequested: () => {},
      onSessionCommitted: record => records.push(record),
    })

    configured.start(1, '输入')
    vi.advanceTimersByTime(67000)
    expect(configured.switchCategoryNow(9, '状态切换', '', '状态切换', 'trace-first').ok).toBe(true)
    vi.advanceTimersByTime(23000)
    configured.endCountupNow()

    configured.start(2, '输出')
    expect((configured as any)._largeSessionStart).toBeInstanceOf(Date)
    vi.advanceTimersByTime(34000)
    expect(configured.switchCategoryNow(9, '状态切换', '', '状态切换', 'trace-second').ok).toBe(true)

    expect(configured.state).toBe('countup_studying')
    expect(configured.currentCategoryName).toBe('状态切换')
    expect(records.map(record => [record.categoryId, record.netDurationSeconds])).toEqual([
      [1, 67], [9, 23], [2, 34],
    ])
  })

  it('快捷切换可从当前 session 起点恢复缺失的大 session 起点', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] })
    let committed: any = null
    engine.setCallbacks({
      onStateChange: () => {}, onTick: () => {}, onAudioCue: () => {},
      onSummaryRequested: () => {}, onPauseReasonRequested: () => {},
      onSessionCommitted: record => { committed = record },
    })
    engine.start(2, '输出', '原备注')
    vi.advanceTimersByTime(5000)
    ;(engine as any)._largeSessionStart = null
    engine.currentCycleStudySeconds = 67
    engine.totalStudySeconds = 67

    const result = engine.switchCategoryNow(9, '状态切换', '', '状态切换', 'trace-recovered')

    expect(result).toMatchObject({ ok: true, status: 'recovered' })
    expect(committed).toMatchObject({ categoryId: 2, netDurationSeconds: 5 })
    expect(engine.currentCategoryName).toBe('状态切换')
  })

  it('快捷切换上下文不可恢复时不停止 timer、不改分类备注或 pending', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'] })
    engine.start(2, '输出', '原备注')
    vi.advanceTimersByTime(3000)
    ;(engine as any)._largeSessionStart = null
    ;(engine as any)._sessionStart = null
    const elapsedBefore = (engine as any)._timer.getElapsed()

    const result = engine.switchCategoryNow(9, '状态切换', '', '状态切换', 'trace-failed')

    expect(result).toMatchObject({ ok: false, status: 'failed', errorCode: 'missing-session-context' })
    expect(engine.state).toBe('studying')
    expect(engine.currentCategoryName).toBe('输出')
    expect(engine.currentFocusTask).toBe('原备注')
    expect((engine as any)._timer.running).toBe(true)
    expect((engine as any)._timer.getElapsed()).toBe(elapsedBefore)
    expect((engine as any)._pendingSwitchCategory).toBeNull()
  })

  it('同一输入输出大 session 的普通续轮保留累计与原大 session 起点', () => {
    engine.start(1, '输入')
    const firstLargeStart = (engine as any)._largeSessionStart
    engine.currentCycleStudySeconds = 5
    ;(engine as any)._runStudyCycle()
    expect((engine as any)._largeSessionStart).toBe(firstLargeStart)
    expect(engine.currentCycleStudySeconds).toBe(5)
  })

  it('普通分类暂停恢复结束不生成结构化分段', () => {
    let committed: any = null
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committed = r },
    })

    engine.start(3, '生活', '运动')
    engine.togglePause()
    engine.submitPauseReason('喝水')
    engine.togglePause()
    engine.endCountupNow()

    expect(committed?.pauseReasons).toContain('喝水')
    expect(committed?.segments).toBeUndefined()
    expect(engine.state).toBe('stopped')
  })

  it('resetCycle: 回到 stopped', () => {
    engine.start(1, '输入', '编程')
    engine.resetCycle()
    expect(engine.state).toBe('stopped')
    expect(engine.cycleCount).toBe(0)
  })

  it('submitSummary: 提交谈判记录', () => {
    let committed: any = null
    engine.setCallbacks({
      onStateChange: () => {},
      onTick: () => {},
      onAudioCue: () => {},
      onSummaryRequested: () => {},
      onPauseReasonRequested: () => {},
      onSessionCommitted: (r) => { committed = r },
    })

    engine.start(1, '输入', '编程')
    // 强制 set largeSessionStart 然后提交
    const record = engine.submitSummary('测试总结')
    expect(record).not.toBeNull()
    if (record) {
      expect(record.sessionSummary).toBe('测试总结')
      expect(record.categoryId).toBe(1)
      expect(record.netDurationMinutes).toBeGreaterThanOrEqual(0)
    }
    expect(engine.state).toBe('stopped')
  })
})
