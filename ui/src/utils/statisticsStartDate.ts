export const beijingDateOffset = (days = 0, nowMs = Date.now()): string => (
  new Date(nowMs + (8 * 60 + days * 24 * 60) * 60 * 1000).toISOString().slice(0, 10)
)

export const isAllowedStatisticsStartDate = (value: string, nowMs = Date.now()): boolean => (
  /^\d{4}-\d{2}-\d{2}$/.test(value) && value <= beijingDateOffset(1, nowMs)
)
