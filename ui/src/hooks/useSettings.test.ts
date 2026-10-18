import { formatSettingsNetworkError, minutesToStoredSeconds, normalizeSleepAutomationConsent, shouldReloadHotkeysForSetting, studySecondsToMinutes } from './useSettings'

const assertEqual = (actual: unknown, expected: unknown, message: string) => {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`)
  }
}

assertEqual(shouldReloadHotkeysForSetting('atimelogger_enabled'), false, 'aTimeLogger toggle does not reload hotkeys')
assertEqual(shouldReloadHotkeysForSetting('shortcut_toggle_timer'), true, 'timer shortcut reloads hotkeys')
assertEqual(shouldReloadHotkeysForSetting('shortcut_minimize'), true, 'minimize shortcut reloads hotkeys')
assertEqual(studySecondsToMinutes(30, 1500), 0.5, '30 seconds remains half a minute in UI')
assertEqual(minutesToStoredSeconds(0.5), '30', 'half a minute persists as 30 seconds')
for (const value of [true, 1, 'true', '1']) assertEqual(normalizeSleepAutomationConsent(value), true, `${String(value)} grants consent`)
for (const value of [false, 0, 'false', '0', '', 'invalid', null]) assertEqual(normalizeSleepAutomationConsent(value), false, `${String(value)} denies consent`)
assertEqual(formatSettingsNetworkError({ name: 'AbortError' }), '请求超时（服务端无响应）', 'timeout is actionable')
assertEqual(formatSettingsNetworkError(new Error('Failed to fetch')).includes('同一局域网'), true, 'network error explains LAN checks')
