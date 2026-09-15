import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

declare const test: (name: string, body: () => void) => void
const source = readFileSync(fileURLToPath(new URL('./TaskEditDialog.tsx', import.meta.url)), 'utf8')
const checklistHook = readFileSync(fileURLToPath(new URL('../../hooks/useChecklist.ts', import.meta.url)), 'utf8')

test('task edit dialog retains date safeguards before server submission', () => {
  for (const label of ['推迟 1 天', '推迟 2 天', '推迟 7 天']) {
    if (!source.includes(label)) throw new Error(`${label} shortcut is missing`)
  }
  if (!source.includes('disabled={!canPostpone}')) throw new Error('postpone must be disabled without dates')
  if (!source.includes("draft.start > draft.due")) throw new Error('invalid ranges must stay in the dialog')
  if (!source.includes("result?.status === 'confirmed'")) throw new Error('dialog must close only after confirmed server response')
  if (!source.includes("result?.error_code === 'task_timezone_unavailable'")) throw new Error('dialog must explain unavailable task timezones')
  if (!checklistHook.includes("result?.error_code === 'task_timezone_unavailable'")) throw new Error('shared checklist status must explain unavailable task timezones')
  if (source.includes('getDatabase(')) throw new Error('dialog must not write local SQLite')
})
