import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8')
const hook = read('./useBehaviorAuditLog.ts')
const sheet = read('../components/ManagementPlan/ManagementPlanSheet.tsx')
const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
assert(hook.includes("timeZone: 'Asia/Shanghai'"), 'default date must use Beijing time')
assert(hook.includes('const seq = ++requestSeq.current'), 'requests must have a stale-response sequence')
assert(hook.includes('if (seq !== requestSeq.current) return'), 'stale responses must be ignored')
assert(hook.includes("setEvents([]); setCursor('')"), 'date changes must reset events and cursor')
assert(!hook.includes('metadata'), 'query result must not expose metadata')
assert(hook.includes('summary: string') && hook.includes('detail: string'), 'behavior rows must expose readable presentation fields')
assert(sheet.indexOf('版本历史</button>') < sheet.indexOf('行为日志</button>'), 'behavior log must follow version history')
assert(sheet.includes('type="date"') && sheet.includes('加载更多') && sheet.includes('该日期暂无行为日志'), 'date, pagination and empty states are required')
assert(sheet.includes("event.summary || '执行了系统操作'") && sheet.includes('event.detail'), 'behavior log must lead with readable Chinese text')
console.log('behavior audit log contracts passed')
