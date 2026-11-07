import assert from 'node:assert/strict'; import { build } from 'esbuild'
import { chromium } from 'playwright'; import { fileURLToPath } from 'node:url'
const bundle = await build({
  stdin: {
    contents: `import React from 'react'; import { createRoot } from 'react-dom/client';
      import { SessionEditSheet } from './SessionEditSheet';
      createRoot(document.getElementById('root')).render(
        <SessionEditSheet onSave={data => { window.saved = data }} onClose={() => {}} />);`,
    resolveDir: fileURLToPath(new URL('.', import.meta.url)), loader: 'tsx',
  },
  tsconfig: fileURLToPath(new URL('../../../tsconfig.json', import.meta.url)), bundle: true,
  platform: 'browser', format: 'iife', write: false, define: { 'import.meta.env.BASE_URL': '"/"' },
})
const browser = await chromium.launch({ headless: true })
async function save(start, end, android = false) {
  const page = await browser.newPage()
  try {
    await page.setContent('<div id="root"></div>')
    await page.evaluate(isAndroid => {
      window.saved = null
      if (isAndroid) window.Capacitor = { getPlatform: () => 'android', isNativePlatform: () => true }
    }, android)
    await page.addScriptTag({ content: bundle.outputFiles[0].text })
    const inputs = page.locator(android ? 'input[type="text"]' : 'input[type="datetime-local"]')
    const canonical = async raw => android ? raw : page.evaluate(value => {
      const input = document.createElement('input'); input.type = 'datetime-local'
      input.step = '1'; input.value = value; return input.value
    }, raw)
    await inputs.first().fill(await canonical(start))
    await inputs.nth(1).fill(await canonical(end))
    const actualEnd = await inputs.nth(1).inputValue()
    await page.getByRole('button', { name: '保存' }).click()
    return await page.evaluate(actualEnd => ({ actualEnd, saved: window.saved,
      error: document.querySelector('[role="alert"]')?.textContent || '' }), actualEnd)
  } finally { await page.close() }
}
try {
  const screenshot = await save('2026-11-02T20:13:46', '2026-11-02T22:29:00')
  assert.equal(screenshot.actualEnd, '2026-11-02T22:29')
  assert.equal(screenshot.saved?.start_time, '2026-11-02T20:13:46')
  assert.equal(screenshot.saved?.end_time, '2026-11-02T22:29:00')
  assert.equal(screenshot.error, '')
  assert.equal((await save('2026-11-02T20:13:00', '2026-11-02T22:29:46')).saved?.start_time, '2026-11-02T20:13:00')
  assert.equal((await save('2026-11-02T20:13:46', '2026-11-02T22:29:46')).saved?.end_time, '2026-11-02T22:29:46')
  assert.match((await save('2026-11-02T20:13:00', '2026-11-02T20:13:00')).error, /结束时间必须晚于开始时间/)
  assert.match((await save('2026-02-30 20:13:00', '2026-03-01 22:29:00', true)).error, /请输入有效/)
  assert.match((await save('2026-11-02 20:13:46', '2026-11-02 22:29', true)).error, /请输入有效/)
  assert.equal((await save('2026-11-02 20:13:46', '2026-11-02 22:29:00', true)).saved?.end_time, '2026-11-02T22:29:00')
  console.log('SessionEditSheet time validation passed')
} finally { await browser.close() }
