import { applyStatusSwitchNote, canRequestStatusSwitch, formatStatusSwitchSourceSummary, requiresStatusSwitchNote, runDetachedRemote, runStatusSwitchRequest, statusSwitchSourcePolicy, toggleStatusSwitchPreset } from './statusSwitchFlow'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message)
}

assert(canRequestStatusSwitch('idle'), 'idle should accept Alt+C')
assert(!canRequestStatusSwitch('queued'), 'queued should gate duplicate Alt+C')
assert(!canRequestStatusSwitch('switching'), 'switching should gate duplicate Alt+C')
assert(!canRequestStatusSwitch('awaiting-note'), 'open sheet should gate duplicate Alt+C')
assert(!canRequestStatusSwitch('note-submitting'), 'note submit should gate duplicate Alt+C')
assert(statusSwitchSourcePolicy('输入').requiresNote, 'input should require a note')
assert(statusSwitchSourcePolicy('输出').requiresNote, 'output should require a note')
assert(statusSwitchSourcePolicy('娱乐').requiresNote, 'other categories should require a note')
assert(!requiresStatusSwitchNote('capacitor-android'), 'Android should bypass the status-switch note')
assert(requiresStatusSwitchNote('electron'), 'Electron should keep the status-switch note')
assert(requiresStatusSwitchNote('web'), 'Web should keep the status-switch note')
for (const runtime of ['electron', 'web'] as const) {
  assert(requiresStatusSwitchNote(runtime), `${runtime} should enter the existing awaiting-note lifecycle`)
}
assert(formatStatusSwitchSourceSummary('  喝水  ') === '中断-喝水', 'preset reason uses interrupted summary')
assert(formatStatusSwitchSourceSummary('手工原因') === '中断-手工原因', 'custom reason uses interrupted summary')
assert(toggleStatusSwitchPreset('', '活动') === '活动', 'empty selection should select clicked preset')
assert(toggleStatusSwitchPreset('活动', '活动') === '', 'clicking selected preset should clear it')
assert(toggleStatusSwitchPreset('活动', '喝水') === '喝水', 'clicking another preset should replace selection')

const category = { id: 9, name: '状态切换' } as any
let remoteSwitches = 0
const failedEngine = {
  state: 'studying', currentCategoryId: 2, currentCategoryName: '输出',
  switchCategoryNow: () => ({ ok: false, status: 'failed', errorCode: 'missing-session-context' }),
} as any
const failed = runStatusSwitchRequest({ engine: failedEngine, category, traceId: 'failed-trace' })
assert(!failed.ok, 'failed engine switch should stay failed')
assert(remoteSwitches === 0, 'failed engine switch must have zero remote side effects')

const successEngine = {
  state: 'studying', currentCategoryId: 2, currentCategoryName: '输出',
  switchCategoryNow: function () {
    this.state = 'countup_studying'
    this.currentCategoryId = 9
    this.currentCategoryName = '状态切换'
    return { ok: true, status: 'switched' }
  },
} as any
const startedAt = Date.now()
const succeeded = runStatusSwitchRequest({ engine: successEngine, category, traceId: 'success-trace' })
assert(succeeded.ok, 'successful local switch should succeed')
assert(Date.now() - startedAt < 200, 'local switch should not wait for remote work')
assert(remoteSwitches === 0, 'pure local switch should have zero remote side effects')

for (const sourceName of ['输入', '输出', '娱乐']) {
  const branchEngine = {
    state: sourceName === '娱乐' ? 'countup_studying' : 'studying', currentCategoryId: 3, currentCategoryName: sourceName,
    switchCategoryNow: function () { this.state = 'countup_studying'; this.currentCategoryId = 9; this.currentCategoryName = '状态切换'; return { ok: true } },
  } as any
  const branchResult = runStatusSwitchRequest({ engine: branchEngine, category, traceId: `branch-${sourceName}` })
  assert(branchResult.ok && branchEngine.currentCategoryName === '状态切换', `${sourceName} should switch locally`)
  assert(statusSwitchSourcePolicy(sourceName).requiresNote, `${sourceName} should open the note sheet`)
}

let releaseRemote!: () => void
let detachedCompleted = false
const delayedRemote = new Promise<void>(resolve => { releaseRemote = resolve })
runDetachedRemote(() => delayedRemote, () => { detachedCompleted = true }, () => { throw new Error('delayed remote should succeed') })
assert(!detachedCompleted, 'slow remote should remain detached from local completion')
releaseRemote()
await delayedRemote
await new Promise(resolve => setTimeout(resolve, 0))
assert(detachedCompleted, 'detached remote should eventually complete')

let detachedFailed = false
runDetachedRemote(async () => { throw new Error('remote down') }, () => undefined, () => { detachedFailed = true })
await new Promise(resolve => setTimeout(resolve, 0))
assert(detachedFailed, 'detached rejection should be caught')

const failedNoteEffects: string[] = []
const failedNoteApplied = applyStatusSwitchNote({
  engine: { state: 'studying', currentCategoryId: 2, setCurrentFocusTask: () => failedNoteEffects.push('engine') } as any,
  categoryId: 9, note: 'test', sourceSessionId: 7,
  updateSource: () => failedNoteEffects.push('source'),
})
assert(!failedNoteApplied, 'note must not apply while engine remains on output')
assert(failedNoteEffects.length === 0, 'failed note validation must have zero local and remote side effects')

const successfulNoteEffects: string[] = []
const successfulNoteApplied = applyStatusSwitchNote({
  engine: { state: 'countup_studying', currentCategoryId: 9, setCurrentFocusTask: () => successfulNoteEffects.push('engine') } as any,
  categoryId: 9, note: 'test', sourceSessionId: 7,
  updateSource: () => successfulNoteEffects.push('source'),
})
assert(successfulNoteApplied, 'valid status-switch note should apply')
assert(JSON.stringify(successfulNoteEffects) === JSON.stringify(['source', 'engine']), 'note local effects should not wait for remote')

const timerHook = readFileSync(fileURLToPath(new URL('./useTimer.ts', import.meta.url)), 'utf8')
const switchStart = timerHook.indexOf('const switchCategory')
const switchEnd = timerHook.indexOf('return useMemo', switchStart)
const switchBlock = timerHook.slice(switchStart, switchEnd)
const cancelStart = timerHook.indexOf('const cancelStatusSwitchNote')
const cancelEnd = timerHook.indexOf('const setCurrentNote', cancelStart)
const cancelBlock = timerHook.slice(cancelStart, cancelEnd)
assert(timerHook.includes("db.updateSession(id, { session_summary: sourceSummary } as any)"), 'confirmed note should persist the source session summary')
assert(switchBlock.includes('cat.name === STATUS_SWITCH_CATEGORY_NAME') && switchBlock.includes('requestStatusSwitch()'), 'status switch grid target should use the dedicated note-enabled request')
assert(timerHook.includes('requiresStatusSwitchNote(detectPlatformRuntime())'), 'Android direct switch should use the runtime note policy')
assert(timerHook.includes("statusSwitchLifecycleRef.current = requiresNote ? 'awaiting-note' : 'idle'"), 'Android direct switch should return to idle instead of awaiting a hidden note')
assert(timerHook.includes('setShowStatusSwitchNote(requiresNote)'), 'Android direct switch should not open the note sheet')
assert(cancelBlock.includes('setShowStatusSwitchNote(false)') && cancelBlock.includes("statusSwitchLifecycleRef.current = 'idle'"), 'later action should dismiss the note sheet')
assert(!cancelBlock.includes('commandCurrentTimer') && !cancelBlock.includes('switchCategoryNow'), 'later action should not roll back a completed status switch')

console.log('statusSwitchFlow tests passed')
