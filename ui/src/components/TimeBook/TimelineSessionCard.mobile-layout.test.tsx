import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./TimelineSessionCard.tsx', import.meta.url)), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

assert(source.includes('flex flex-col items-start gap-0.5') && source.includes('md:flex-row md:items-center md:justify-between'), 'mobile uses two rows and desktop keeps the existing horizontal layout')
assert(source.includes('className="whitespace-nowrap"') && source.includes('formatClockTime(session.start_time)') && source.includes('formatClockTime(session.end_time)'), 'the time range remains on one mobile line')
assert(source.includes('formatDurationHms(resolveSessionDurationSeconds(session))'), 'duration keeps the existing formatter')
assert(source.includes('type="button" onClick={onClick}'), 'record editing click behavior remains unchanged')

console.log('timeline session mobile layout contract passed')
