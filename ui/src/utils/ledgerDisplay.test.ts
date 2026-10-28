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
console.log('ledger display tests passed')
