import type { LogicEngine } from '@core/LogicEngine'
import type { Category } from '../types'
import type { PlatformRuntime } from '../platform/runtime'

export type StatusSwitchLifecycle = 'idle' | 'queued' | 'switching' | 'awaiting-note' | 'note-submitting'

export const canRequestStatusSwitch = (lifecycle: StatusSwitchLifecycle): boolean => lifecycle === 'idle'

export const requiresStatusSwitchNote = (runtime: PlatformRuntime): boolean => runtime !== 'capacitor-android'

export const statusSwitchSourcePolicy = (categoryName: string | null | undefined) => {
  const kind = categoryName === '输入' || categoryName === '输出' ? 'input-output' as const : 'other' as const
  return { kind, requiresNote: true }
}

export const formatStatusSwitchSourceSummary = (note: string): string => `中断-${note.trim() || '状态切换'}`

export const toggleStatusSwitchPreset = (current: string, clicked: string): string => current === clicked ? '' : clicked

export const runDetachedRemote = (
  work: () => Promise<any>,
  onCompleted: () => void,
  onFailed: () => void,
): void => { void Promise.resolve().then(work).then(onCompleted).catch(onFailed) }

export const isStatusSwitchRunning = (engine: LogicEngine, categoryId: number): boolean => (
  engine.currentCategoryId === categoryId && engine.state === 'countup_studying'
)

export const runStatusSwitchRequest = (options: {
  engine: LogicEngine
  category: Category
  traceId: string
}): { ok: boolean, mode: 'started' | 'switched' | 'already' | 'failed' } => {
  const { engine, category, traceId } = options
  const running = engine.state !== 'stopped' && engine.state !== 'long_break_finished'
  if (isStatusSwitchRunning(engine, category.id)) return { ok: true, mode: 'already' }
  if (!running) {
    engine.start(category.id, category.name, '', { traceId })
    if (!isStatusSwitchRunning(engine, category.id)) return { ok: false, mode: 'failed' }
    return { ok: true, mode: 'started' }
  }
  const result = engine.switchCategoryNow(category.id, category.name, '', '状态切换', traceId)
  if (!result.ok || !isStatusSwitchRunning(engine, category.id)) return { ok: false, mode: 'failed' }
  return { ok: true, mode: 'switched' }
}

export const applyStatusSwitchNote = (options: {
  engine: LogicEngine
  categoryId: number
  note: string
  sourceSessionId: number | string | null | undefined
  updateSource: (sourceSessionId: number | string, note: string) => void
}): boolean => {
  const { engine, categoryId, note, sourceSessionId, updateSource } = options
  if (!isStatusSwitchRunning(engine, categoryId)) return false
  if (sourceSessionId !== null && sourceSessionId !== undefined) updateSource(sourceSessionId, note)
  engine.setCurrentFocusTask(note)
  return true
}
