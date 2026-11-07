import { writeFile, rm } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { chromium } from 'playwright'

const assert = (value, message) => { if (!value) throw new Error(message) }
const fixture = resolve('__home_slogan_visual.html')
const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
import React from 'react'; import { createRoot } from 'react-dom/client'; import './src/index.css'; import { TimerStats } from './src/components/Timer/TimerStats.tsx';
const root = createRoot(document.getElementById('root'));
window.renderSlogan = value => root.render(React.createElement(TimerStats, { totalTodayMinutes: 0, compactSyncText: '刚刚同步 · 2026-11-07 13:00:50', homeSlogan: value }));
window.renderSlogan('');
</script></body></html>`
let server, browser
try {
  await writeFile(fixture, html)
  server = await createServer({ server: { host: '127.0.0.1', port: 0 }, logLevel: 'error' })
  await server.listen()
  browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 390, height: 700 } })
  await page.goto(`${server.resolvedUrls.local[0]}__home_slogan_visual.html`)
  await page.waitForFunction(() => typeof window.renderSlogan === 'function')
  assert(await page.locator('[data-testid="home-slogan"]').count() === 0, 'empty slogan must be hidden')
  const long = '写给自己的长标语'.repeat(12) + 'A'.repeat(100) + '\n第二行仍要完整显示'
  await page.evaluate(value => window.renderSlogan(value), long)
  await page.waitForFunction(value => document.querySelector('[data-testid="home-slogan"]')?.textContent === value, long)
  const box = selector => page.locator(`[data-testid="${selector}"]`).boundingBox()
  let [total, date, sync, slogan] = await Promise.all(['today-total', 'today-date', 'compact-sync-status', 'home-slogan'].map(box))
  assert(date.x >= total.x + total.width - 2 && Math.abs(date.y - total.y) < 3, 'mobile date must start beside total')
  assert(slogan.y >= Math.max(date.y + date.height, sync.y + sync.height) - 2, 'mobile slogan must follow the metadata row')
  await page.setViewportSize({ width: 1150, height: 500 })
  ;[total, date, sync, slogan] = await Promise.all(['today-total', 'today-date', 'compact-sync-status', 'home-slogan'].map(box))
  assert(slogan.x >= date.x + date.width - 2 && sync.x >= slogan.x + slogan.width - 2, 'desktop slogan must sit between date and sync')
  assert(slogan.height > 35 && await page.locator('[data-testid="home-slogan"]').textContent() === long, 'long slogan must wrap without truncation')
  const light = await page.locator('[data-testid="home-slogan"]').evaluate(element => getComputedStyle(element).color)
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  const dark = await page.locator('[data-testid="home-slogan"]').evaluate(element => getComputedStyle(element).color)
  assert(light !== dark, 'slogan must follow the light and dark themes')
  console.log('home slogan visual checks passed: empty, mobile alignment, desktop wrap, newline, themes')
} finally {
  await browser?.close()
  await server?.close()
  await rm(fixture, { force: true })
}
