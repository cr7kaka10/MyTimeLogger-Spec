import { readFileSync } from 'node:fs'
import { strict as assert } from 'node:assert'

const hook = readFileSync(new URL('./useTimer.ts', import.meta.url), 'utf8')
const database = readFileSync(new URL('../db.ts', import.meta.url), 'utf8')

assert(hook.includes("window.addEventListener('sync-pull-complete', consume)"), 'Pull 后必须处理睡眠命令')
assert(hook.includes("window.addEventListener('online', consume)"), '离线恢复后必须补收睡眠命令')
assert(hook.includes('markSleepTimerCommandExecuted'), '命令须以 ID 幂等确认后持久化')
assert(hook.includes('const refreshed = await coordinator?.refresh()') && hook.includes('客户端只刷新并确认命令，禁止二次切换'), '自动睡眠必须只读取服务端权威状态，不得由客户端二次切换')
assert(database.includes('sleep_automation_commands') && database.includes('client_sync_state'), '命令镜像和本地执行状态必须分离')
console.log('useTimer sleep command tests passed')
