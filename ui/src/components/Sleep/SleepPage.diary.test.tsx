const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const page = fs.readFileSync(new URL('./SleepPage.tsx', import.meta.url), 'utf8') as string

if (!page.includes("MORNING_DIARY_TEMPLATE = '今天值得期待、也愿意主动创造的3件事：\\n1. '")) throw new Error('empty morning diary must use the positive template')
if (!page.includes("EVENING_DIARY_TEMPLATE = '让我开心/满意/感到耳目一新的3件事：\\n1. '")) throw new Error('empty evening diary must use the approved template')
if (!page.includes("value || (title === '晚间日记' ? EVENING_DIARY_TEMPLATE : MORNING_DIARY_TEMPLATE)")) throw new Error('only a blank diary may receive its template')
if (!page.includes('Number(match[1]) + 1')) throw new Error('Markdown ordered list should continue after Enter')

console.log('SleepPage diary template tests passed')
