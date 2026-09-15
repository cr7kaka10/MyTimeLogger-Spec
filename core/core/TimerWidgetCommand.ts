export const TIMER_WIDGET_ACTIONS = ['start', 'switch', 'stop'] as const
export type TimerWidgetAction = typeof TIMER_WIDGET_ACTIONS[number]

export interface TimerWidgetCommand {
  action: TimerWidgetAction
  commandId: string
  categoryId: number
  eventEpochMs: number
}

export type TimerWidgetCommandValidation =
  | { ok: true; command: TimerWidgetCommand }
  | { ok: false; reason: 'invalid-command' }

const FIELDS = ['action', 'commandId', 'categoryId', 'eventEpochMs'] as const
const COMMAND_ID = /^[A-Za-z0-9._:-]{1,64}$/

export function parseTimerWidgetCommand(value: unknown): TimerWidgetCommandValidation {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { ok: false, reason: 'invalid-command' }
  const candidate = value as Record<string, unknown>
  const keys = Object.keys(candidate)
  if (keys.length !== FIELDS.length || !FIELDS.every(field => keys.includes(field))) return { ok: false, reason: 'invalid-command' }
  if (!TIMER_WIDGET_ACTIONS.includes(candidate.action as TimerWidgetAction)) return { ok: false, reason: 'invalid-command' }
  if (typeof candidate.commandId !== 'string' || !COMMAND_ID.test(candidate.commandId)) return { ok: false, reason: 'invalid-command' }
  if (!Number.isSafeInteger(candidate.categoryId) || Number(candidate.categoryId) <= 0) return { ok: false, reason: 'invalid-command' }
  if (!Number.isSafeInteger(candidate.eventEpochMs) || Number(candidate.eventEpochMs) <= 0) return { ok: false, reason: 'invalid-command' }
  return { ok: true, command: candidate as unknown as TimerWidgetCommand }
}
