import { renderToStaticMarkup } from 'react-dom/server'
import { exportLedgerCsv, LedgerSheet, parseLedgerDisplay } from './LedgerSheet'
import type { LedgerGroup } from '../../hooks/useLedger'
import { LEDGER_SOURCE_CATALOG, ledgerSourceName, ledgerSourcePresentation } from '../../utils/ledgerDisplay'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const render = (groupedEntries: LedgerGroup[], filter: 'all' | 'income' = 'all') => renderToStaticMarkup(
  <LedgerSheet entries={groupedEntries.flatMap(group => group.items)} groupedEntries={groupedEntries} filter={filter} setFilter={() => {}}
    summary={{ balance: 0, income: 0, expense: 0 }} hasMore={false} isLoadingMore={false} loadMore={async () => {}}
    exportEntries={async () => groupedEntries.flatMap(group => group.items)}
    refresh={async () => {}} onClose={() => {}} />,
)
const item = (amount: number) => ({ id: String(amount), amount, source_type: 'task', target_date: '2026-07-01' })

const mixed: LedgerGroup = { date: '2026-07-01', items: [item(3), item(0.1), item(-3)], income: 3.1, expense: 3 }
const mixedMarkup = render([mixed])
assert(mixedMarkup.includes('收入3.1🪙') && mixedMarkup.includes('支出3🪙'), 'mixed group renders both unsigned totals')
assert(!mixedMarkup.includes('收入+3.1') && !mixedMarkup.includes('支出-3'), 'daily totals never render signs')

const incomeOnly: LedgerGroup = { ...mixed, items: [item(3)], income: 3, expense: 0 }
const incomeMarkup = render([incomeOnly], 'income')
assert(incomeMarkup.includes('收入3🪙') && !incomeMarkup.includes('text-xs font-semibold text-green-500">支出'), 'income filter hides the zero expense total')

const legacyGoal = parseLedgerDisplay({ amount: 1, source_type: 'goal_reward', description: '输入+输出 ≥ 6h 08-04', target_date: '2026-08-04' })
const canonicalGoal = parseLedgerDisplay({ amount: -1, source_type: 'goal_penalty', description: '× 目标 输入+输出 ≥ 6h', target_date: '2026-08-04' })
assert(legacyGoal.title === '输入+输出 ≥ 6h【08-04】', 'successful goal title uses target date instead of legacy description date')
assert(canonicalGoal.title === legacyGoal.title, 'failed goal title uses the same normalized title')
const unlockedGoal = parseLedgerDisplay({ amount: 0, source_type: 'reward_buy', source_id: 'reward:goal:goal_daily_20260804', description: '目标自动解锁兑换: 输入+输出 ≥ 6h', target_date: '2026-08-04' })
assert(unlockedGoal.label === '目标' && unlockedGoal.title === '输入+输出 ≥ 6h【08-04】', 'zero-coin goal unlock displays as the settled goal on its target date')

const nonGoal = parseLedgerDisplay({ amount: 1, source_type: 'task_complete', description: '报告提交 08-04', target_date: '2026-08-04' })
assert(nonGoal.title === '报告提交 08-04', 'non-goal title retains its original trailing date')

const namedExercise = parseLedgerDisplay({ amount: 1, source_type: 'exercise_checkin', description: '√ 运动 sc-2026-07-25-0', target_date: '2026-07-25', display_title: '慢跑 30 分钟' })
const unnamedExercise = parseLedgerDisplay({ amount: 1, source_type: 'exercise_checkin', description: '√ 运动 sc-2026-07-25-0', target_date: '2026-07-25' })
assert(namedExercise.title === '慢跑 30 分钟【07-25】', 'exercise title uses checkin item_name')
assert(unnamedExercise.title === '运动打卡【07-25】' && !unnamedExercise.title.includes('sc-'), 'exercise title never exposes item key')
const penalty = parseLedgerDisplay({ amount: -50, source_type: 'body_metric_deadline_penalty', description: '体重体脂逾期未填写（09:00）', target_date: '2026-09-02' })
const duplicatedChecklist = parseLedgerDisplay({ amount: 0.1, source_type: 'task', description: '√ 清单 √ 清单 打印' })
const morningDiary = parseLedgerDisplay({ amount: 10, source_type: 'sleep_morning_diary_reward', description: '晨间日记奖励', target_date: '2026-09-06' })
const eveningDiary = parseLedgerDisplay({ amount: 10, source_type: 'sleep_evening_diary_reward', description: '晚间日记奖励', target_date: '2026-09-06' })
const dietPenalty = parseLedgerDisplay({ amount: -20, source_type: 'exercise_diet_penalty', description: '饮食必做项逾期未完成', target_date: '2026-09-11' })
const severeSleepPenalty = parseLedgerDisplay({ amount: -200, source_type: 'sleep_no_sleep_penalty', description: '无睡眠，严重警告！', target_date: '2026-09-12' })
assert(penalty.label === '运动' && penalty.title === '体重体脂逾期未填写（09:00）', 'body metric penalty uses readable exercise display')
assert(duplicatedChecklist.label === '清单' && duplicatedChecklist.title === '打印', 'repeated checklist prefixes collapse without changing the source row')
assert(morningDiary.label === '睡眠' && morningDiary.title === '晨间日记奖励', 'morning diary ledger uses canonical Chinese title')
assert(eveningDiary.label === '睡眠' && eveningDiary.title === '晚间日记奖励', 'evening diary ledger uses canonical Chinese title')
assert(dietPenalty.label === '饮食' && dietPenalty.sourceName === '饮食约束逾期处罚', 'diet penalty uses its registered Chinese presentation')
assert(severeSleepPenalty.label === '睡眠' && severeSleepPenalty.sourceName === '无睡眠严重处罚', 'no-main-sleep penalty uses its registered Chinese presentation')

const KNOWN_SERVER_LEDGER_TYPES = [
  'habit_checkin', 'habit_fail', 'task_complete', 'task_fail', 'goal_reward', 'goal_penalty',
  'learning_checkin', 'learning_objective_complete', 'exercise_checkin', 'exercise_score',
  'exercise_completion_reward', 'body_metric_deadline_penalty', 'exercise_diet_penalty',
  'sleep_settlement_reward', 'sleep_cycle_penalty', 'sleep_deep_penalty', 'sleep_no_sleep_penalty',
  'sleep_completion_reward', 'sleep_bedtime_adjustment', 'sleep_diary_completion_reward',
  'sleep_morning_diary_reward', 'sleep_evening_diary_reward', 'reward_buy', 'store_custom_spend',
  'manual_adjustment', 'backpack_use', 'backpack_discard', 'external_claim',
]
for (const sourceType of KNOWN_SERVER_LEDGER_TYPES) {
  const presentation = ledgerSourcePresentation(sourceType)
  assert(Boolean(LEDGER_SOURCE_CATALOG[sourceType]), `known server ledger type must be cataloged: ${sourceType}`)
  assert(/^[\u4e00-\u9fff]/.test(presentation.name) && presentation.name !== sourceType, `known server ledger type must have a Chinese name: ${sourceType}`)
  assert(/^[\u4e00-\u9fff]/.test(presentation.badge) && presentation.badge !== sourceType, `known server ledger type must have a Chinese badge: ${sourceType}`)
}
const unknown = parseLedgerDisplay({ amount: 0, source_type: 'future_internal_key', description: '', target_date: '2026-09-12' })
const unknownMarkup = render([{ date: '2026-09-12', items: [{ id: 'unknown', amount: 0, source_type: 'future_internal_key', description: '', target_date: '2026-09-12' }], income: 0, expense: 0 }])
assert(unknown.label === '系统流水' && unknown.sourceName === '系统流水' && unknown.title === '系统流水', 'unknown source must safely fall back to a Chinese system label')
assert(ledgerSourceName('future_internal_key') === '系统流水' && !unknownMarkup.includes('future_internal_key'), 'unknown source must never expose an internal key')
assert(mixedMarkup.includes('>导出</button>'), 'export control must render beside ledger filters')
let selected = ''; let delivered = ''; let deliverCount = 0
const exported = await exportLedgerCsv('income', async filter => { selected = filter ?? ''; return mixed.items }, async (name, content, options) => {
  deliverCount += 1; delivered = `${name}|${content.slice(0, 1)}|${options?.mimeType}`
})
assert(selected === 'income' && exported === 3 && deliverCount === 1, 'export must freeze the selected filter and deliver all loaded export rows once')
assert(delivered.includes('金币流水-收入-') && delivered.includes('|\uFEFF|text/csv'), 'export must deliver a BOM CSV with the matching filter name')
console.log('LedgerSheet daily summary tests passed')
