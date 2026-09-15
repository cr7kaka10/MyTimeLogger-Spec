import type { TimerState } from '@core/LogicEngine'

export const isStructuredFocusLocked = (categoryName: string | null | undefined, state: TimerState): boolean => (
  (categoryName === '输入' || categoryName === '输出')
  && state !== 'stopped'
  && state !== 'long_break_finished'
)

export const isTimerCategoryGridBlocked = (
  currentCategoryId: number | null | undefined,
  targetCategoryId: number,
  currentCategoryName: string | null | undefined,
  state: TimerState,
): boolean => isStructuredFocusLocked(currentCategoryName, state) && currentCategoryId !== targetCategoryId

export const isDirectTimerCategoryActionBlocked = (
  currentCategoryName: string | null | undefined,
  state: TimerState,
): boolean => isStructuredFocusLocked(currentCategoryName, state)

export type TimerCategoryAction = 'start' | 'switchCategory' | 'requestStatusSwitch' | 'endSession'

export const shouldBlockTimerCategoryAction = (
  action: TimerCategoryAction,
  currentCategoryName: string | null | undefined,
  state: TimerState,
): boolean => (action === 'start' || action === 'switchCategory') && isDirectTimerCategoryActionBlocked(currentCategoryName, state)
