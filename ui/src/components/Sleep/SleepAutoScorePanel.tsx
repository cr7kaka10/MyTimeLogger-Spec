import React, { memo } from 'react'
import type { SleepAutoScoreState, SleepData } from '../../types'

const LABELS: Record<string, string> = {
  report_before_nine: '9点前生成睡眠报告', on_time_sleep: '按时入睡', wake_regular: '起床规律',
  huawei_sleep_score: '华为睡眠评分', deep_sleep: '深睡时长', sleep_cycles: '睡眠周期',
  awake_duration: '清醒时长', awake_count: '清醒次数', fall_asleep: '入睡用时', wake_up: '起床用时',
}
const LEGACY_KEYS = ['report_before_nine', 'on_time_sleep', 'wake_regular', 'huawei_sleep_score', 'deep_sleep', 'sleep_cycles', 'awake_duration', 'awake_count', 'fall_asleep', 'wake_up']
const V4_KEYS = ['sleep_cycles', 'on_time_sleep', 'wake_up', 'awake_count', 'deep_sleep', 'report_before_nine', 'huawei_sleep_score', 'awake_duration']
const actualValue = (key: string, data: SleepData) => ({
  report_before_nine: '--', on_time_sleep: data.sleep_start || '--', wake_regular: data.atm_sleep_end || '--',
  huawei_sleep_score: data.sleep_score ?? '--', deep_sleep: data.deep_sleep_min == null ? '--' : `${data.deep_sleep_min} 分钟`,
  sleep_cycles: data.sleep_cycles == null ? '--' : `${data.sleep_cycles} 次`, awake_duration: data.awake_min == null ? '--' : `${data.awake_min} 分钟`,
  awake_count: data.awake_count == null ? '--' : `${data.awake_count} 次`, fall_asleep: data.fall_asleep_min == null ? '--' : `${data.fall_asleep_min} 分钟`,
  wake_up: data.wake_up_min == null ? '--' : `${data.wake_up_min} 分钟`,
}[key] ?? '--')

export const sleepAutoScoreState = (data: SleepData): SleepAutoScoreState => {
  const hasReport = data.full_report_state === 'no_main_sleep'
    || Number(data.report_status || 0) >= 1 && Boolean((data.analysis_report || data.analysis_html || '').trim())
  if (!hasReport) return 'no_report'
  if (!data.score_settlement) return 'scoring'
  return data.score_settlement.settlement_status === 'scored' ? 'scored' : 'unavailable'
}

export const SleepAutoScorePanel = memo(({ data }: { data: SleepData }) => {
  const state = sleepAutoScoreState(data); const settlement = data.score_settlement
  const noMainSleep = data.full_report_state === 'no_main_sleep'
  const scores = (() => { try { return JSON.parse(settlement?.score_breakdown || '{}') } catch { return {} } })()
  const missing = (() => { try { return JSON.parse(settlement?.missing_fields || '[]') as string[] } catch { return [] } })()
  const fallbackKeys = String(settlement?.rule_version || '').includes('v4') || data.date >= '2026-09-12' ? V4_KEYS : LEGACY_KEYS
  const displayRows = state === 'scored'
    ? Object.entries(scores).map(([key, row]: [string, any], originalIndex) => ({ key, row, originalIndex }))
      .sort((left, right) => Number(right.row?.max_score ?? 0) - Number(left.row?.max_score ?? 0) || left.originalIndex - right.originalIndex)
    : fallbackKeys.map((key, originalIndex) => ({ key, row: null, originalIndex }))
  const maxTotal = displayRows.reduce((total, item) => total + Number(item.row?.max_score ?? 0), 0)
  return <section data-testid="sleep-auto-score-panel" data-score-state={state} className="rounded-2xl border border-violet-200 bg-violet-50/60 p-4 text-sm text-slate-700 dark:border-violet-900 dark:bg-violet-950/30 dark:text-slate-200">
    <div className="flex items-center justify-between gap-3"><div><h3 className="text-base font-bold text-violet-900 dark:text-violet-200">🌙 睡眠自动评分</h3><p className="text-xs text-slate-500">服务端报告生成后自动评分</p></div>{state === 'scored' && <strong className="text-2xl text-violet-700 dark:text-violet-300">{settlement!.score_total}/{maxTotal}</strong>}</div>
    {noMainSleep && <p role="alert" className="mt-3 rounded-xl border border-red-300 bg-red-50 px-3 py-2.5 font-bold text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">无睡眠，严重警告！扣200金币</p>}
    {state === 'scoring' && <p className="mt-3 rounded-lg bg-white/80 p-3 text-amber-700">评分生成中，正在等待权威结算回读…</p>}
    {state === 'unavailable' && <p className="mt-3 rounded-lg bg-white/80 p-3 text-amber-700">暂不可评分：{missing.join('、') || '必要指标不足'}，请重新分析。</p>}
    <div className="mt-3 divide-y divide-violet-100 overflow-hidden rounded-xl bg-white/85 dark:divide-violet-900 dark:bg-slate-900/70">{displayRows.map(({ key, row }, index) => {
      return <div key={key} className="flex min-w-0 items-start justify-between gap-3 px-3 py-2.5"><div className="min-w-0"><div className="font-medium">{'①②③④⑤⑥⑦⑧⑨⑩'[index]} {LABELS[key] || key}</div><div className="break-words text-xs text-slate-500">实际值：{state === 'scored' ? row?.raw_value ?? '--' : actualValue(key, data)}{state === 'scored' && <> · {row?.matched_rule || '--'}</>}</div>{state === 'scored' && <div className="mt-0.5 break-words text-xs text-slate-500" data-testid={`sleep-score-coin-${key}`}>{row?.coin_effect || '影响睡眠评分奖励；本项无独立金币流水'}</div>}{key === 'on_time_sleep' && state === 'scored' && <div className="text-xs text-slate-500">22:30–23:30 满分；23:31–00:00 部分分；其他时段未达标</div>}{key === 'wake_regular' && <div className="text-xs text-slate-500">只按 aTimeLogger 睡眠计时截止时刻评分；华为醒来时刻仅用于起床用时</div>}</div><span className="shrink-0 font-semibold text-violet-700 dark:text-violet-300">{state === 'scored' ? `${row?.score ?? 0}/${row?.max_score ?? 0}` : '等待报告'}</span></div>
    })}</div>
    {state === 'no_report' && <p className="mt-3 text-center text-xs text-slate-500">生成睡眠报告后自动评分</p>}
    {state === 'scored' && <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs font-medium"><span>规则 {settlement!.rule_version}</span><span>总分奖励 {Number(settlement!.reward_amount || 0) >= 0 ? '+' : ''}{settlement!.reward_amount || 0} 🪙</span><span>全完成奖励 {Number(settlement!.completion_reward_amount || 0) >= 0 ? '+' : ''}{settlement!.completion_reward_amount || 0} 🪙</span><span>周期惩罚 {settlement!.cycle_penalty || 0} 🪙</span><span>深睡惩罚 {settlement!.deep_sleep_penalty || 0} 🪙</span><span>入睡时间 {settlement!.bedtime_coin_amount || 0} 🪙</span><span>晨间日记 {settlement!.morning_diary_reward_amount || 0} 🪙</span><span>晚间日记 {settlement!.evening_diary_reward_amount || 0} 🪙</span>{noMainSleep && <span>无睡眠加罚 {settlement!.no_sleep_penalty ?? -200} 🪙</span>}<span>净金币 {settlement!.net_amount} 🪙</span></div>}
  </section>
})
SleepAutoScorePanel.displayName = 'SleepAutoScorePanel'
