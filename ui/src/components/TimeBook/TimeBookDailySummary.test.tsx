import { renderToStaticMarkup } from 'react-dom/server'
import { buildDailySummary, TimeBookDailySummary } from './TimeBookDailySummary'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const beforeNine = Date.parse('2026-10-03T08:59:00+08:00')
const afterNine = Date.parse('2026-10-03T09:00:00+08:00')
const base = { date: '2026-10-03', planVersion: 'v4', dietRulesValid: true,
  dietCheckins: { no_snacks: { status: 'completed' }, no_sugary_drinks: { status: 'failed' }, no_refined_staples: { status: 'pending' } },
  bodyMetrics: { weight: 100.6, body_fat_rate: 31, updated_at: '2026-10-03 08:58:00' },
  dailyGoals: [{ id: 'g1', title: '输入 2 小时', period: 'daily', operator: '>=', current: 90, target: 120, rewardCoins: 10, penaltyCoins: 15 }],
  ledger: [
    { id: 'body', source_type: 'body_metric_deadline_penalty', source_id: 'body:2026-10-03', amount: -50, description: '身体指标逾期' },
    { id: 'late', source_type: 'sleep_bedtime_adjustment', source_id: 'sleep:2026-10-03', amount: -40, description: '晚睡' },
    { id: 'cycle', source_type: 'sleep_cycle_penalty', source_id: 'sleep-cycle:2026-10-03', amount: -50, description: '睡眠周期不足' },
  ] }

const pending = buildDailySummary({ ...base, diary: null, nowMs: beforeNine })
assert(pending[0].status === 'pending' && pending[1].status === 'pending', 'sleep items must remain pending before 09:00')
const overdue = buildDailySummary({ ...base, diary: { report_status: 0 }, nowMs: afterNine })
assert(overdue[0].status === 'overdue' && overdue[1].status === 'overdue', 'sleep items must become overdue at 09:00')
const uploaded = buildDailySummary({ ...base, diary: { image_uploaded_at: '2026-10-03 08:59:00', source: 'screenshot_ocr', sync_status: 'success', report_status: 1 }, nowMs: afterNine })
assert(uploaded.find(item => item.key === 'sleep-upload')?.status === 'completed' && uploaded.find(item => item.key === 'sleep-report')?.status === 'overdue', 'upload must not imply full report completion')
const lateUpload = buildDailySummary({ ...base, diary: { image_uploaded_at: '2026-10-03 16:29:10', source: 'screenshot_ocr', sync_status: 'success', report_status: 2, full_report_state: 'generated', report_completed_at: '2026-10-03 16:30:14' }, nowMs: Date.parse('2026-10-03T16:31:00+08:00') })
assert(lateUpload.find(item => item.key === 'sleep-upload')?.status === 'failed' && lateUpload.find(item => item.key === 'sleep-upload')?.actualTime === '16:29', 'late upload must remain failed with first upload time')
assert(lateUpload.find(item => item.key === 'sleep-report')?.status === 'failed' && lateUpload.find(item => item.key === 'sleep-report')?.actualTime === '16:30', 'late report must remain failed with completion time')
const complete = buildDailySummary({ ...base, diary: { image_uploaded_at: '2026-10-03 08:58:00', source: 'screenshot_ocr', sync_status: 'success', report_status: 2, full_report_state: 'generated', report_completed_at: '2026-10-03 08:59:00', morning_diary: '晨记', evening_diary: '晚记' }, nowMs: afterNine })
assert(['sleep-upload', 'sleep-report', 'morning-diary', 'evening-diary'].every(key => complete.find(item => item.key === key)?.status === 'completed'), 'sleep and diary facts must complete independently')
assert(['diet-no_snacks', 'diet-no_sugary_drinks', 'diet-no_refined_staples'].map(key => complete.find(item => item.key === key)?.status).join(',') === 'completed,failed,pending', 'V4 diet facts must preserve authoritative states')
const v5Rules = [
  ['protein_at_lunch_and_dinner', '午晚餐保证蛋白质'], ['vegetables_at_lunch_and_dinner', '午晚餐至少2拳蔬菜'],
  ['controlled_staple_and_no_sugary_drink', '控制主食且不喝含糖饮料'], ['breakfast_on_time', '按时吃早餐'],
  ['lunch_on_time', '按时吃午饭'], ['dinner_on_time', '按时吃晚饭'],
]
const v5Plan = { diet: v5Rules.map(([ruleKey, content]) => ({ ruleKey, content, time: ruleKey === 'breakfast_on_time' ? '08:30 前' : '' })),
  exercisePlan: { 周一: { gym: [], rain: [] }, 周二: { gym: [{}], rain: [] } } } as any
const v5Base = { ...base, date: '2026-10-27', planVersion: 'v5', planDefinition: v5Plan, planReady: true, diary: null, ledger: [],
  dietCheckins: Object.fromEntries(v5Rules.map(([key], index) => [key, { status: index === 0 ? 'completed' : index === 1 ? 'failed' : 'pending' }])) }
const v5Items = buildDailySummary(v5Base).filter(item => item.key.startsWith('diet-'))
assert(v5Items.length === 6 && v5Rules.every(([key]) => v5Items.some(item => item.key === `diet-${key}`)), 'V5 summary must include all six current plan rules')
assert(v5Items.find(item => item.key === 'diet-breakfast_on_time')?.label === '08:30 前 按时吃早餐', 'V5 summary must use the exercise plan label')
assert(v5Rules.every(([key], index) => v5Items.find(item => item.key === `diet-${key}`)?.status === (index === 0 ? 'completed' : index === 1 ? 'failed' : 'pending')), 'V5 summary must use the selected-date facts')
const historical = buildDailySummary({ ...v5Base, dietCheckins: Object.fromEntries(v5Rules.slice(0, 3).map(([key]) => [key, { status: 'completed' }])) })
assert(historical.filter(item => item.key.startsWith('diet-') && item.status === 'plan_only').length === 3, 'historical meal rules must be plan-only')
assert(!buildDailySummary({ ...v5Base, date: '2026-10-26' }).some(item => item.key.startsWith('diet-')), 'V5 rest day must not show diet tasks')
assert(!buildDailySummary({ ...v5Base, planReady: false }).some(item => item.key.startsWith('diet-')), 'incomplete V5 plan must not fall back to three rules')
const task = { id: 'task-1', title: '当天任务', due_date: '2026-10-03 12:00:00', status: 0, is_overdue: false } as any
const habit = { id: 'habit-1', name: '当天习惯', repeatRule: 'daily', status: 0 }
const checklistPending = buildDailySummary({ ...base, diary: null, dailyHabits: [habit], checklistTasks: [task] })
assert(checklistPending.find(item => item.key === 'task-task-1')?.status === 'pending' && checklistPending.find(item => item.key === 'habit-habit-1')?.status === 'pending', 'summary must use pending checklist facts')
const checklistDone = buildDailySummary({ ...base, diary: null, dailyHabits: [{ ...habit, status: 2 }], checklistTasks: [{ ...task, status: 2 }] })
assert(checklistDone.find(item => item.key === 'task-task-1')?.status === 'completed' && checklistDone.find(item => item.key === 'habit-habit-1')?.status === 'completed', 'summary must follow completed checklist facts')
const checklistFailed = buildDailySummary({ ...base, diary: null, dailyHabits: [{ ...habit, status: 1 }], checklistTasks: [{ ...task, is_overdue: true }] })
assert(checklistFailed.find(item => item.key === 'habit-habit-1')?.status === 'failed' && checklistFailed.find(item => item.key === 'task-task-1')?.status === 'overdue', 'summary must follow failed and overdue checklist facts')
const otherDateOverdue = { ...task, id: 'task-other-day', due_date: '2026-10-02 12:00:00', is_overdue: true }
assert(!buildDailySummary({ ...base, diary: null, checklistTasks: [task, otherDateOverdue] }).some(item => item.key === 'task-task-other-day'), 'summary must not mix another day overdue tasks into selected date')
const offlineSleep = buildDailySummary({ ...base, diary: { image_uploaded_at: '2026-10-03 08:59:00', sync_status: 'error', morning_diary_reward_status: 'failed' }, nowMs: afterNine })
assert(offlineSleep.find(item => item.key === 'sleep-upload')?.status === 'completed' && offlineSleep.find(item => item.key === 'morning-diary')?.status === 'pending', 'sync and reward errors must not rewrite local sleep or diary status')
const settledFailure = buildDailySummary({ ...base, diary: null, dailyGoals: [{ ...base.dailyGoals[0], current: 150 }], ledger: [{ id: 'goal-penalty', source_type: 'goal_penalty', source_id: 'goal_g1_20261003', amount: -15 }] })
assert(settledFailure.find(item => item.key === 'goal-g1')?.status === 'failed' && settledFailure.find(item => item.key === 'goal-g1')?.actualAmount === -15, 'settled goal failure must survive later progress changes')
const settledReward = buildDailySummary({ ...base, diary: null, ledger: [{ id: 'goal-reward', source_type: 'goal_reward', source_id: 'goal_g1_20261003', amount: 10 }] })
assert(settledReward.find(item => item.key === 'goal-g1')?.status === 'completed' && settledReward.find(item => item.key === 'goal-g1')?.actualAmount === 10, 'settled goal reward must be authoritative')
assert(!buildDailySummary({ ...base, diary: null, summaryReady: false, dailyHabits: [habit], checklistTasks: [task] }).some(item => ['habit-habit-1', 'task-task-1', 'goal-g1'].includes(item.key)), 'unloaded date must not reuse source facts')
assert(buildDailySummary({ ...base, planVersion: 'v3', diary: null }).every(item => !item.key.startsWith('diet-')), 'non-V4 dates must not fabricate diet items')
assert(complete.some(item => item.key === 'body-metrics' && item.actualAmount === -50), 'body metrics and actual penalty must render')
assert(complete.some(item => item.key === 'goal-g1' && item.ruleAmount === -15), 'active daily goals must render with rule amount')
const orderedKeys = complete.map(item => item.key)
assert(orderedKeys.indexOf('sleep_bedtime_adjustment') < orderedKeys.indexOf('morning-diary'), 'sleep outcomes must precede the morning diary')
assert(orderedKeys.indexOf('morning-diary') < orderedKeys.indexOf('body-metrics'), 'morning items must precede daytime obligations')
assert(orderedKeys.at(-1) === 'evening-diary', 'evening diary must be the final daily item')
const html = renderToStaticMarkup(<TimeBookDailySummary {...base} diary={null} nowMs={beforeNine} onNavigate={() => {}} />)
for (const label of ['每日摘要', '奖励', '处罚', '净额', '体重和体脂率', '上传睡眠图片', '完整睡眠报告', '晨间日记', '晚间日记', '不吃零食', '不喝含糖饮料', '不吃精制主食', '实际 -50']) assert(html.includes(label), `${label} must render`)
for (const amount of ['奖励 0🪙', '处罚 -140🪙', '净额 -140🪙', '规则 -50🪙', '实际 -50🪙']) assert(html.includes(amount), `${amount} must render with a coin emoji`)
assert(!html.includes('未结算🪙'), 'non-numeric unsettled state must not show a coin emoji')
let intent: any = null
const navHtml = <TimeBookDailySummary {...base} diary={null} nowMs={beforeNine} onNavigate={value => { intent = value }} />
navHtml.props.onNavigate({ tab: 'sleep', date: base.date, target: 'morning-diary', nonce: 1 })
assert(intent?.date === base.date && intent?.target === 'morning-diary', 'diary navigation must carry date, target and nonce')
const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const sleepPage = fs.readFileSync(new URL('../Sleep/SleepPage.tsx', import.meta.url), 'utf8') as string
const app = fs.readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8') as string
for (const contract of ['sleep-diary-${type}', 'scrollIntoView', 'onFocusHandled?.(focusIntent.nonce)']) assert(sleepPage.includes(contract), `missing diary focus contract: ${contract}`)
assert(!/ref=\{reportSectionRef\}[^>]*>[\s\S]{0,180}14 天趋势/.test(sleepPage), 'focus ref must not point at the trend section')
assert(/ref=\{reportSectionRef\}[^>]*>[\s\S]{0,300}AI 分析报告/.test(sleepPage), 'focus ref must point at the AI report section')
assert(app.includes('setSleepFocusIntent(intent.target ? intent : null)'), 'app must retain structured sleep focus intent')
assert(html.includes('dark:'), 'summary must keep dark theme classes')
console.log('timebook daily summary tests passed')
