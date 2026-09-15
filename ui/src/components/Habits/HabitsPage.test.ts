import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./HabitsPage.tsx', import.meta.url), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

assert(source.includes("SourceRewardSummary sourceType=\"habit\""), 'habit cards must show the authoritative reward fragment summary')
assert(source.includes('sourceId={String(habit.id)}'), 'each summary must use its own habit source ID')
assert(!source.includes('连续 {streak} 天解锁'), 'habit cards must not describe an item as a consecutive-days unlock')
console.log('habit fragment summary contracts passed')
