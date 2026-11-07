import { writeFile, rm } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { chromium } from 'playwright'
const assert = (value, message) => { if (!value) throw new Error(message) }
const fixture = resolve('__home_slogan_settings.html')
const html = `<!doctype html><html><body><div id="root"></div><script type="module">
import React from 'react'; import { createRoot } from 'react-dom/client'; import './src/index.css'; import { SettingsPage } from './src/components/Settings/SettingsPage.tsx';
const root = createRoot(document.getElementById('root'));
const settings = { home_slogan: '旧标语', statistics_start_date: '2026-11-07' };
const noop = () => {};
window.shouldFail = true; window.savedValue = null;
const render = () => root.render(React.createElement(SettingsPage, { settings, updateSetting: async (key, value) => {
  if (window.shouldFail) return { ok: false, error: '模拟失败' };
  window.savedValue = value; settings.home_slogan = value; render(); return { ok: true };
}, selectedEnvironmentProfile: { serverUrl: '', authToken: '', username: '', verifiedUserId: '' }, activeEnvironment: 'development', selectedEnvironment: 'development', connectionStatus: {},
onSleepReportReady: noop, onOpenCategoryManager: noop, onOpenMealWheelSettings: noop, exportConfig: noop, importConfig: noop,
clearActiveSession: noop, logoutActiveSession: noop, verifyActiveSession: noop, onSignedOut: noop }));
render();
</script></body></html>`
let server, browser
try {
  await writeFile(fixture, html)
  server = await createServer({ server: { host: '127.0.0.1', port: 0 }, logLevel: 'error', plugins: [{
    name: 'isolate-slogan-settings', enforce: 'pre',
    transform(code, id) {
      if (id.endsWith('/SettingsPage.tsx')) return code.replace("import { LoggingSettings } from './LoggingSettings'", 'const LoggingSettings = () => null')
    },
  }] })
  await server.listen()
  browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))
  await page.goto(`${server.resolvedUrls.local[0]}__home_slogan_settings.html`)
  const input = page.locator('#home-slogan')
  await input.waitFor()
  assert(await input.inputValue() === '旧标语', 'saved slogan must load into settings')
  await input.fill('新的标语\n完整第二行')
  await page.getByRole('button', { name: '保存标语' }).click()
  await page.getByRole('alert', { name: '' }).filter({ hasText: '模拟失败' }).waitFor()
  assert(await input.inputValue() === '新的标语\n完整第二行', 'failed save must retain draft')
  await page.evaluate(() => { window.shouldFail = false })
  await page.getByRole('button', { name: '保存标语' }).click()
  await page.waitForFunction(() => window.savedValue === '新的标语\n完整第二行')
  await page.getByRole('button', { name: '清空' }).click()
  await page.waitForFunction(() => window.savedValue === '')
  assert(await input.inputValue() === '', 'clear must empty the editor')
  assert(pageErrors.length === 0, `unexpected browser errors: ${pageErrors.join('; ')}`)
  console.log('home slogan settings checks passed: load, failed save, multiline save, clear')
} finally { await browser?.close(); await server?.close(); await rm(fixture, { force: true }) }
