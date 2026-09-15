import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const login = readFileSync(resolve(root, 'src/components/Auth/LoginPage.tsx'), 'utf8')
const app = readFileSync(resolve(root, 'src/App.tsx'), 'utf8')
const settings = readFileSync(resolve(root, 'src/hooks/useSettings.ts'), 'utf8')
const startAll = readFileSync(resolve(root, '../start-all.bat'), 'utf8')
const startLocal = readFileSync(resolve(root, '../scripts/start-local-process.ps1'), 'utf8')
const server = readFileSync(resolve(root, '../server/server.py'), 'utf8')
const clientSources = [login, app, settings, startAll].join('\n')
const bootstrapGuard = startAll.indexOf('if errorlevel 1 goto :failed')
const serviceStart = startAll.indexOf('-Name Server')

const checks = [
  ['personal email default removed', !/[\w.+-]+@(?!example\.(?:com|org|net)\b)[\w.-]+\.[A-Za-z]{2,}/.test(clientSources)],
  ['server address is editable', login.includes('服务端地址') && login.includes('setServerAddress')],
  ['server address persists before auth', login.includes('await onServerUrlChange(base)')],
  ['server address is normalized', login.includes('normalizeServerUrl') && login.includes('http://${trimmed}')],
  ['remote profiles have no bundled URL', !settings.includes('VITE_MTL_TESTING_SERVER_URL') && !settings.includes('VITE_MTL_PRODUCTION_SERVER_URL')],
  ['bundled username removed', !/VITE_MTL_(?:TESTING|PRODUCTION)_USERNAME|MTL_USERNAME/.test(clientSources)],
  ['only development receives fallback', app.includes("settings.activeEnvironment === 'development'")],
  ['bootstrap fails before services', startAll.includes('bootstrap-dev.ps1') && bootstrapGuard >= 0 && bootstrapGuard < serviceStart],
  ['local server listens on LAN', startLocal.includes('--host 0.0.0.0 --port 8000')],
  ['server health check stays loopback', startLocal.includes("Url = 'http://127.0.0.1:8000/ping'")],
  ['ordinary settings cannot import provider secrets', !settings.includes('/admin/provider-bindings/import') && server.includes('USER_SERVICE_CONFIG_SCHEMA')],
]

const failed = checks.filter(([, ok]) => !ok).map(([name]) => name)
if (failed.length) {
  console.error(`login-boundary: FAIL (${failed.join(', ')})`)
  process.exit(1)
}
console.log('login-boundary: PASS')
