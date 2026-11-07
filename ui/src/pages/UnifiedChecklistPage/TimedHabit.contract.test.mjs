import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../../hooks/useHabits.ts', import.meta.url), 'utf8')
const helper = source.match(/export function timedHabitBlock\([\s\S]*?\n}/)?.[0]
assert.ok(helper, 'timed habit guard must be exported')
const compiled = ts.transpileModule(`${helper}\nexports.block=timedHabitBlock`, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const module = { exports: {} }
const dateToShanghaiDateString = value => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(value)
vm.runInNewContext(compiled, { exports: module.exports, dateToShanghaiDateString, Intl, Date, Number })
const block = module.exports.block
const habit = { window_start_minute: 480, window_end_minute: 600 }
const at = time => new Date(`2026-11-02T${time}:00+08:00`)
assert.match(block(habit, '2026-11-02', 0, at('07:59')), /未到/)
assert.equal(block(habit, '2026-11-02', 0, at('08:00')), null)
assert.equal(block(habit, '2026-11-02', 0, at('09:59')), null)
assert.match(block(habit, '2026-11-02', 0, at('10:00')), /超时/)
assert.match(block(habit, '2026-11-02', 2, at('08:30')), /不能修改/)
assert.match(block(habit, '2026-11-02', 1, at('08:30')), /不能修改/)
assert.equal(block({ ...habit, window_start_minute: null }, '2026-11-02', 2, at('08:30')), null)
console.log('timed habit UI contract passed')
