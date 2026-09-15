import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const source = readFileSync(fileURLToPath(new URL('./LearningPage.tsx', import.meta.url)), 'utf8')

assert(/flex flex-wrap items-center gap-2 rounded-xl border border-amber-200/.test(source), 'objective bar must wrap controls on narrow screens')
assert(/min-w-\[12rem\] flex-1 basis-\[12rem\] break-words/.test(source), 'objective title must retain horizontal readable width and wrap naturally')
assert(/group flex h-8 flex-none items-center gap-1 whitespace-nowrap/.test(source), 'AI action remains an intact control when it wraps')
console.log('learning objective responsive layout contract passed')
