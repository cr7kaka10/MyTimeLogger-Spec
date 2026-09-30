import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const layout = readFileSync(new URL('./MainLayout.tsx', import.meta.url), 'utf8')
const tabs = readFileSync(new URL('../components/common/TabBar.tsx', import.meta.url), 'utf8')

assert(layout.includes("activeTab === 'timer' ? 'overflow-hidden' : 'overflow-y-auto'"), 'timer home must disable main scrolling while other tabs remain scrollable')
assert(!layout.includes('pb-[calc(4rem+env(safe-area-inset-bottom,0px))]'), 'flow tab bar must replace guessed main bottom padding')
assert(tabs.includes('shrink-0'), 'tab bar must reserve its own flex height')
assert(!tabs.includes('fixed bottom-0'), 'tab bar must not overlay the home viewport')
assert(tabs.includes('safe-area-tabbar'), 'tab bar must retain bottom safe-area handling')
assert(tabs.includes('min-h-11'), 'tab buttons must retain 44px touch targets')

console.log('MainLayout timer viewport contract tests passed')
