import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { build, transform } from 'esbuild'
import { chromium } from 'playwright'

const root = resolve(import.meta.dirname, '..')
const parserSource = await readFile(resolve(root, 'src/utils/checklistItems.ts'), 'utf8')
const parserModule = await transform(parserSource, { loader: 'ts', format: 'esm' })
const { parseChecklistItems } = await import(`data:text/javascript,${encodeURIComponent(parserModule.code)}`)
assert.deepEqual(parseChecklistItems(undefined), [])
assert.deepEqual(parseChecklistItems([]), [])
assert.deepEqual(parseChecklistItems([{ id: 'b', title: '后', status: 2, sortOrder: 2 },
  { id: 'a', title: '前', status: 0, sortOrder: 1 }, { id: '', title: '坏', status: 0 }]).map(item => item.id), ['a', 'b'])

const bundle = await build({ stdin: {
  contents: `import React from 'react'; import { createRoot } from 'react-dom/client';
    import { ChecklistItemsPreview } from './src/components/Checklist/ChecklistItemsPreview';
    const root = createRoot(document.getElementById('app'));
    window.renderItems = items => root.render(React.createElement(ChecklistItemsPreview, { items }));`,
  resolveDir: root, loader: 'tsx', sourcefile: 'checklist-test.tsx',
}, bundle: true, write: false, platform: 'browser', format: 'iife' })
const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 320, height: 640 } })
  await page.setContent('<div id="app"></div>')
  await page.addScriptTag({ content: bundle.outputFiles[0].text })
  await page.evaluate(() => window.renderItems([]))
  assert.equal(await page.getByRole('button', { name: /检查项/ }).count(), 0)
  await page.evaluate(() => window.renderItems([
    { id: '1', title: '已完成', status: 2, sortOrder: 0 },
    { id: '2', title: '阅读 https://example.com/long/path', status: 0, sortOrder: 1 },
  ]))
  const toggle = page.getByRole('button', { name: /检查项\s*1\/2/ })
  await toggle.waitFor()
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false')
  await toggle.click()
  assert.equal(await toggle.getAttribute('aria-expanded'), 'true')
  assert.equal(await page.getByRole('list', { name: /只读/ }).locator('li').count(), 2)
  assert.equal(await page.getByRole('img', { name: '已完成' }).count(), 1)
  assert.equal(await page.getByRole('link', { name: 'https://example.com/long/path' }).getAttribute('target'), '_blank')
  assert.equal(await page.locator('input[type="checkbox"]').count(), 0)
  await toggle.click()
  assert.equal(await page.getByRole('list', { name: /只读/ }).count(), 0)
  await toggle.press('Enter')
  assert.equal(await toggle.getAttribute('aria-expanded'), 'true')
  console.log('checklist parser and UI contract: passed')
} finally {
  await browser.close()
}
