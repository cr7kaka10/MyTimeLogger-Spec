import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { SleepAutoScorePanel, sleepAutoScoreState } from './SleepAutoScorePanel'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8')
const panel = read('./SleepAutoScorePanel.tsx')
const page = read('./SleepPage.tsx')
const base = { date: '2026-09-08', sleep_start: '23:00', sleep_end: '07:00', sleep_score: 90 } as any

assert(sleepAutoScoreState(base) === 'no_report', 'raw metrics without a report must remain no_report')
assert(sleepAutoScoreState({ ...base, report_status: 1, analysis_report: '# 报告' }) === 'scoring', 'visible report without settlement must be scoring')
assert(sleepAutoScoreState({ ...base, report_status: 1, analysis_report: '# 报告', score_settlement: { settlement_status: 'not_scored' } }) === 'unavailable', 'missing metrics must be unavailable')
assert(sleepAutoScoreState({ ...base, report_status: 2, analysis_html: '<h1>报告</h1>', score_settlement: { settlement_status: 'scored' } }) === 'scored', 'authoritative settlement must be scored')
assert((panel.match(/'等待报告'/g) || []).length >= 1 && panel.includes('LEGACY_KEYS') && panel.includes('V4_KEYS'), 'no-report state must select the matching rule-version rows')
for (const ordinal of '①②③④⑤⑥⑦⑧⑨⑩') assert(panel.includes(ordinal), `missing ordinal: ${ordinal}`)
for (const label of ['9点前生成睡眠报告', '按时入睡', '起床规律', '华为睡眠评分', '深睡时长', '睡眠周期', '清醒时长', '清醒次数', '入睡用时', '起床用时']) assert(panel.includes(label), `missing score row: ${label}`)
assert(panel.includes('state === \'scored\'') && panel.includes('maxTotal') && panel.includes('总分奖励') && panel.includes('周期惩罚'), 'score and coins must only render for scored state')
assert(panel.includes('22:30–23:30 满分；23:31–00:00 部分分；其他时段未达标'), 'bedtime scoring explanation must be complete')
assert(panel.includes('coin_effect') && panel.includes('sleep-score-coin-') && panel.includes('入睡时间'), 'panel must render snapshot coin attribution and readable bedtime settlement')
assert(page.indexOf('<SleepAutoScorePanel') < page.indexOf('<SleepStatsGrid') && page.indexOf('<SleepStatsGrid') < page.indexOf('📊 AI 分析报告'), 'score panel must stay above raw metrics and report')
assert(!panel.includes('grid-cols-2'), 'ten score indicators must remain one row each without narrow-screen overflow')
const noReportHtml = renderToStaticMarkup(<SleepAutoScorePanel data={base} />)
assert((noReportHtml.match(/等待报告/g) || []).length === 10, 'no-report rendering must visibly contain ten waiting rows')
assert(!noReportHtml.includes('/100') && !noReportHtml.includes('净金币'), 'no-report rendering must not leak scores or coin effects')

const v4Html = renderToStaticMarkup(<SleepAutoScorePanel data={{
  ...base, date: '2026-09-12', report_status: 1, analysis_report: '# 报告',
  score_settlement: {
    settlement_status: 'scored', rule_version: 'sleep-score-v4', score_total: 100, reward_amount: 80, cycle_penalty: 0, net_amount: 180,
    score_breakdown: JSON.stringify({
      sleep_cycles: { score: 30, max_score: 30, coin_effect: '+0 🪙：未触发周期惩罚' }, on_time_sleep: { score: 20, max_score: 20, coin_effect: '+20 🪙：18:00–23:00入睡，获得满额奖励' }, wake_up: { score: 15, max_score: 15, coin_effect: '影响睡眠评分奖励；本项无独立金币流水' },
      awake_count: { score: 10, max_score: 10, coin_effect: '影响睡眠评分奖励；本项无独立金币流水' }, deep_sleep: { score: 10, max_score: 10, coin_effect: '+0 🪙：未触发深睡惩罚' }, report_before_nine: { score: 5, max_score: 5, coin_effect: '影响睡眠评分奖励；本项无独立金币流水' },
      huawei_sleep_score: { score: 5, max_score: 5, coin_effect: '影响睡眠评分奖励；本项无独立金币流水' }, awake_duration: { score: 5, max_score: 5, coin_effect: '影响睡眠评分奖励；本项无独立金币流水' },
    }),
  },
} as any} />)
assert(v4Html.includes('100/100'), 'V4 denominator must be derived from the authoritative eight-row snapshot')
assert(!v4Html.includes('入睡用时') && !v4Html.includes('起床规律'), 'V4 must not render removed indicators')
for (const [ordinal, label] of [['①', '睡眠周期'], ['②', '按时入睡'], ['③', '起床用时'], ['④', '清醒次数'], ['⑤', '深睡时长'], ['⑥', '9点前生成睡眠报告'], ['⑦', '华为睡眠评分'], ['⑧', '清醒时长']]) {
  assert(v4Html.includes(`${ordinal} ${label}`), `V4 breakdown must render ${ordinal} ${label} in snapshot score order`)
}
assert((v4Html.match(/影响睡眠评分奖励；本项无独立金币流水/g) || []).length === 5, 'each non-ledger V4 dimension must explain its score-only coin effect')
assert(v4Html.includes('+0 🪙：未触发周期惩罚') && v4Html.includes('+20 🪙：18:00–23:00入睡，获得满额奖励'), 'V4 panel must render authoritative per-item coin effects')

const noMainSleepHtml = renderToStaticMarkup(<SleepAutoScorePanel data={{
  ...base, date: '2026-09-12', report_status: 1, full_report_state: 'no_main_sleep',
  analysis_report: '无睡眠，严重警告！',
  score_settlement: {
    settlement_status: 'scored', rule_version: 'sleep-score-v4', score_total: 0,
    reward_amount: 0, completion_reward_amount: 0, cycle_penalty: -50, no_sleep_penalty: -200,
    bedtime_coin_status: 'settled', bedtime_coin_amount: -100,
    bedtime_coin_reason: '截至北京时间12:00仍无有效睡眠记录', net_amount: -270,
    score_breakdown: JSON.stringify({
      sleep_cycles: { score: 0, max_score: 30, matched_rule: '无有效主睡眠' },
      on_time_sleep: { score: 0, max_score: 20, matched_rule: '无有效主睡眠' },
      wake_up: { score: 0, max_score: 15, matched_rule: '无有效主睡眠' },
      awake_count: { score: 0, max_score: 10, matched_rule: '无有效主睡眠' },
      deep_sleep: { score: 0, max_score: 10, matched_rule: '无有效主睡眠' },
      report_before_nine: { score: 0, max_score: 5, matched_rule: '无有效主睡眠' },
      huawei_sleep_score: { score: 0, max_score: 5, matched_rule: '无有效主睡眠' },
      awake_duration: { score: 0, max_score: 5, matched_rule: '无有效主睡眠' },
    }),
  },
} as any} />)
assert(noMainSleepHtml.includes('0/100') && noMainSleepHtml.includes('净金币') && noMainSleepHtml.includes('-270'), 'no-main-sleep must render the settled zero score and net coins')
assert(noMainSleepHtml.includes('无睡眠，严重警告！扣200金币') && noMainSleepHtml.includes('无睡眠加罚 -200'), 'no-main-sleep must render the authoritative warning and penalty')
assert(!noMainSleepHtml.includes('等待报告'), 'no-main-sleep must never render a waiting-report row')
assert(!noMainSleepHtml.includes('入睡时间金币') && !noMainSleepHtml.includes('12:00截止结算') && !noMainSleepHtml.includes('等待有效睡眠记录'), 'legacy bedtime coin fields must not render the obsolete card')

const scoredHtml = renderToStaticMarkup(<SleepAutoScorePanel data={{
  ...base,
  report_status: 1,
  analysis_report: '# 报告',
  score_settlement: {
    settlement_status: 'scored', score_total: 100, reward_amount: 80, cycle_penalty: 0, net_amount: 80,
    score_breakdown: JSON.stringify({
      report_before_nine: { score: 5, max_score: 5 }, on_time_sleep: { score: 10, max_score: 10 },
      wake_regular: { score: 10, max_score: 10 }, huawei_sleep_score: { score: 5, max_score: 5 },
      deep_sleep: { score: 10, max_score: 10 }, sleep_cycles: { score: 30, max_score: 30 },
      awake_duration: { score: 5, max_score: 5 }, awake_count: { score: 5, max_score: 5 },
      fall_asleep: { score: 15, max_score: 15 }, wake_up: { score: 5, max_score: 5 },
    }),
  },
} as any} />)
for (const [ordinal, label] of [['①', '睡眠周期'], ['②', '入睡用时'], ['③', '按时入睡'], ['④', '起床规律'], ['⑤', '深睡时长'], ['⑥', '9点前生成睡眠报告'], ['⑦', '华为睡眠评分'], ['⑧', '清醒时长'], ['⑨', '清醒次数'], ['⑩', '起床用时']]) {
  assert(scoredHtml.includes(`${ordinal} ${label}`), `scored breakdown must render ${ordinal} ${label} in maximum-score order`)
}

console.log('sleep auto score panel contracts passed')
