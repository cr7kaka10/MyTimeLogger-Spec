import { readFileSync } from 'node:fs'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
const page = readFileSync(new URL('./TimerPage.tsx', import.meta.url), 'utf8')

assert(page.includes('flex min-w-0 flex-col gap-4'), 'category area should remain shrink-safe on narrow screens')
assert(page.includes('className="shrink-0 pt-2"'), 'flash input should follow the complete category grid')
assert(!page.includes('sticky bottom-[calc(5rem+env(safe-area-inset-bottom,0px))]'), 'flash input must not cover extra category rows')

console.log('TimerPage layout tests passed')
