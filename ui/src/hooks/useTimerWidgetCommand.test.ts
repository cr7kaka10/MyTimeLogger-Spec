const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const hook = fs.readFileSync(new URL('./useTimer.ts', import.meta.url), 'utf8') as string
const platform = fs.readFileSync(new URL('../platform/timerWidget.ts', import.meta.url), 'utf8') as string

assert(hook.includes('registerTimerWidgetCommandListener'), 'useTimer must register the native widget listener')
assert(hook.includes("enqueueTimerAction(`widget-${command.action}`"), 'widget and UI actions must share the serial queue')
assert(hook.includes("['输入', '输出'].includes(cat.name)"), 'input and output widget targets must be rejected')
assert(hook.includes('new Date(command.eventEpochMs)'), 'widget integration boundaries must use command event time')
assert(hook.includes("commandCurrentTimer(operation"), 'widget commands must enter the current-state coordinator')
assert(hook.includes('await ensureCoordinatorRef.current()') && hook.includes('isTimerCommandReady(timerReadinessRef.current)'), 'widget must not command before readiness')
assert(hook.includes("currentTimerCoordinatorRef.current?.snapshot()?.active"), 'widget start/switch must use refreshed authoritative state')
assert(hook.includes("userIntentId: command.commandId"), 'widget retry and aTimeLogger dedupe must share the command intent')
assert(!hook.includes('setTimerWidgetIntegrationConsumer'), 'old native command journals must never auto-takeover after restart')
assert(!hook.includes('recoverNativeWidgetSessions'), 'widget observation must never write a second local session')
assert(!platform.includes("createOutboxOperation('study_sessions'"), 'widget platform must not publish native sessions')
assert(!hook.includes('publishWidgetPresence'), 'widget recovery must not control remote presence')
assert(hook.includes("window.addEventListener('mtl:timer-widget-snapshot-changed', refresh)"), 'native authoritative change must trigger a server refresh')
assert(hook.includes('const refresh = () => { void refreshCurrentTimerRef.current() }'), 'app must re-read authority instead of applying a native payload')
console.log('useTimer widget command tests passed')
