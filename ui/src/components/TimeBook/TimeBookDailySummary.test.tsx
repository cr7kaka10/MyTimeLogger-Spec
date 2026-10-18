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
assert(uploaded[0].status === 'completed' && uploaded[1].status === 'overdue', 'upload must not imply full report completion')
const lateUpload = buildDailySummary({ ...base, diary: { image_uploaded_at: '2026-10-03 16:29:10', source: 'screenshot_ocr', sync_status: 'success', report_status: 2, full_report_state: 'generated', report_completed_at: '2026-10-03 16:30:14' }, nowMs: Date.parse('2026-10-03T16:31:00+08:00') })
assert(lateUpload[0].status === 'failed' && lateUpload[0].actualTime === '16:29', 'late upload must remain failed with first upload time')
assert(lateUpload[1].status === 'failed' && lateUpload[1].actualTime === '16:30', 'late report must remain failed with completion time')
const complete = buildDailySummary({ ...base, diary: { image_uploaded_at: '2026-10-03 08:58:00', source: 'screenshot_ocr', sync_status: 'success', report_status: 2, full_report_state: 'generated', report_completed_at: '2026-10-03 08:59:00', morning_diary: '晨记', evening_diary: '晚记' }, nowMs: afterNine })
assert(['sleep-upload', 'sleep-report', 'morning-diary', 'evening-diary'].every(key => complete.find(item => item.key === key)?.status === 'completed'), 'sleep and diary facts must complete independently')
assert(['diet-no_snacks', 'diet-no_sugary_drinks', 'diet-no_refined_staples'].map(key => complete.find(item => item.key === key)?.status).join(',') === 'completed,failed,pending', 'V4 diet facts must preserve authoritative states')
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
