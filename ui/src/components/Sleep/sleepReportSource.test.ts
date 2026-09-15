import { selectSleepReportSource } from './sleepReportSource'

const markdown = '## ⏱️ [Part 2: 时间管理报告]\n### 2.1 时间分配'
const oldHtml = '<h2>1.6 晨间日记</h2>'
const repaired = selectSleepReportSource({ analysis_report: markdown, analysis_html: oldHtml })
if (repaired.format !== 'markdown' || repaired.source !== markdown || !repaired.isComplete) {
  throw new Error('stale HTML must not hide the synced full markdown report')
}
const missing = selectSleepReportSource({ analysis_report: '# 睡眠报告', analysis_html: oldHtml })
if (missing.isComplete || missing.format !== 'html') throw new Error('ordinary body must not claim a complete report')
const completeHtml = '<h2>⏱️ [Part 2: 时间管理报告]</h2>'
const canonical = selectSleepReportSource({ analysis_report: markdown, analysis_html: completeHtml })
if (canonical.format !== 'html' || !canonical.isComplete) throw new Error('complete HTML should render normally')

console.log('sleep report source contract passed')
