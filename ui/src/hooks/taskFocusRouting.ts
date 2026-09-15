import type { TimerState } from '@core/LogicEngine'

export type TaskFocusSuccess = 'started' | 'retargeted' | 'switched'
export type TaskFocusResult =
  | { status: TaskFocusSuccess }
  | { status: 'blocked'; sourceCategoryName: '输入' | '输出' }
  | { status: 'unavailable'; reason: 'missing-category' | 'missing-engine' | 'action-failed' }

export const decideTaskFocus = (
  state: TimerState,
  sourceCategoryId: number | null,
  sourceCategoryName: string,
  targetCategoryId: number | null,
): TaskFocusResult => {
  if (targetCategoryId === null) return { status: 'unavailable', reason: 'missing-category' }
  const active = state !== 'stopped' && state !== 'long_break_finished'
  if (!active) return { status: 'started' }
  if (sourceCategoryId === targetCategoryId) return { status: 'retargeted' }
  if (sourceCategoryName === '输入' || sourceCategoryName === '输出') {
    return { status: 'blocked', sourceCategoryName }
  }
  return { status: 'switched' }
}

export const executeTaskFocus = async (
  result: TaskFocusResult,
  actions: Record<TaskFocusSuccess, () => void | Promise<void>>,
): Promise<TaskFocusResult> => {
  if (result.status === 'started' || result.status === 'retargeted' || result.status === 'switched') {
    await actions[result.status]()
  }
  return result
}

export const formatTaskFocusBlockedMessage = (source: '输入' | '输出'): string => (
  `当前处于${source}计时状态中，不能切换，按 Alt+C 或提前结束专注才行`
)
