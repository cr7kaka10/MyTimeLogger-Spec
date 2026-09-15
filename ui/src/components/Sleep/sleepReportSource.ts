import type { SleepData } from '../../types'

type ReportFields = Pick<SleepData, 'analysis_report' | 'analysis_html'>

export function selectSleepReportSource(data: ReportFields): {
  source: string; format: 'html' | 'markdown'; isComplete: boolean
} {
  const html = data.analysis_html?.trim() || ''
  const markdown = data.analysis_report?.trim() || ''
  const hasPartTwo = (value: string) => /Part\s*2\s*[:：]\s*时间管理报告/i.test(value)
  if (html && hasPartTwo(html)) return { source: html, format: 'html', isComplete: true }
  if (markdown && hasPartTwo(markdown)) return { source: markdown, format: 'markdown', isComplete: true }
  if (html) return { source: html, format: 'html', isComplete: false }
  return { source: markdown, format: 'markdown', isComplete: false }
}
