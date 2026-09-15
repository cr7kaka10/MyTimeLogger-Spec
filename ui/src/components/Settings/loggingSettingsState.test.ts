import { INHERIT_LOG_LEVEL, mergeLoggingDraft, sameEditableLoggingConfig, updateModuleLevel } from './loggingSettingsState'

const assert = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message)
}

const server = {
  global_level: 'INFO', module_levels: { 'server.request': 'WARNING' },
  available_levels: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
  logger_names: ['server', 'server.request', 'server.sync_hub', 'server.ticktick_client', 'server.store', 'server.analyzer', 'uvicorn', 'uvicorn.error', 'uvicorn.access'],
}
const sameLegacyDraft = { global_level: 'INFO', module_levels: { 'server.request': 'WARNING' } }
assert(sameEditableLoggingConfig(sameLegacyDraft, server), 'matching legacy draft should be removable')
assert(!sameEditableLoggingConfig({ ...sameLegacyDraft, global_level: 'ERROR' }, server), 'different draft should remain pending')

const merged = mergeLoggingDraft(server, { global_level: 'ERROR', module_levels: {} })
assert(merged.global_level === 'ERROR', 'draft should override editable global level')
assert(merged.logger_names?.length === 9, 'server logger metadata must not be masked by local defaults')
assert(merged.available_levels?.length === 5, 'server available levels must remain authoritative')

const explicit = updateModuleLevel({}, 'server.sync_hub', 'DEBUG')
assert(explicit['server.sync_hub'] === 'DEBUG', 'specific level should create an override')
const inherited = updateModuleLevel(explicit, 'server.sync_hub', INHERIT_LOG_LEVEL)
assert(!('server.sync_hub' in inherited), 'inherit should delete the override key')
assert(server.global_level === 'INFO' && explicit['server.sync_hub'] === 'DEBUG', 'global changes must not mutate explicit overrides')

console.log('loggingSettingsState tests passed')
