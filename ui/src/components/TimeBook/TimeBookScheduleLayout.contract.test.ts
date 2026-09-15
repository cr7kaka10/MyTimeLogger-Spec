import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8')
const page = read('./TimeBookPage.tsx'), timeline = read('./DualTrackTimeline.tsx'), rail = read('./TimeBookScheduleRail.tsx')

assert(page.includes('grid-cols-[42%_minmax(0,58%)]'), 'mobile must reserve 42% for plan and 58% for actual records')
assert(page.includes('lg:grid-cols-[minmax(250px,320px)_minmax(0,1fr)]'), 'desktop must place a bounded plan rail left of timeline')
assert(page.includes('timelineEntries.length === 0') && page.indexOf('<TimeBookScheduleRail') < page.indexOf('timelineEntries.length === 0'), 'empty actual timeline must keep the plan visible')
assert(timeline.includes('手机端实际记录时间线') && timeline.includes('entries.map'), 'mobile right track must merge every actual record kind')
assert(timeline.includes("entry.kind === 'session'") && timeline.includes('TimelinePointCard'), 'mobile actual track must render sessions and non-session facts')
assert(rail.includes('min-w-0') && !rail.includes('overflow-x'), 'plan rail must wrap without horizontal scrolling')
console.log('timebook schedule layout contracts passed')
