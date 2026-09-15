const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const app = fs.readFileSync(new URL('./App.tsx', import.meta.url), 'utf8') as string
const db = fs.readFileSync(new URL('./db.ts', import.meta.url), 'utf8') as string
const ledger = fs.readFileSync(new URL('./hooks/useLedger.ts', import.meta.url), 'utf8') as string
const timerEvents = fs.readFileSync(new URL('./hooks/useTimerEvents.ts', import.meta.url), 'utf8') as string

if (!app.includes("syncNow({ reason: 'user-action' })")) throw new Error('user actions must request core sync')
if (!app.includes('userActionSyncRef.current?.request()')) throw new Error('tab navigation must trigger sync')
if (!app.includes('setCoreActionSyncRequester(requestActionSync)') || !db.includes('coreActionSyncRequester?.()')) {
  throw new Error('a local database write must schedule the same core sync as a user action')
}
for (const event of ['click', 'change', 'submit']) {
  if (!app.includes(`window.addEventListener('${event}', requestActionSync)`)) throw new Error(`${event} must trigger sync`)
}
if (app.includes("window.addEventListener('input', requestActionSync)")) throw new Error('typing must not trigger one sync per character')
if (!app.includes('onOpenLedger={() => setShowLedger(true)}')) throw new Error('ledger opening must remain connected to app actions')
if (!db.includes("runSyncNow(options, 'core', false)")) throw new Error('syncNow must use core without provider refresh')
if (!ledger.includes("'sync-pull-complete'")) throw new Error('ledger must refresh after core Pull')
if (!timerEvents.includes("window.addEventListener('sync-pull-complete', handleBalanceUpdate)")) throw new Error('top balance must refresh after core Pull')

console.log('user action core sync contract passed')
