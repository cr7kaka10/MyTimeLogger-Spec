import { readFileSync } from 'node:fs'

const file = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const app = file('../../App.tsx')
const timeBook = file('../../hooks/useTimeBook.ts')
const exercise = file('../../hooks/useExercise.ts')
const page = file('./TimeBookPage.tsx')
const summary = file('./TimeBookDailySummary.tsx')
const check = (condition, message) => { if (!condition) throw new Error(message) }

const pageMemo = app.match(/const page = useMemo\([\s\S]*?\}, \[([^\]]+)\]\)/)?.[1] || ''
check(pageMemo.includes('checklist.tasks'), 'timebook page must rerender when checklist tasks change')
check(app.includes('checklistTasks={checklist.tasks}'), 'timebook must receive current checklist tasks')
check(timeBook.includes("useEventRefresh(['sync-pull-complete', 'balance-updated', LOCAL_HABITS_UPDATED])"), 'timebook must refresh after source events')
check(timeBook.includes('activeDateRef.current !== selectedDate || generation !== loadGenerationRef.current'), 'late date reads must be ignored')
check(timeBook.includes('summaryLoadedDate:') || timeBook.includes('selectedDate, summaryLoadedDate,'), 'summary snapshot must carry its date')
const exerciseListener = exercise.match(/useEffect\(\(\)=>\{const refresh=\(\)=>\{([^}]+)\};window.addEventListener\('sync-pull-complete'/)?.[1] || ''
check(exerciseListener.includes('void load()') && !exerciseListener.includes('syncNow'), 'exercise sync listener must only reread local facts')
check(page.includes('summaryLoadedDate === selectedDate') && page.includes('exercise.loadedDate === selectedDate'), 'timebook must guard both source dates')
check(summary.includes('summaryReady = true') && summary.includes('if (!summaryReady) items.length = 0'), 'unloaded summaries must not show stale source facts')

console.log('daily summary refresh contracts passed')
