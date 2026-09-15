import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

declare const test: (name: string, body: () => void) => void
const source = readFileSync(fileURLToPath(new URL('./useChecklist.ts', import.meta.url)), 'utf8')
const db = readFileSync(fileURLToPath(new URL('../db.ts', import.meta.url)), 'utf8')
const worker = readFileSync(fileURLToPath(new URL('../../../core/core/SyncWorker.ts', import.meta.url)), 'utf8')

test('foreground checklist pull always clears syncing after an exception', () => {
  const pull = source.slice(source.indexOf('const pullServerChanges'), source.indexOf('useEffect(() => {', source.indexOf('const pullServerChanges')))
  if (!/try \{[\s\S]*syncNow[\s\S]*catch \(error: any\)[\s\S]*setLatestSyncStatus\(seq, `同步失败/.test(pull)) {
    throw new Error('foreground pull exceptions must replace the syncing status with failure')
  }
})

test('safe provider degradation is not rendered as a global sync failure', () => {
  if (!source.includes("providerRefresh.status === 'degraded'") || !source.includes('本地已同步，外部任务源部分更新，稍后重试')) {
    throw new Error('provider degradation must have an explicit safe status message')
  }
  if (!source.includes("reason: forceRefresh ? 'checklist-refresh' : 'checklist-enter'") || !worker.includes("params.provider_manual = 'true'")) {
    throw new Error('manual checklist refresh must be distinguishable from automatic refreshes')
  }
})

test('checklist date switches only pull the safe server snapshot', () => {
  const dateSwitch = db.slice(db.indexOf('export async function syncAfterDateSwitch'), db.indexOf('const requireElectronApi'))
  if (dateSwitch.includes('refreshTickTick') || !dateSwitch.includes('date_switch_dedupe')) {
    throw new Error('date switches must be deduplicated without forcing TickTick refreshes')
  }
})
