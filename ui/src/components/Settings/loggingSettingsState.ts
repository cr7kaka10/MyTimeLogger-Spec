export type LoggingConfigState = {
  global_level: string
  module_levels: Record<string, string>
  available_levels?: string[]
  logger_names?: string[]
}

export type LoggingDraft = Pick<LoggingConfigState, 'global_level' | 'module_levels'> & { dirty?: boolean }
export const INHERIT_LOG_LEVEL = '__inherit__'

const sortedLevels = (levels: Record<string, string>) =>
  Object.entries(levels || {}).sort(([left], [right]) => left.localeCompare(right))

export const sameEditableLoggingConfig = (left: LoggingDraft, right: LoggingConfigState) =>
  left.global_level === right.global_level
  && JSON.stringify(sortedLevels(left.module_levels)) === JSON.stringify(sortedLevels(right.module_levels))

export const mergeLoggingDraft = (server: LoggingConfigState, draft: LoggingDraft): LoggingConfigState => ({
  ...server,
  global_level: draft.global_level,
  module_levels: { ...draft.module_levels },
})

export const updateModuleLevel = (levels: Record<string, string>, name: string, level: string) => {
  const next = { ...levels }
  if (level === INHERIT_LOG_LEVEL) delete next[name]
  else next[name] = level
  return next
}
