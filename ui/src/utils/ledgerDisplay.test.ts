import { parseLedgerDisplay } from './ledgerDisplay'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const oldLunch = parseLedgerDisplay({
  source_type: 'exercise_diet_penalty', source_id: 'exercise-diet-penalty:1:2026-10-28:v5:lunch_on_time',
  target_date: '2026-10-28', description: '饮食必做项逾期未完成', amount: -20, display_title: '',
})
assert(oldLunch.title.includes('午餐按时打卡') && oldLunch.description.includes('2026-10-28')
  && oldLunch.description.includes('13:31'), 'old lunch penalty must show rule, date and cutoff')
const unknown = parseLedgerDisplay({ source_type: 'exercise_diet_penalty', source_id: 'unknown',
  target_date: '2026-10-28', description: '原始描述', amount: -20, display_title: '' })
assert(unknown.title === '原始描述' && unknown.description === '原始描述', 'unknown rule keeps original description')
const compensation = parseLedgerDisplay({ source_type: 'store_compensation_credit', source_id: 'credit:1',
  target_date: '2026-10-28', description: '补偿金币 · +200🪙 · 原因：面试占用当天运动时间', amount: 200, display_title: '' })
assert(compensation.title === '补偿金币【10-28】' && compensation.description.includes('面试占用当天运动时间')
  && !compensation.isFail, 'compensation keeps date and reason as income')
const exercise = parseLedgerDisplay({ source_type: 'exercise_zero_checkin_penalty', source_id: 'exercise-zero-checkin:2026-10-28',
  target_date: '2026-10-28', description: '运动漏打卡 · 2026-10-28 · 当天无任何运动训练打卡 · -200🪙', amount: -200, display_title: '' })
assert(exercise.title === '运动漏打卡【10-28】' && exercise.description.includes('当天无任何运动训练打卡')
  && exercise.isFail, 'zero exercise penalty keeps date and cause as expense')
console.log('ledger display tests passed')
