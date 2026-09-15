export class SerialTaskQueue {
  private interactive: Array<{ task: () => Promise<unknown>; resolve: (value: any) => void; reject: (error: unknown) => void }> = []
  private maintenance: Array<{ task: () => Promise<unknown>; resolve: (value: any) => void; reject: (error: unknown) => void }> = []
  private running = false

  enqueue<T>(task: () => Promise<T>, priority: 'interactive' | 'maintenance' = 'interactive'): Promise<T> {
    const promise = new Promise<T>((resolve, reject) => this[priority].push({ task, resolve, reject }))
    void this.drain()
    return promise
  }

  enqueueInteractive<T>(task: () => Promise<T>): Promise<T> { return this.enqueue(task, 'interactive') }
  enqueueMaintenance<T>(task: () => Promise<T>): Promise<T> { return this.enqueue(task, 'maintenance') }

  private async drain(): Promise<void> {
    if (this.running) return
    this.running = true
    try {
      while (this.interactive.length || this.maintenance.length) {
        const item = this.interactive.shift() || this.maintenance.shift()!
        try { item.resolve(await item.task()) } catch (error) { item.reject(error) }
      }
    } finally {
      this.running = false
    }
  }
}
