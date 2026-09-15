/** 将连续用户操作合并为一次同步；在途期间的新操作最多排一轮尾随。 */
export function createUserActionSyncScheduler(
  synchronize: () => Promise<unknown>,
  delayMs = 350,
  clock: Pick<typeof globalThis, 'setTimeout' | 'clearTimeout'> = globalThis,
) {
  let timer: ReturnType<typeof setTimeout> | null = null
  let inFlight: Promise<unknown> | null = null
  let trailing = false
  let closed = false
  const run = () => {
    timer = null
    if (closed) return
    if (inFlight) { trailing = true; return }
    const pending = Promise.resolve().then(synchronize)
    inFlight = pending
    void pending.catch(() => {}).finally(() => {
      inFlight = null
      if (trailing && !closed) { trailing = false; run() }
    })
  }
  return {
    request() {
      if (closed) return
      if (timer) clock.clearTimeout(timer)
      timer = clock.setTimeout(run, delayMs)
    },
    dispose() {
      closed = true
      if (timer) clock.clearTimeout(timer)
      timer = null
      trailing = false
    },
  }
}
