import { LogicEngine } from '@core/LogicEngine'
import type { DeviceRuntimeStateService } from '../platform'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const values = new Map<string, string>()
const runtime: DeviceRuntimeStateService = {
  available: true, get: async key => values.get(key) ?? null,
  set: async (key, value) => { values.set(key, value) }, remove: async key => { values.delete(key) },
}
const original = new LogicEngine(); original.start(1, '输入', '同一会话')
await runtime.set('timer.logic.snapshot.v1', JSON.stringify(original.exportSnapshot()))
const restored = new LogicEngine()
assert(restored.restoreSnapshot(JSON.parse((await runtime.get('timer.logic.snapshot.v1'))!)), 'Android remount should restore the snapshot')
assert(restored.currentCategoryId === 1 && restored.currentFocusTask === '同一会话', 'remount must not create a new session')
assert(restored.exportSnapshot().session.startedAtEpochMs === original.exportSnapshot().session.startedAtEpochMs, 'restored session identity should stay stable')
assert(values.size === 1, 'snapshot should only use device runtime state')
const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const hook = fs.readFileSync(new URL('./useTimer.ts', import.meta.url), 'utf8') as string
assert(hook.includes('const importRuntimeSnapshot') && hook.includes('await importRuntimeSnapshot()') && hook.includes('const importWidgetSnapshot = importRuntimeSnapshot'), 'cold start and widget recovery must share one snapshot import path')
assert(hook.includes('persistTimerSnapshot(engine'), 'Hook should persist after actions')
assert(!hook.includes("setConfig(TIMER_RUNTIME_KEY"), 'Hook must not write the snapshot to Database config or Outbox')
const persistStart = hook.indexOf('export const persistTimerSnapshot')
const persist = hook.slice(persistStart, persistStart + 650)
assert(persist.indexOf('await service.set') < persist.indexOf('refresh()'), 'launcher refresh must happen only after the authoritative snapshot write resolves')
assert(persist.includes('refresh = refreshTimerWidget') && !persist.includes('finally'), 'failed snapshot writes must not refresh an unpersisted state')
const recoveryStart = hook.indexOf('const refresh = () => { void refreshCurrentTimerRef.current() }')
const recovery = hook.slice(recoveryStart, recoveryStart + 1200)
assert(recovery.includes('refreshCurrentTimerRef.current()'), 'widget refresh must GET the authoritative current state')
assert(!recovery.includes('restoreTimerSnapshot(engine)') && !recovery.includes('handleEndSession('), 'widget refresh must not replay native or stale local transitions')
assert(recovery.includes("removeEventListener('mtl:timer-widget-snapshot-changed'"), 'snapshot listener must be removable')
original.resetCycle(); restored.resetCycle()
console.log('useTimer runtime state tests passed')
