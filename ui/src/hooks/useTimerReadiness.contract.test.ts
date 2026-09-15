const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const hook = fs.readFileSync(new URL('./useTimer.ts', import.meta.url), 'utf8') as string

assert(hook.includes('subscribeCurrentTimerClient'), 'late API client must notify the timer hook')
assert(hook.includes('const ensureCoordinator = async'), 'timer hook must create the coordinator after client readiness')
assert(hook.includes('db.ensureDeviceId?.()'), 'coordinator must have a stable local device identity')
assert(hook.includes('coordinatorInitPromiseRef'), 'concurrent recovery signals must share initialization')
assert(hook.includes('timerReadinessFromOutcome(initial)'), 'accepted stopped state must become ready after initial GET')
assert(hook.includes('await ensureCoordinatorRef.current()'), 'commands must wait for coordinator readiness')
assert(hook.includes('isTimerCommandReady(timerReadinessRef.current)'), 'commands must be gated before server submission')
for (const eventName of ["'online'", "'focus'", "'visibilitychange'", "'mtl:timer-state-changed'", "'mtl:current-timer-state'"]) {
  assert(hook.includes(eventName), `recovery event ${eventName} must refresh current timer readiness`)
}
assert(hook.includes('refreshCurrentTimerRef.current().catch(() => null)'), 'recovery must use the same single-flight current timer refresh')
assert(!hook.includes("setTimerSyncStatus('waiting')"), 'generic waiting must not hide an initialization error')
console.log('useTimer readiness contract passed')
