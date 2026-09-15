const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const page = fs.readFileSync(new URL('./SleepPage.tsx', import.meta.url), 'utf8') as string

if (!page.includes("EVENING_DIARY_TEMPLATE = '今天满意的三件事：\\n1. '")) throw new Error('empty evening diary must use the approved template')
if (!page.includes("title === '晚间日记' ? EVENING_DIARY_TEMPLATE : '1. '")) throw new Error('only a blank evening diary may receive the template')
if (!page.includes('Number(match[1]) + 1')) throw new Error('Markdown ordered list should continue after Enter')

console.log('SleepPage diary template tests passed')
