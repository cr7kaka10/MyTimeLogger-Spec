import { beijingDateOffset, isAllowedStatisticsStartDate } from './statisticsStartDate'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const instant = Date.parse('2026-09-24T15:59:59Z')
assert(beijingDateOffset(0, instant) === '2026-09-24', 'Beijing today must ignore host timezone')
assert(beijingDateOffset(1, instant) === '2026-09-25', 'tomorrow is the maximum')
assert(isAllowedStatisticsStartDate('2026-09-25', instant), 'tomorrow must be allowed')
assert(!isAllowedStatisticsStartDate('2026-09-26', instant), 'the day after tomorrow must be rejected')
console.log('statistics start date contracts passed')
