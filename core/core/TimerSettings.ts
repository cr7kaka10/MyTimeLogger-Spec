export const INPUT_OUTPUT_COUNTDOWN_MINUTE_OPTIONS = [2, 30, 60, 90] as const
export const DEFAULT_INPUT_OUTPUT_COUNTDOWN_MINUTES = 90
export const LONG_BREAK_MINUTE_OPTIONS = [1, 5, 10, 20] as const
export const DEFAULT_LONG_BREAK_MINUTES = 20
export const DEFAULT_STUDY_REMINDER_RANGE_SECONDS = { min: 300, max: 420 } as const
export const TEST_STUDY_REMINDER_RANGE_SECONDS = { min: 30, max: 60 } as const

const toSupportedMinutes = <T extends readonly number[]>(
  rawSecondsOrMinutes: unknown,
  options: T,
  fallback: T[number],
  legacyMap: Record<number, T[number]> = {},
): T[number] => {
  const value = Number(rawSecondsOrMinutes)
  if (!Number.isFinite(value)) return fallback

  if (Number.isInteger(value) && legacyMap[value] !== undefined) return legacyMap[value]
  if (Number.isInteger(value) && options.includes(value as T[number])) return value as T[number]
  if (Number.isInteger(value) && value % 60 === 0) {
    const minutes = value / 60
    if (legacyMap[minutes] !== undefined) return legacyMap[minutes]
    if (options.includes(minutes as T[number])) return minutes as T[number]
  }

  return fallback
}

export const resolveInputOutputCountdownMinutes = (rawSeconds: unknown): number => {
  return toSupportedMinutes(
    rawSeconds,
    INPUT_OUTPUT_COUNTDOWN_MINUTE_OPTIONS,
    DEFAULT_INPUT_OUTPUT_COUNTDOWN_MINUTES,
    { 3: 2 },
  )
}

export const resolveInputOutputCountdownSeconds = (rawSeconds: unknown): number => (
  resolveInputOutputCountdownMinutes(rawSeconds) * 60
)

export const resolveLongBreakMinutes = (rawSeconds: unknown): number => (
  toSupportedMinutes(rawSeconds, LONG_BREAK_MINUTE_OPTIONS, DEFAULT_LONG_BREAK_MINUTES)
)

export const resolveLongBreakSeconds = (rawSeconds: unknown): number => (
  resolveLongBreakMinutes(rawSeconds) * 60
)

export const resolveStudyReminderRangeSeconds = (rawMin: unknown, rawMax: unknown): { min: number; max: number } => {
  const min = Number(rawMin)
  const max = Number(rawMax)
  if (min === 0 && max === 60) return { ...TEST_STUDY_REMINDER_RANGE_SECONDS }
  if (!Number.isFinite(min) || !Number.isFinite(max) || min < 0 || max < min) {
    return { ...DEFAULT_STUDY_REMINDER_RANGE_SECONDS }
  }
  return { min: Math.floor(min), max: Math.floor(max) }
}
