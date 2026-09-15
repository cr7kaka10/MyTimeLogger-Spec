import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./SessionEditSheet.tsx', import.meta.url)), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

assert(source.includes("import { detectPlatformRuntime } from '../../platform/runtime'"), 'session editor must select its time input by runtime')
assert(source.includes("const androidDateTimeText = (value: string): string => value.replace('T', ' ')") && source.includes("YYYY-MM-DD HH:mm:ss"), 'Android must display an explicit 24-hour timestamp')
assert(source.includes("type={isAndroid ? 'text' : 'datetime-local'}") && source.includes("placeholder={isAndroid ? 'YYYY-MM-DD HH:mm:ss' : undefined}"), 'Android must not delegate visible time formatting to the native AM/PM picker while PC keeps datetime-local')
assert(source.includes('normalizeAndroidDateTime') && source.includes('isValidDateTime') && source.includes("setTimeError('请输入有效的 24 小时时间"), 'invalid Android time input must be rejected before saving')
assert(source.includes('start_time: normalizedStart') && source.includes('end_time: normalizedEnd'), 'valid Android text input must be normalized back into existing session data')

console.log('session 24-hour time format contracts passed')
