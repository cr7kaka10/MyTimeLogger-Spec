const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const page = fs.readFileSync(new URL('./SleepPage.tsx', import.meta.url), 'utf8') as string

if (!page.includes("data.full_report_state === 'generated' && selectSleepReportSource(data).isComplete")) {
  throw new Error('full report badge requires a visible Part 2 and non-waiting state')
}
if (!page.includes("data.full_report_state === 'insufficient_time_records'")) {
  throw new Error('waiting state must show the recorded duration')
}
console.log('full report badge contract passed')
