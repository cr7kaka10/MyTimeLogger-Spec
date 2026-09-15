const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const hook = fs.readFileSync(new URL('./useSleep.ts', import.meta.url), 'utf8') as string
const platform = fs.readFileSync(new URL('../platform/fetch.ts', import.meta.url), 'utf8') as string

for (const [contract, label] of [
  ['SLEEP_FILE_READ_FAILED', 'file read'],
  ['formatPlatformNetworkError', 'network'],
  ['服务端未返回上传任务编号', 'missing request id'],
  ['服务端状态查询失败', 'polling'],
  ["job.status === 'done' || job.status === 'reused'", 'reused terminal status'],
  ["syncAfterDateSwitch('sleep', resultDate)", 'completion settlement refresh'],
  ["detail?.error_code === 'date_mismatch'", 'date mismatch'],
]) if (!hook.includes(contract)) throw new Error(`missing ${label} error contract`)

if (!hook.includes('catch {\n    return fallback')) throw new Error('non-JSON private response body must not reach the alert')
if (!platform.includes("throw new Error('SLEEP_FILE_READ_FAILED')")) throw new Error('file read failures need a stable safe code')
if (/alert\([^\n]*(token|file|text)/i.test(hook)) throw new Error('alerts must not include tokens, image data, or private response bodies')
console.log('sleep transport error contract passed')
