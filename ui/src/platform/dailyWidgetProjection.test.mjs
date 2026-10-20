import assert from 'node:assert/strict'
import { build } from 'esbuild'

const result = await build({
  entryPoints: ['src/platform/dailyWidgetProjection.ts'],
  bundle: true, format: 'esm', platform: 'node', write: false,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`
const { shanghaiDay, projectHabits } = await import(moduleUrl)

assert.equal(shanghaiDay(Date.parse('2026-10-19T15:59:59Z')), '2026-10-19')
assert.equal(shanghaiDay(Date.parse('2026-10-19T16:00:00Z')), '2026-10-20')
const days = projectHabits([
  { id: 'daily', repeat_rule: 'FREQ=DAILY' },
  { id: 'weekly', repeat_rule: 'FREQ=WEEKLY;BYDAY=TU,TH' },
], '2026-10-20', 3)
assert.deepEqual(days['2026-10-20'], ['daily', 'weekly'])
assert.deepEqual(days['2026-10-21'], ['daily'])
assert.deepEqual(days['2026-10-22'], ['daily', 'weekly'])
assert.equal(Object.keys(projectHabits([], '2026-10-20')).length, 90)
console.log('daily widget projection: 6 assertions passed')
