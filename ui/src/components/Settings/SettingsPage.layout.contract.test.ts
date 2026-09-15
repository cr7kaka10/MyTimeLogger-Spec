import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const source = readFileSync(fileURLToPath(new URL('./SettingsPage.tsx', import.meta.url)), 'utf8')

assert(/grid-cols-\[148px_minmax\(0,1fr\)_max-content\]/.test(source), 'service row must size its final column for all visible actions')
assert(/flex min-w-0 flex-wrap items-center justify-end gap-2/.test(source), 'status and actions must wrap instead of overflowing')
assert(/flex flex-wrap justify-end gap-2 max-sm:justify-start/.test(source), 'retry and login buttons must remain complete on narrow screens')
console.log('settings responsive layout contract passed')
