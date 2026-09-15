import type { TimerState } from '@core/LogicEngine'

export const isTaskFocusActive = (
  activeTaskId: string | null,
  taskId: string,
  state: TimerState,
  currentCategoryId: number | null | undefined,
  taskCategoryId: number | null | undefined,
  currentNote: string,
  taskTitle: string,
): boolean => Boolean(
  activeTaskId === taskId
  && state !== 'stopped'
  && state !== 'long_break_finished'
  && currentCategoryId === taskCategoryId
  && currentNote === taskTitle
)
