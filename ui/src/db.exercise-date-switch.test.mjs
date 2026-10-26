import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const dbSource = readFileSync(new URL('./db.ts', import.meta.url), 'utf8')
const file = ts.createSourceFile('db.ts', dbSource, ts.ScriptTarget.Latest, true)
const fn = file.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === 'syncAfterDateSwitch')
assert.ok(fn, 'date-switch function exists')
const js = ts.transpileModule(fn.getText(file).replace(/^export /, ''), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
}).outputText

function harness(initialResponse) {
  const calls = [], state = { response: initialResponse }
  const context = {
    activeAccountStorageKey: 'account-1',
    dateSwitchSyncState: Object.fromEntries(['exercise', 'sleep', 'timebook', 'checklist'].map(key => [key, { key: '', at: 0, promise: null }])),
    getDatabase: async () => ({}),
    getCurrentTimerClient: () => ({ get: async (path, params) => { calls.push(['state', path, params]); return state.response } }),
    syncNow: async () => { calls.push(['sync']); return { ok: true, merged: 6 } },
  }
  return { run: vm.runInNewContext(`${js}\nsyncAfterDateSwitch`, context), calls, state }
}

for (const [date, dietRows] of [['2026-10-27', 6], ['2026-10-25', 3], ['2026-10-26', 0]]) {
  const h = harness({ ok: true, data: { plan_version: 'v5', diet_checkins: Array(dietRows) } })
  const result = await h.run('exercise', date, { planVersion: 'v5' })
  assert.equal(result.ok, true)
  assert.deepEqual(h.calls.map(call => call[0]), ['state', 'sync'], `${date}: state must precede pull`)
  assert.equal(h.calls[0][2].date, date)
}

const failed = harness({ ok: false, error: 'network' })
assert.equal((await failed.run('exercise', '2026-10-27', { planVersion: 'v5' })).ok, false)
assert.deepEqual(failed.calls.map(call => call[0]), ['state'], 'failed state must not be reported as a successful pull')
failed.state.response = { ok: true, data: { plan_version: 'v5' } }
assert.equal((await failed.run('exercise', '2026-10-27', { planVersion: 'v5', force: true })).ok, true)
assert.deepEqual(failed.calls.map(call => call[0]), ['state', 'state', 'sync'])

const legacy = harness({ ok: false })
await legacy.run('exercise', '2026-10-27', { planVersion: 'v4' })
assert.deepEqual(legacy.calls.map(call => call[0]), ['sync'], 'V4 must not gain a new state request')
const hook = readFileSync(new URL('./hooks/useExercise.ts', import.meta.url), 'utf8')
const page = readFileSync(new URL('./pages/ExercisePage.tsx', import.meta.url), 'utf8')
assert.match(hook, /generation!==authorityGeneration\.current/, 'stale requests must be discarded')
assert.match(page, /authorityStatus !== 'ready'/, 'unknown policy must hide the old score card')
console.log('exercise selected-date state tests passed')
