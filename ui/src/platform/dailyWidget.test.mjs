import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { fileURLToPath } from 'node:url'

let checkins = []
let syncOk = true
let submissions = 0
globalThis.__widgetMocks = {
  db: { getTodayCheckins: () => checkins, getHabits: () => [], getChecklistTasks: () => [] },
  client: { commandHabitCheckin: async () => { submissions++; return { ok: true, data: { status: 'confirmed' } } } },
  sync: async () => ({ ok: syncOk }),
}
globalThis.window = Object.assign(new EventTarget(), {
  MTLDailyWidget: { ready() {}, pause() {}, publish() { return true }, refresh() {}, ack() {} },
  setInterval, clearInterval,
})
const built = await build({ entryPoints: [fileURLToPath(new URL('./dailyWidget.ts', import.meta.url))], bundle: true,
  write: false, format: 'esm', platform: 'node', plugins: [{ name: 'widget-fixtures', setup(api) {
    api.onResolve({ filter: /^(\.\.\/db|\.\/dailyWidgetProjection)$/ }, args => ({ path: args.path, namespace: 'fixture' }))
    api.onLoad({ filter: /.*/, namespace: 'fixture' }, args => ({ contents: args.path === '../db'
      ? `export const getDatabase=async()=>globalThis.__widgetMocks.db;
         export const getCurrentTimerClient=()=>globalThis.__widgetMocks.client;
         export const syncNow=()=>globalThis.__widgetMocks.sync();
         export const syncChecklistNow=()=>globalThis.__widgetMocks.sync();`
      : `export const shanghaiDay=()=> '2026-11-01'; export const projectHabits=()=>({});`, loader: 'js' }))
  } }] })
const widget = await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`)
const command = (id, action = 'complete') => ({ kind: 'habit', action, id: 'habit-1', date: '2026-11-01', commandId: id, userId: '7' })
assert.equal(await widget.applyDailyWidgetCommand(command('daily-first')), 'applied')
assert.equal(widget.pendingDailyWidgetHabitJournals().length, 1)
assert.equal(widget.pendingDailyWidgetHabitJournals()[0].userId, '7')
checkins = [{ habit_id: 'habit-1', status: 2 }]
assert.equal(await widget.applyDailyWidgetCommand(command('daily-first')), 'applied')
assert.equal(submissions, 1)
assert.equal(widget.pendingDailyWidgetHabitJournals().length, 1)
widget.dismissDailyWidgetHabitJournal('daily-first')
checkins = []
assert.equal(await widget.applyDailyWidgetCommand(command('daily-fail', 'fail')), 'applied')
assert.equal(widget.pendingDailyWidgetHabitJournals().length, 0)
syncOk = false
assert.equal(await widget.applyDailyWidgetCommand(command('daily-late')), 'pending_sync')
assert.equal(widget.pendingDailyWidgetHabitJournals().length, 0)
const detach = widget.attachDailyWidget(true)
checkins = [{ habit_id: 'habit-1', status: 2 }]
window.dispatchEvent(new Event('sync-pull-complete'))
await new Promise(resolve => setTimeout(resolve, 0))
assert.deepEqual(widget.pendingDailyWidgetHabitJournals().map(item => item.commandId), ['daily-late'])
detach()
console.log('daily widget habit journal runtime passed')
