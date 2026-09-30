import { existsSync, readFileSync } from 'node:fs'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
const componentUrl = new URL('./DiaryQuickEntries.tsx', import.meta.url)
const source = existsSync(componentUrl) ? readFileSync(componentUrl, 'utf8') : ''
const timerPage = readFileSync(new URL('./TimerPage.tsx', import.meta.url), 'utf8')
const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const timeBookPage = readFileSync(new URL('../TimeBook/TimeBookPage.tsx', import.meta.url), 'utf8')
const timeBookHook = readFileSync(new URL('../../hooks/useTimeBook.ts', import.meta.url), 'utf8')

assert(source.includes('data-testid="timer-diary-entries"'), 'home diary entries component is missing')
assert(source.includes("(['morning', 'evening'] as const)"), 'morning and evening cards must share one renderer')
assert(source.includes('grid-cols-2'), 'diary entries must use two equal columns')
assert(source.includes('min-h-11'), 'each diary entry must keep a 44px touch target')
assert(source.includes('[-webkit-line-clamp:2]'), 'long diary preview must clamp to two lines')
assert(source.includes('dark:bg-slate-900'), 'diary entries must include dark theme surface styles')
assert(source.includes('已锁定'), 'locked diary status must be visible')
assert(source.includes('金币'), 'authoritative diary reward status must be visible')
assert(source.includes('BottomSheet'), 'unlocked diary entry must reuse the shared bottom sheet')
assert(source.includes("onSave(editing, draft)"), 'explicit save must keep the diary type')
assert(source.includes("if (draft !=="), 'unchanged diary content must not create a write')
assert(source.includes('onClose={() => setEditing(null)}'), 'closing the editor must discard the draft')
assert(source.includes('>取消</button>'), 'editor must provide an explicit cancel action')
assert(source.includes("if (locked) { onLockedClick(); return }"), 'locked entry must navigate without opening the editor')
assert(timerPage.indexOf('<TimerAiPrompt') < timerPage.indexOf('<DiaryQuickEntries'), 'diary entries must render below the flash prompt')
assert(app.includes("tab === 'timebook' || tab === 'timer'"), 'opening timer must reset the time-book date to Beijing today')
assert(app.includes('diary={timeBook.diary}') && app.includes('onSaveDiary={timeBook.saveDiary}'), 'timer home must reuse the time-book diary state and save path')
assert(!timeBookPage.includes('timebook-morning-diary') && !timeBookPage.includes('timebook-evening-diary'), 'time book must remove both diary edit entries')
assert(timeBookHook.includes("kind: 'diary'") && timeBookHook.includes('diaryContent'), 'time book timeline must keep saved diary events')

console.log('DiaryQuickEntries contract tests passed')
