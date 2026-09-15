import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./RewardAddSheet.tsx', import.meta.url), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

assert(source.includes('物品碎片'), 'reward sheet must expose a fragment rule panel')
assert(source.includes('完成奖励型'), 'reward sheet must expose the reward-only product type')
assert(source.includes('商品页不设置绑定来源'), 'product sheet must not contain source binding controls')
assert(source.includes('任一绑定来源每次完成获得 1 枚'), 'fragment target must be a shared product property')
assert(source.includes("value === 'daily' || value === 'monthly' ? value : 'unlimited'"), 'legacy weekly inventory must display as unlimited')
console.log('reward add sheet fragment contracts passed')
