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

test('provider degradation remains visible and retries without bypassing cooldown', () => {
  if (!source.includes("providerRefresh.status === 'degraded'") || !source.includes('滴答旧快照') || !source.includes('上次完整成功') || !source.includes('本次已安全更新')) {
    throw new Error('provider degradation must have an explicit safe status message')
  }
  if (!source.includes("providerRetryAttemptRef.current > 0 ? 'checklist-auto-retry'") || !source.includes('providerRetryAttemptRef.current < 3') || !worker.includes("params.provider_manual = 'true'")) {
    throw new Error('manual checklist refresh and bounded automatic retries must remain distinguishable')
  }
})

test('complete provider refresh displays the remote observation time', () => {
  if (!source.includes('providerRefresh.provider_observed_at') || !source.includes('滴答观察')) {
    throw new Error('complete provider status must expose the remote observation time')
  }
})

test('generic pull events cannot overwrite request-scoped provider status', () => {
  if (!source.includes('该事件只触发本地数据重载') || !source.includes('discard stale provider result')) {
    throw new Error('generic completion and late provider results must not report a false success')
  }
  if (!worker.includes("provider: providerRefresh ? 'ticktick' : 'core'") || !worker.includes('providerRefresh.complete === true')) {
    throw new Error('sync completion events must expose provider scope and completeness')
  }
})

test('checklist date switches only pull the safe server snapshot', () => {
  const dateSwitch = db.slice(db.indexOf('export async function syncAfterDateSwitch'), db.indexOf('const requireElectronApi'))
  if (dateSwitch.includes('refreshTickTick') || !dateSwitch.includes('date_switch_dedupe')) {
    throw new Error('date switches must be deduplicated without forcing TickTick refreshes')
  }
})
