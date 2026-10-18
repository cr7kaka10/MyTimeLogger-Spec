import type { TimerState } from './LogicEngine'
import { resolveInputOutputCountdownSeconds } from './TimerSettings'

export type FocusGroup = 'input-output' | 'side-business' | 'work'

const GROUPS: Record<FocusGroup, readonly string[]> = {
  'input-output': ['输入', '输出'],
  'side-business': ['副业生产', '副业研发', '副业营销'],
  work: ['工作'],
}

const normalized = (name: string | null | undefined) => String(name || '').trim()
const extendedEnabled = () => (globalThis as any).__MTL_EXTENDED_FOCUS_GROUPS__ !== false

export const focusGroupFor = (name: string | null | undefined): FocusGroup | null => {
  const value = normalized(name)
  return (Object.keys(GROUPS) as FocusGroup[]).find(group => (group === 'input-output' || extendedEnabled()) && GROUPS[group].includes(value)) || null
}

export const focusCategoryPolicy = (name: string | null | undefined) => {
  const group = focusGroupFor(name)
  return {
    group,
    timerMode: group ? 'countdown' as const : 'countup' as const,
    structured: Boolean(group),
    allowedTargets: group ? [...GROUPS[group]] : [],
  }
}

export const resolveFocusCommandPolicy = (name: string | null | undefined, configuredDuration: unknown) => {
  const timerMode = focusCategoryPolicy(name).timerMode
  return { timerMode, durationMs: timerMode === 'countdown' ? resolveInputOutputCountdownSeconds(configuredDuration) * 1000 : 0 }
}

export const sameFocusGroup = (left: string | null | undefined, right: string | null | undefined): boolean => {
  const group = focusGroupFor(left)
  return Boolean(group && group === focusGroupFor(right))
}

export const canHandoffFocusCategory = (
  state: TimerState,
  isPaused: boolean,
  current: string | null | undefined,
  target: string | null | undefined,
): boolean => state === 'studying' && !isPaused && normalized(current) !== normalized(target) && sameFocusGroup(current, target)
