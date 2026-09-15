import { detectPlatformRuntime } from './runtime'
import { getElectronCapabilities } from './electron'
import { decryptString, encryptString } from './crypto'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }

assert(detectPlatformRuntime({ electronAPI: {} }) === 'electron', 'Electron should win when multiple bridges exist')
assert(detectPlatformRuntime({
  electronAPI: {}, Capacitor: { getPlatform: () => 'android', isNativePlatform: () => true },
}) === 'electron', 'Electron must remain the first runtime choice')
assert(detectPlatformRuntime({
  Capacitor: { getPlatform: () => 'android', isNativePlatform: () => true },
}) === 'capacitor-android', 'native Android Capacitor should be detected')
assert(detectPlatformRuntime({
  Capacitor: { getPlatform: () => 'web', isNativePlatform: () => false },
}) === 'web', 'Capacitor Web must not be treated as Android')
assert(detectPlatformRuntime(undefined) === 'web', 'missing host should use Web fallback')

const capabilities = getElectronCapabilities({
  dbExecuteSync: () => {}, dbQuerySync: () => [], ticktickFetch: async () => ({}),
  encryptStringSync: text => text, decryptStringSync: text => text, openExternalUrl: async () => ({ ok: true }),
  minimizeWindow: () => {}, closeWindow: () => {}, setTrayTooltip: () => {},
  onShortcutTrigger: () => () => {}, reloadHotkeys: () => {},
})
assert(Object.values(capabilities).every(Boolean), 'Electron bridge should expose all mapped capabilities')
assert(Object.values(getElectronCapabilities(null)).every(value => !value), 'missing bridge should expose no Electron capabilities')

const host = globalThis as { window?: unknown }
const previousWindow = host.window
host.window = { electronAPI: { encryptStringSync: (text: string) => `ENC:${text}`, decryptStringSync: (text: string) => text.slice(4) } }
assert(encryptString('secret') === 'ENC:secret', 'Electron should use safeStorage encryption')
assert(decryptString('ENC:secret') === 'secret', 'Electron should use safeStorage decryption')
if (previousWindow === undefined) delete host.window
else host.window = previousWindow

console.log('platform runtime tests passed')
