const fs = (globalThis as any).process.getBuiltinModule('node:fs')

const page = fs.readFileSync(new URL('./SleepPage.tsx', import.meta.url), 'utf8') as string
const types = fs.readFileSync(new URL('../../types.ts', import.meta.url), 'utf8') as string
const hook = fs.readFileSync(new URL('../../hooks/useSleep.ts', import.meta.url), 'utf8') as string
const sourceStatus = fs.readFileSync(new URL('../../utils/sleepSourceStatus.ts', import.meta.url), 'utf8') as string

for (const label of ['睡眠报告已生成', '完整报告已生成', '时间记录过少']) {
  if (!page.includes(label)) throw new Error(`missing sleep report status: ${label}`)
}
if (!page.includes('data-testid="sleep-module-status"')) throw new Error('sleep status must be a module-level surface')
if (!page.includes('等待睡眠数据同步')) throw new Error('sleep status must have an empty-data state')
if (!page.includes('!hasSleepSourceEvidence(data) ? <span>等待截图上传</span>')) throw new Error('diary-only rows must not claim a screenshot OCR sync')
if (!sourceStatus.includes("data.source !== 'screenshot_ocr'")) throw new Error('the default OCR source cannot prove screenshot upload')
if (!hook.includes("setStatusMessage('OCR 已识别')")) throw new Error('OCR completion must remain visible in the authoritative status')
if (!page.includes('statusMessage ? <span>{statusMessage}</span> : !data')) throw new Error('job status must take precedence over an empty sleep snapshot')
const statusUse = page.indexOf('<SleepModuleStatus data={sleepData} statusMessage={statusMessage} />')
const dataBranch = page.indexOf('{!sleepData ?')
const reportContent = page.indexOf('<ReportContent data={sleepData}')
if (statusUse < 0 || statusUse > dataBranch) throw new Error('sleep status must render outside the sleep-data branch')
if (statusUse > reportContent) throw new Error('sleep status must render before report content')
if (!page.includes("data.full_report_state === 'insufficient_time_records'")) throw new Error('insufficient tracking state must drive the warning')
if (!page.includes('formatTrackedDuration(data.tracked_duration_seconds)')) throw new Error('warning must show persisted tracked duration')
if (!page.includes('selectSleepReportSource(data).isComplete')) throw new Error('full report badge must require visible Part 2')
if (!page.includes('extractSleepReportOutline(reportSource.source, reportSource.format)')) throw new Error('report outline must follow the rendered source')
if (!types.includes('full_report_state?:') || !types.includes('tracked_duration_seconds?:')) throw new Error('SleepData must expose persisted report status fields')
for (const label of ['report_completed_at?:', 'completion_reward_amount?:', 'is_all_complete?:']) {
  if (!types.includes(label)) throw new Error(`SleepScoreSettlement must expose ${label}`)
}
if (!hook.includes('db.getSleepData(selectedDate)') || !hook.includes('setRefreshTrigger(prev => prev + 1)')) throw new Error('selected date refresh must reload persisted report status')

console.log('sleep report status contract passed')
