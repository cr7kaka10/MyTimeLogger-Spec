const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const hook = fs.readFileSync(new URL('./useSleep.ts', import.meta.url), 'utf8') as string
const refresh = fs.readFileSync(new URL('./useEventRefresh.ts', import.meta.url), 'utf8') as string

if (!hook.includes('const syncRefresh = useSyncRefresh()')) throw new Error('sleep must subscribe to Pull completion')
if (!hook.includes('[selectedDate, refreshTrigger, syncRefresh]')) throw new Error('Pull must reload the selected date')
if (!refresh.includes("useEventRefresh(['sync-pull-complete'])")) throw new Error('refresh must follow completed Pull')
const read = hook.indexOf('getDatabase().then(db => {')
const dateRead = hook.indexOf('db.getSleepData(selectedDate)', read)
const staleGuard = hook.indexOf('if (!current) return', read)
const cleanup = hook.indexOf('return () => { current = false }', read)
if (read < 0 || staleGuard < read || dateRead < staleGuard || cleanup < dateRead) {
  throw new Error('stale date read must not overwrite current selection')
}
console.log('sleep Pull refresh contract passed')
