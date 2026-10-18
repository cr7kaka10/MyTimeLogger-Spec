import { useRef } from 'react'
import type { MainTab } from '../../types'
import type { UseTimeBookReturn } from '../../hooks/useTimeBook'

export type DailySummaryStatus = 'pending' | 'completed' | 'failed' | 'overdue'
export type DailySummaryTarget = 'morning-diary' | 'evening-diary'
export type DailySummaryNavigationIntent = { tab: MainTab; date: string; target?: DailySummaryTarget; nonce: number }
export type DailySummaryLedger = { id: string | number; source_type: string; source_id?: string | number; amount: number; description?: string; occurred_at?: string | null }
export type DailySummaryGoal = { id: string | number; title: string; period: string; operator: string; current: number; target: number; rewardCoins: number; penaltyCoins: number }
export type DailySummaryItem = { key: string; label: string; status: DailySummaryStatus; tab: MainTab; target?: DailySummaryTarget; consequence: 'penalty' | 'sleep_risk' | 'reward_only'; ruleAmount?: number; actualAmount?: number | null; actualTime?: string; sourceIds: string[] }

const DIET_RULES = [['no_snacks', '不吃零食'], ['no_sugary_drinks', '不喝含糖饮料'], ['no_refined_staples', '不吃精制主食']] as const
const SLEEP_LEDGER_RULES: Array<[string, string, number | undefined]> = [
  ['sleep_bedtime_adjustment', '按时入睡', undefined], ['sleep_cycle_penalty', '睡眠周期达标', -50],
  ['sleep_deep_penalty', '深睡时长达标', undefined], ['sleep_no_sleep_penalty', '存在有效主睡眠', undefined],
  ['sleep_settlement_reward', '睡眠评分奖励', undefined], ['sleep_completion_reward', '睡眠指标全完成奖励', undefined],
]
const failed = (value: unknown) => /fail|error|失败/i.test(String(value || ''))
const timeMs = (value?: string | null) => value ? Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value.replace(' ', 'T')}+08:00`) : Number.NaN
const clock = (value?: string | null) => value?.match(/\d{2}:\d{2}/)?.[0]
const signed = (value: number) => value > 0 ? `+${value}` : String(value)
const coins = (value: number) => `${signed(value)}🪙`
const summaryOrder = (item: DailySummaryItem) => item.key === 'sleep-upload' ? 10
  : item.key === 'sleep-report' ? 20
    : item.key.startsWith('sleep_') ? 30
      : item.key === 'morning-diary' ? 40
        : item.key === 'body-metrics' ? 50
          : item.key.startsWith('goal-') ? 60
            : item.key.startsWith('diet-') ? 70
              : item.key === 'evening-diary' ? 90 : 80
const sumMatches = (ledger: DailySummaryLedger[], source: string, token?: string) => {
  const rows = ledger.filter(entry => entry.source_type === source && (!token || String(entry.source_id || '').includes(token) || String(entry.description || '').includes(token)))
  return { amount: rows.length ? rows.reduce((sum, row) => sum + Number(row.amount || 0), 0) : null, ids: rows.map(row => String(row.id)) }
}

export function buildDailySummary({ date, diary, planVersion, dietRulesValid, dietCheckins, bodyMetrics, dailyGoals = [], ledger = [], nowMs = Date.now() }: {
  date: string; diary: UseTimeBookReturn['diary']; planVersion: string; dietRulesValid?: boolean; dietCheckins: Record<string, any>
  bodyMetrics?: { weight?: number | null; body_fat_rate?: number | null; updated_at?: string | null }; dailyGoals?: DailySummaryGoal[]; ledger?: DailySummaryLedger[]; nowMs?: number
}): DailySummaryItem[] {
  const deadline = Date.parse(`${date}T09:00:00+08:00`)
  const timedStatus = (actual?: string, explicitFailure = false): DailySummaryStatus => {
    if (explicitFailure) return 'failed'
    const actualMs = timeMs(actual)
    if (Number.isFinite(actualMs)) return actualMs <= deadline ? 'completed' : 'failed'
    return nowMs >= deadline ? 'overdue' : 'pending'
  }
  const bodyActual = sumMatches(ledger, 'body_metric_deadline_penalty')
  const bodyComplete = bodyMetrics?.weight != null && bodyMetrics?.body_fat_rate != null
  const items: DailySummaryItem[] = [
    { key: 'sleep-upload', label: '09:00 前上传睡眠图片', status: timedStatus(diary?.image_uploaded_at, failed(diary?.sync_status)), tab: 'sleep', consequence: 'sleep_risk', actualTime: clock(diary?.image_uploaded_at), sourceIds: [] },
    { key: 'sleep-report', label: '09:00 前完成完整睡眠报告', status: timedStatus(diary?.report_completed_at, failed(diary?.sync_status) || diary?.full_report_state === 'insufficient_time_records'), tab: 'sleep', consequence: 'sleep_risk', actualTime: clock(diary?.report_completed_at), sourceIds: [] },
    { key: 'body-metrics', label: '09:00 前填写体重和体脂率', status: bodyActual.amount != null && bodyActual.amount < 0 ? 'failed' : bodyComplete ? timedStatus(bodyMetrics?.updated_at || undefined) : timedStatus(), tab: 'exercise', consequence: 'penalty', ruleAmount: -50, actualAmount: bodyActual.amount, sourceIds: bodyActual.ids },
    { key: 'morning-diary', label: '晨间日记', status: diary?.morning_diary?.trim() ? 'completed' : failed(diary?.morning_diary_reward_status) ? 'failed' : 'pending', tab: 'sleep', target: 'morning-diary', consequence: 'reward_only', actualAmount: diary?.morning_diary_reward_status ? Number(diary.morning_diary_reward_amount || 0) : null, sourceIds: [] },
    { key: 'evening-diary', label: '晚间日记', status: diary?.evening_diary?.trim() ? 'completed' : failed(diary?.evening_diary_reward_status) ? 'failed' : 'pending', tab: 'sleep', target: 'evening-diary', consequence: 'reward_only', actualAmount: diary?.evening_diary_reward_status ? Number(diary.evening_diary_reward_amount || 0) : null, sourceIds: [] },
  ]
  if (planVersion === 'v4' && dietRulesValid) for (const [key, label] of DIET_RULES) {
    const value = dietCheckins[key]?.status, actual = sumMatches(ledger, 'exercise_diet_penalty', key)
    items.push({ key: `diet-${key}`, label, status: value === 'completed' ? 'completed' : value === 'failed' || (actual.amount != null && actual.amount < 0) ? 'failed' : 'pending', tab: 'exercise', consequence: 'penalty', ruleAmount: -20, actualAmount: actual.amount, sourceIds: actual.ids })
  }
  for (const goal of dailyGoals.filter(goal => goal.period === 'daily')) {
    const met = goal.operator === '<=' ? goal.current <= goal.target : goal.current >= goal.target
    const actual = sumMatches(ledger, met ? 'goal_reward' : 'goal_penalty', String(goal.id))
    items.push({ key: `goal-${goal.id}`, label: goal.title, status: actual.amount != null ? actual.amount >= 0 ? 'completed' : 'failed' : met ? 'completed' : 'pending', tab: 'timebook', consequence: met ? 'reward_only' : 'penalty', ruleAmount: met ? goal.rewardCoins : -Math.abs(goal.penaltyCoins), actualAmount: actual.amount, sourceIds: actual.ids })
  }
  for (const [source, label, ruleAmount] of SLEEP_LEDGER_RULES) {
    const actual = sumMatches(ledger, source)
    if (actual.amount == null) continue
    items.push({ key: source, label, status: actual.amount < 0 ? 'failed' : 'completed', tab: 'sleep', consequence: actual.amount < 0 ? 'penalty' : 'reward_only', ruleAmount, actualAmount: actual.amount, sourceIds: actual.ids })
  }
  return items.sort((left, right) => summaryOrder(left) - summaryOrder(right))
}

const statusView: Record<DailySummaryStatus, [string, string]> = {
  pending: ['待完成', 'border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300'], completed: ['已完成', 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300'],
  failed: ['失败', 'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300'], overdue: ['已逾期', 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300'],
}

export function TimeBookDailySummary(props: Parameters<typeof buildDailySummary>[0] & { onNavigate: (intent: DailySummaryNavigationIntent) => void }) {
  const nonce = useRef(0), items = buildDailySummary(props)
  const unique = new Map((props.ledger || []).map(row => [String(row.id), row]))
  const rewards = [...unique.values()].reduce((sum, row) => sum + Math.max(0, Number(row.amount || 0)), 0)
  const penalties = [...unique.values()].reduce((sum, row) => sum + Math.min(0, Number(row.amount || 0)), 0)
  return <aside aria-label="每日摘要" className="min-w-0 self-start p-2 lg:sticky lg:top-2 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:p-3">
    <h3 className="mb-1 truncate text-xs font-bold text-slate-700 dark:text-slate-200">每日摘要</h3>
    <p className="mb-2 text-[10px] text-slate-500">奖励 {coins(rewards)} · 处罚 {coins(penalties)} · 净额 {coins(rewards + penalties)}</p>
    <div className="space-y-1.5">{items.map(item => { const [label, tone] = statusView[item.status]; return <button key={item.key} type="button" onClick={() => props.onNavigate({ tab: item.tab, date: props.date, target: item.target, nonce: ++nonce.current })} className={`grid w-full min-w-0 grid-cols-[1fr_auto] items-center gap-2 rounded-lg border px-2 py-2 text-left text-[11px] ${tone}`}><span className="min-w-0"><span className="block break-words leading-4">{item.label}{item.ruleAmount != null ? `（规则 ${coins(item.ruleAmount)}）` : ''}</span><span className="block text-[10px] opacity-80">实际 {item.actualAmount == null ? '未结算' : coins(item.actualAmount)}{item.actualTime ? ` · ${item.actualTime}` : ''}</span></span><span aria-label={label} className="whitespace-nowrap font-semibold">{label}</span></button> })}</div>
  </aside>
}
