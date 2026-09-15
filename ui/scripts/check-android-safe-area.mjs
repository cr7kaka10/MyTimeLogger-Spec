import { readFileSync } from 'node:fs'

const read = relative => readFileSync(new URL(relative, import.meta.url), 'utf8')
const config = read('../capacitor.config.ts')
const html = read('../index.html')
const layout = read('../src/pages/MainLayout.tsx')
const assert = (condition, message) => { if (!condition) throw new Error(message) }

assert(config.includes('overlaysWebView: true'), 'Android status bar must overlay the WebView for edge-to-edge rendering')
assert(html.includes('viewport-fit=cover'), 'viewport must expose safe-area inset variables')
assert(layout.includes('env(safe-area-inset-top, 0px)'), 'mobile quick actions must consume the top safe-area inset')
assert(layout.includes('env(safe-area-inset-bottom,0px)'), 'bottom navigation spacing must consume the bottom safe-area inset')
assert(!/safe-area[^\n]*(?:24|32|44|48)px/i.test(layout), 'safe-area layout must not depend on device-specific pixels')
console.log('Android safe-area contract passed')
