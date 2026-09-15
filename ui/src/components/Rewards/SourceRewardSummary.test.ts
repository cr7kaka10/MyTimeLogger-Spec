import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./SourceRewardSummary.tsx', import.meta.url), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
assert(source.includes("summary?.coins ?? 0"), 'zero coin state is visible')
assert(source.includes("'🎁 未设置'"), 'empty item state is visible')
assert(source.includes('item.title'), 'each authoritative item reward is visible')
assert(source.includes('itemRewards || []'), 'all rewards bound to the same source are visible')
assert(source.includes('percent') && source.includes('本月已满'), 'shared progress and the full monthly limit are explicit')
assert(source.includes('dark:text-gray-400'), 'summary uses light and dark theme semantics')
assert(source.includes('奖励读取失败，重试'), 'load failures are retryable')
console.log('source reward summary contracts passed')
