import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const page = readFileSync(fileURLToPath(new URL('./ExercisePage.tsx', import.meta.url)), 'utf8')
if (page.includes('全天时刻表') || page.includes('ex-fab') || page.includes("setTab('sched')")) throw new Error('exercise page must not duplicate the full-day schedule')
if (!page.includes("switchDay(todayTab())}>今</")) throw new Error('exercise page must keep the 今 button')
if (!page.includes('<ExercisePanel') || !page.includes('<ExerciseHistory')) throw new Error('exercise content and history must remain visible')
console.log('exercise schedule ownership contract passed')
