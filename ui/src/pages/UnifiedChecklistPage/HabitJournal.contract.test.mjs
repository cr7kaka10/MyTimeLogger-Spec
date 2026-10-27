import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const read = path => readFileSync(fileURLToPath(new URL(path, import.meta.url)), 'utf8')
const assert = (ok, message) => { if (!ok) throw new Error(message) }
const page = read('./index.tsx')
const section = read('./HabitSection.tsx')
const sheet = read('./HabitJournalSheet.tsx')
const month = read('./HabitMonthView.tsx')
const actions = read('./HabitActions.tsx')
const hook = read('../../hooks/useHabits.ts')
const db = read('../../../../core/models/Database.ts')
assert(page.includes('result.confirmed && result.checkedIn') && page.includes('<HabitJournalSheet'), 'only confirmed successful check-ins open a journal')
assert(sheet.includes('saveHabitJournal(habitId, date, content)') && sheet.includes('disabled={busy}') && sheet.includes('setError('), 'save errors retain a retryable draft')
assert(sheet.includes('onClick={onClose}') && sheet.includes('跳过'), 'skip closes the sheet without changing check-in state')
assert(section.includes('checkin?.note && !window.confirm') && section.includes('查看习惯'), 'cancelling a journaled check-in asks first and a habit opens details')
assert(month.includes('moveMonth(month, -1)') && month.includes('moveMonth(month, 1)') && month.includes('grid-cols-7'), 'month navigation uses a seven-day grid')
assert(month.includes('db.getHabitMonthCheckins(id, month)') && month.includes('let active = true') && actions.includes('setJournal({ date, note })'), 'month data is scoped and existing notes can be edited')
assert(db.includes('COALESCE(checkin_date,date)>=?') && !db.includes('COALESCE(checkin_date,date)>=? AND COALESCE(checkin_date,date)<? ORDER BY COALESCE(checkin_date,date) DESC LIMIT 30'), 'month query includes full legacy and current month')
assert(hook.includes("checkedIn: desiredStatus === 2") && hook.includes("return false"), 'failed and withdrawn commands do not trigger a journal')
console.log('habit journal UI contracts passed')
