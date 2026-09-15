const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const page = fs.readFileSync(new URL('./SleepPage.tsx', import.meta.url), 'utf8') as string

for (const text of ['isReportReaderOpen', 'sleep-report-reader', 'aria-label="全屏阅读睡眠报告"', 'aria-label="缩小睡眠报告"', "event.key === 'Escape'", '报告目录', 'scrollIntoView', 'dark:bg-slate-950/95', 'hidden rounded-md']) {
  if (!page.includes(text)) throw new Error(`report reader requirement missing: ${text}`)
}
if (page.includes('requestFullscreen') || page.includes('window.open(')) throw new Error('report reader must stay in the current page')
console.log('sleep report reader contract passed')
