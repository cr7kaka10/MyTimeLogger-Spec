import type { TimerState } from '@core/LogicEngine'
import { canHandoffFocusCategory, focusCategoryPolicy } from '@core/FocusCategoryPolicy'

export const isStructuredFocusLocked = (categoryName: string | null | undefined, state: TimerState): boolean => (
  focusCategoryPolicy(categoryName).structured
  && state !== 'stopped'
  && state !== 'long_break_finished'
)

export const isTimerCategoryGridBlocked = (
  currentCategoryId: number | null | undefined,
  targetCategoryId: number,
  currentCategoryName: string | null | undefined,
  state: TimerState,
  targetCategoryName?: string | null,
  isPaused = false,
): boolean => isStructuredFocusLocked(currentCategoryName, state)
  && currentCategoryId !== targetCategoryId
  && !canHandoffFocusCategory(state, isPaused, currentCategoryName, targetCategoryName)

export const isDirectTimerCategoryActionBlocked = (
  currentCategoryName: string | null | undefined,
  state: TimerState,
): boolean => isStructuredFocusLocked(currentCategoryName, state)

export type TimerCategoryAction = 'start' | 'switchCategory' | 'requestStatusSwitch' | 'endSession'

export const shouldBlockTimerCategoryAction = (
  action: TimerCategoryAction,
  currentCategoryName: string | null | undefined,
  state: TimerState,
  targetCategoryName?: string | null,
  isPaused = false,
): boolean => (action === 'start' || action === 'switchCategory')
  && isDirectTimerCategoryActionBlocked(currentCategoryName, state)
  && !canHandoffFocusCategory(state, isPaused, currentCategoryName, targetCategoryName)
