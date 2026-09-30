import { readFileSync } from 'node:fs'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const page = readFileSync(new URL('./TimerPage.tsx', import.meta.url), 'utf8')
const stats = readFileSync(new URL('./TimerStats.tsx', import.meta.url), 'utf8')
const grid = readFileSync(new URL('./CategoryGrid.tsx', import.meta.url), 'utf8')

assert(stats.includes('compactSyncText?: string'), 'timer stats must accept the sync text for the desktop summary row')
assert(stats.includes('md:flex-row') && stats.includes('md:whitespace-nowrap'), 'desktop duration, date and sync status must share one line')
assert(page.includes('compactSyncText={compactSyncText}'), 'timer page must place sync status inside TimerStats')
assert(!page.includes('data-testid="compact-sync-status"'), 'timer page must not render a second sync row')
assert(page.includes('h-full min-h-0 overflow-hidden'), 'timer home must fit the layout-owned viewport')
assert(!page.includes('min-h-full') && !page.includes('pb-[calc(5rem+env(safe-area-inset-bottom,0px))]'), 'timer home must not add scroll height or duplicate tab padding')
assert(page.includes('shrink-0 flex-col gap-3 md:min-h-0 md:flex-1'), 'desktop category area must absorb the remaining viewport height')
assert(page.includes('md:pt-2 md:pb-4'), 'desktop timer home must keep a controlled 16px bottom breathing space')
assert(grid.includes('grid-cols-5') && grid.includes('md:min-h-0 md:flex-1 md:content-evenly'), 'desktop 19-category grid must keep five columns and distribute four rows evenly')
assert(grid.includes('md:min-h-14'), 'desktop category buttons must remain at least 56px tall')
assert(page.includes('data-testid="timer-diary-slot"') && page.includes('flex min-h-0 flex-1 items-center'), 'mobile diary entries must center in the remaining space')
assert(page.includes('md:flex-none') && !grid.includes(' grid-cols-5 content-evenly'), 'mobile diary centering and category density must not inherit desktop distribution')
assert(page.indexOf('<TimerAiPrompt') < page.indexOf('data-testid="timer-diary-slot"'), 'diary slot must remain below the complete flash prompt')

console.log('TimerPage viewport contract tests passed')
