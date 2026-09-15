import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const page = readFileSync(fileURLToPath(new URL('./TimerPage.tsx', import.meta.url)), 'utf8')
assert(page.includes('<CurrentTimerHeader'), 'all active current states must reuse the standard timer header')
assert(!page.includes('另一台设备正在计时'), 'remote current state must never render an owner-only card')
assert(!page.includes('owner_device_id'), 'timer page must not expose diagnostic device identity')
for (const text of ['刚刚同步', '正在准备计时', '网络不可用', '登录已失效', '正在切换', '正在停止']) {
  assert(page.includes(text), `missing current timer feedback: ${text}`)
}
assert(!page.includes('等待同步 · 请先同步后再操作'), 'readiness must not be reported as generic sync waiting')
assert(page.includes("timerSyncStatus === 'ready'"), 'only ready status may enable timer commands')
assert(page.includes('commandsEnabled={commandsEnabled}'), 'timer controls must receive the readiness gate')
assert(page.match(/aria-live="polite"/g)?.length === 2, 'page must use one compact live region plus the active sync banner')
assert(page.includes('data-testid="compact-sync-status"'), 'compact sync status container missing')
assert(page.includes('[overflow-wrap:anywhere]'), 'narrow Android screens must wrap the compact row safely')
console.log('timer page current-state contract passed')
