import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const source = readFileSync(fileURLToPath(new URL('./SettingsPage.tsx', import.meta.url)), 'utf8')

assert(source.includes('/admin/provider-bindings/atimelogger/failures'), 'failure count must load details from the read-only endpoint')
assert(source.includes("onStatusClick={integrationStatus?.atimelogger?.failed_count > 0 ? openAtimeloggerFailures : undefined}"), 'only failed status should be clickable')
assert(source.includes("if (response.ok && showAtimeloggerFailures) await loadAtimeloggerFailures()"), 'retry must refresh open failure details')
assert(source.includes('服务端暂不支持失败详情'), 'old server fallback must be explicit')
console.log('aTimeLogger failure details contract passed')
