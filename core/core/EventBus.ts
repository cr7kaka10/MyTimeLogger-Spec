/** 发布/订阅事件总线 — 从 app/core/signal_bus.py 翻译 */

type Listener = (...args: any[]) => void

export class EventBus {
  private _listeners = new Map<string, Set<Listener>>()

  on(event: string, listener: Listener): void {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, new Set())
    }
    this._listeners.get(event)!.add(listener)
  }

  off(event: string, listener: Listener): void {
    this._listeners.get(event)?.delete(listener)
  }

  emit(event: string, ...args: any[]): void {
    this._listeners.get(event)?.forEach(fn => {
      try { fn(...args) } catch (e) { console.error(`[EventBus] ${event}:`, e) }
    })
  }

  once(event: string, listener: Listener): void {
    const wrapper: Listener = (...args) => {
      this.off(event, wrapper)
      listener(...args)
    }
    this.on(event, wrapper)
  }

  clear(): void {
    this._listeners.clear()
  }
}
