import { __resetTimerFlowForTests, emitTimerFlow, sanitizeTimerFlowDetails } from './timerFlow'

const assert = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message)
}

const safe = sanitizeTimerFlowDetails({
  note: 'private note', token: 'secret-token', password: 'secret-password',
  Authorization: 'Bearer secret', Cookie: 'session=secret', headers: { auth: 'secret' },
  hasNote: true, noteLength: 12, errorCode: 'safe-code', currentCategoryId: 2,
})
const safeText = JSON.stringify(safe)
for (const forbidden of ['private note', 'secret-token', 'secret-password', 'Bearer secret', 'session=secret']) {
  assert(!safeText.includes(forbidden), `sanitized event leaked ${forbidden}`)
}
assert(safe.hasNote === true && safe.noteLength === 12, 'note metadata should remain')
assert(safe.errorCode === 'safe-code', 'stable error code should remain')

const originalInfo = console.info
const originalWarn = console.warn
const originalError = console.error
console.info = () => undefined
console.warn = () => undefined
console.error = () => undefined

__resetTimerFlowForTests()
const first = emitTimerFlow('ElectronMain', 'shortcut.sent', { traceId: 'success', traceStep: 1 })
const second = emitTimerFlow('App', 'shortcut.received', { traceId: 'success' })
const third = emitTimerFlow('useTimer', 'flow.completed', { traceId: 'success', result: 'completed' })
assert(first.step === 2 && second.step === 3 && third.step === 4, 'trace steps should be monotonic across layers')

for (const [traceId, event, result] of [
  ['recovered', 'flow.completed', 'recovered'],
  ['failed', 'flow.failed', 'failed'],
  ['deduped', 'flow.completed', 'deduped'],
  ['gated', 'flow.completed', 'gated'],
] as const) {
  emitTimerFlow('test', 'shortcut.received', { traceId })
  const terminal = emitTimerFlow('test', event, { traceId, result, errorCode: result === 'failed' ? 'test-failure' : undefined, failedStep: result === 'failed' ? 'preflight' : undefined })
  assert(terminal.step === 2, `${traceId} should have one continuous terminal step`)
  if (result === 'failed') assert(terminal.errorCode === 'test-failure' && terminal.failedStep === 'preflight', 'failed trace should identify the breakpoint')
}

__resetTimerFlowForTests()
const source = emitTimerFlow('useTimer', 'source.classified', { traceId: 'detached', sourceCategoryName: '输入', targetCategoryName: '状态切换', result: 'completed' })
const sheet = emitTimerFlow('useTimer', 'sheet.opened', { traceId: 'detached', result: 'completed' })
const localTerminal = emitTimerFlow('useTimer', 'flow.local.completed', { traceId: 'detached', result: 'completed' })
const remoteTerminal = emitTimerFlow('useTimer', 'flow.remote.failed', { traceId: 'detached', result: 'failed', errorCode: 'remote-category-switch-failed', failedStep: 'remote.category-switch' })
assert(source.step < sheet.step && sheet.step < localTerminal.step && localTerminal.step < remoteTerminal.step, 'detached local and remote steps should share one monotonic trace')
assert(sheet.durationMs! < 200, 'local sheet trace should meet the 200ms target without remote work')
assert(remoteTerminal.errorCode === 'remote-category-switch-failed' && remoteTerminal.failedStep === 'remote.category-switch', 'remote failure should identify its breakpoint')

const skipped = emitTimerFlow('useTimer', 'sheet.opened/skipped', { traceId: 'other-source', sourceCategoryName: '娱乐', result: 'skipped', reason: 'source-note-not-required' })
assert(skipped.result === 'skipped' && skipped.reason === 'source-note-not-required', 'other source should have an observable skipped sheet')

console.info = originalInfo
console.warn = originalWarn
console.error = originalError
console.log('timerFlow tests passed')
