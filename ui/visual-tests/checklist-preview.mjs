import { readFile, readdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { build } from 'esbuild'
import { chromium } from 'playwright'

const root = resolve(import.meta.dirname, '..')
const cssFile = (await readdir(resolve(root, 'dist/assets'))).find(name => name.endsWith('.css'))
if (!cssFile) throw new Error('先运行 npm run build')
const css = await readFile(resolve(root, 'dist/assets', cssFile), 'utf8')
const bundle = await build({ stdin: {
  contents: `import React from 'react'; import {createRoot} from 'react-dom/client';
    import {ChecklistItemsPreview} from './src/components/Checklist/ChecklistItemsPreview';
    createRoot(document.getElementById('items')).render(React.createElement(ChecklistItemsPreview,{items:[
      {id:'1',title:'整理方案并核对步骤',status:2,sortOrder:0},
      {id:'2',title:'检查页面在手机上的长标题换行与链接 https://example.com/very/long/path/to/reference',status:0,sortOrder:1},
      {id:'3',title:'发布前复查',status:0,sortOrder:2}]}));`,
  resolveDir: root, loader: 'tsx', sourcefile: 'preview.tsx',
}, bundle: true, write: false, platform: 'browser', format: 'iife' })
const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 360, height: 640 }, deviceScaleFactor: 1 })
  await page.setContent(`<style>${css}</style><main class="theme-page min-h-screen p-4"><article class="theme-surface mx-auto max-w-xl rounded-xl border p-4 shadow-sm"><div class="flex gap-3"><button aria-label="标记完成任务" class="h-5 w-5 shrink-0 rounded-full border">✓</button><div class="min-w-0 flex-1"><h2 class="text-sm font-semibold">修复博客网站，采用完全免费的方法</h2><p class="theme-muted mt-1 text-xs">⚑ 中　 🔴 今天 全天　 # 副业营销</p><div id="items"></div></div><button aria-label="启动专注" class="h-7 w-7 shrink-0 rounded-lg bg-blue-50 text-blue-600">▶</button></div></article></main>`)
  await page.addScriptTag({ content: bundle.outputFiles[0].text })
  await page.getByRole('button', { name: /检查项/ }).click()
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('mobile horizontal overflow')
  const light = resolve(tmpdir(), 'mtl-checklist-light.png')
  await page.screenshot({ path: light })
  await page.locator('html').evaluate(element => element.classList.add('dark'))
  const dark = resolve(tmpdir(), 'mtl-checklist-dark.png')
  await page.screenshot({ path: dark })
  console.log(JSON.stringify({ light, dark }))
} finally { await browser.close() }
