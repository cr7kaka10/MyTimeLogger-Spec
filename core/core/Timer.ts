/** 高精度计时器 — 从 app/core/simple_timer.py 翻译 */

export type TimerMode = 'countdown' | 'countup'

export interface TimerCallbacks {
  onTick: (elapsedMs: number, remainingMs: number) => void
  onFinish: (elapsedMs: number) => void
}

export class Timer {
  private _intervalId: ReturnType<typeof setInterval> | null = null
  private _startTime = 0          // performance.now() 基准点
  private _accumulatedMs = 0      // 暂停前已累计的时间
  private _totalMs = 0            // 倒计时总时长（正计时为 0）
  private _mode: TimerMode = 'countdown'
  private _callbacks: TimerCallbacks | null = null
  private _running = false

  /** 启动计时器 */
  start(totalMs: number, mode: TimerMode, callbacks: TimerCallbacks): void {
    this.stop()
    this._mode = mode
    this._totalMs = mode === 'countdown' ? totalMs : 0
    this._accumulatedMs = 0
    this._startTime = performance.now()
    this._callbacks = callbacks
    this._running = true
    this._tick()
    this._intervalId = setInterval(() => this._tick(), 200)
  }

  /** 暂停 */
  pause(): { elapsedMs: number; remainingMs: number } {
    if (!this._running) return { elapsedMs: 0, remainingMs: this._totalMs }
    this._accumulatedMs += performance.now() - this._startTime
    this._stopInterval()
    this._running = false
    return this._state()
  }

  /** 恢复 */
  resume(): void {
    if (this._running) return
    this._startTime = performance.now()
    this._running = true
    this._tick()
    this._intervalId = setInterval(() => this._tick(), 200)
  }

  /** 停止 */
  stop(): { elapsedMs: number } {
    const elapsed = this._accumulatedMs + (this._running ? performance.now() - this._startTime : 0)
    this._stopInterval()
    this._running = false
    this._callbacks = null
    return { elapsedMs: Math.round(elapsed) }
  }

  /** 获取当前经过时间 */
  getElapsed(): number {
    return Math.round(
      this._accumulatedMs + (this._running ? performance.now() - this._startTime : 0),
    )
  }

  /** 是否正在运行 */
  get running(): boolean {
    return this._running
  }

  /** 当前模式 */
  get mode(): TimerMode {
    return this._mode
  }

  private _tick(): void {
    const elapsed = this.getElapsed()
    const remaining = this._mode === 'countdown'
      ? Math.max(0, this._totalMs - elapsed)
      : 0

    this._callbacks?.onTick(elapsed, remaining)

    // 倒计时归零 → 触发完成回调
    if (this._mode === 'countdown' && remaining <= 0) {
      this._stopInterval()
      this._running = false
      this._callbacks?.onFinish(elapsed)
    }
  }

  private _state(): { elapsedMs: number; remainingMs: number } {
    const elapsed = this.getElapsed()
    const remaining = this._mode === 'countdown'
      ? Math.max(0, this._totalMs - elapsed)
      : 0
    return { elapsedMs: elapsed, remainingMs: remaining }
  }

  private _stopInterval(): void {
    if (this._intervalId !== null) {
      clearInterval(this._intervalId)
      this._intervalId = null
    }
  }
}
