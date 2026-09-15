import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { newSessionDefaults } from '../TimeBook/TimeBookPage'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), 'utf8')

const now = new Date('2026-08-23T02:35:10.000Z')
const withHistory = newSessionDefaults([
  { end_time: '2026-08-23 09:25:58' },
  { end_time: '2026-08-23 10:35:02' },
], '2026-08-23', now)
assert(withHistory.start_time === '2026-08-23 10:35:02', 'new timebook session must begin at the latest end on the selected day')
assert(withHistory.end_time === '2026-08-23 10:35:10', 'new timebook session must end at current Beijing time')

const withoutHistory = newSessionDefaults([], '2026-08-23', now)
assert(withoutHistory.start_time === withoutHistory.end_time, 'new session without history must start and end at current Beijing time')

const taskSection = read('../../pages/UnifiedChecklistPage/TaskSection.tsx')
const checklist = read('../../hooks/useChecklist.ts')
const db = read('../../db.ts')
assert(taskSection.includes('onAdd(title, dateToShanghaiDateString(new Date()))'), 'new checklist tasks must use Beijing today as the default due date')
assert(checklist.includes("runTaskCommand('create', { title, due_date: dueDate })"), 'new checklist task command must send the selected due date to the server')

const status = read('./SyncStatusBar.tsx')
const layout = read('../../pages/MainLayout.tsx')
const quickActions = read('./PageQuickActions.tsx')
assert(['connecting', 'syncing', 'synced', 'offline', 'failed'].every(state => status.includes(state)), 'shared sync status must represent all required states')
assert(status.includes('mtl:sync-status') && status.includes('sync-pull-complete'), 'status bar must share the sync worker state and completion event')
assert(quickActions.includes('<SyncStatusBar />') && quickActions.indexOf('<SyncStatusBar />') < quickActions.indexOf('明暗切换'), 'sync status must sit to the left of the theme switch in the shared title bar actions')
assert(!layout.includes('<SyncStatusBar />'), 'main page content must not render a floating sync status instance')
assert(status.includes('bg-white/75') && status.includes('dark:bg-gray-800/75') && status.includes('dotTones'), 'sync status must share the light and dark title-bar surface while retaining state dots')
assert(db.includes('latestSharedSyncSequence') && db.includes('sharedSyncSequence === latestSharedSyncSequence'), 'a stale sync run must not overwrite a newer shared success or failure state')

console.log('sync status and defaults contracts passed')
