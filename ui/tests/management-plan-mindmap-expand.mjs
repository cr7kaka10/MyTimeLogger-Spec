import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewportSize: viewport })
    await page.setContent('<div id="map" style="width:100%;height:700px"></div>')
    await page.addStyleTag({ path: `${root}/node_modules/mind-elixir/dist/MindElixir.css` })
    await page.addScriptTag({ path: `${root}/node_modules/mind-elixir/dist/MindElixir.iife.js` })
    await page.evaluate(() => {
      const Engine = window.MindElixir.default || window.MindElixir
      const target = document.querySelector('#map')
      const mind = new Engine({ el: target, direction: Engine.RIGHT, editable: false, contextMenu: false, toolBar: false, keypress: false, allowUndo: false, overflowHidden: true })
      mind.init({ nodeData: { id: 'root', topic: '管理方案', expanded: true, children: [{ id: 'domain', topic: '目标', expanded: false, children: [{ id: 'item', topic: '目标一' }] }] } })
      window.__expandCount = 0
      window.__navigationCount = 0
      const nativeExpand = mind.expandNode.bind(mind)
      mind.expandNode = (...args) => { window.__expandCount += 1; return nativeExpand(...args) }
      target.addEventListener('click', event => {
        const expander = event.target.closest('me-epd')
        if (!expander) return
        event.preventDefault()
        event.stopImmediatePropagation()
        mind.expandNode(expander.previousSibling)
      }, true)
      target.addEventListener('click', event => {
        if (!event.target.closest('me-epd') && event.target.closest('me-tpc')) window.__navigationCount += 1
      })
    })
    await page.locator('me-epd').click()
    await page.waitForTimeout(400)
    const state = await page.evaluate(() => ({
      expanded: document.querySelector('[data-nodeid="medomain"]')?.nodeObj.expanded,
      expandCount: window.__expandCount,
      navigationCount: window.__navigationCount,
      childVisible: Boolean(document.querySelector('[data-nodeid="meitem"]')),
    }))
    if (!state.expanded || !state.childVisible || state.expandCount !== 1 || state.navigationCount !== 0) throw new Error(`mindmap expansion failed at ${viewport.width}px: ${JSON.stringify(state)}`)
    await page.locator('[data-nodeid="medomain"]').click()
    if (await page.evaluate(() => window.__navigationCount) !== 1) throw new Error(`topic navigation failed at ${viewport.width}px`)
    await page.close()
  }
  console.log('management plan mindmap browser regression passed')
} finally {
  await browser.close()
}
