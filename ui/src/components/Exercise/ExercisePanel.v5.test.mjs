import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import * as jsxRuntime from 'react/jsx-runtime'

const source = readFileSync(new URL('./ExercisePanel.tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText
const module = { exports: {} }
const mocks = {
  react: React,
  'react/jsx-runtime': jsxRuntime,
  '../../db': { getDatabase: async () => ({ getExercisePlanItems: () => [] }) },
  './ExerciseItem': { ExerciseItem: () => null },
  '../../utils/exerciseScore': { exerciseItemPoints: () => [] },
  '../../utils/exerciseAuthoritativeScore': { isAuthoritativeExercisePlan: () => true },
}
vm.runInNewContext(compiled, { module, exports: module.exports, require: id => mocks[id] ?? (() => { throw Error(id) })() })
const { ExercisePanel } = module.exports
const rules = [
  'breakfast_on_time', 'lunch_on_time', 'dinner_on_time',
  'no_sugary_drinks', 'no_refined_staples', 'no_snacks',
]
const labels = { no_sugary_drinks: '不喝含糖饮料', no_refined_staples: '不吃精米白面', no_snacks: '不吃零食' }
const definition = gym => ({ dietRulesValid: true, diet: rules.map(ruleKey => ({ ruleKey, content: labels[ruleKey] || ruleKey, time: '12:00' })),
  exercisePlan: { 周二: { label: '训练', color: '#000', gym, rain: gym }, 周三: { label: '训练', color: '#000', gym, rain: gym }, 日: { label: '休息', color: '#000', gym: [], rain: [] } }, progress: [] })
const render = (date, day, checkins, gym = [{}], locked = false, dietMigrated = false) => renderToStaticMarkup(React.createElement(ExercisePanel, {
  date, day, rain: false, setRain: () => {}, states: {}, setState: () => {}, dietCheckins: checkins,
  setDietState: () => {}, planVersion: 'v5', planDefinition: definition(gym), locked, dietMigrated,
}))
const historical = render('2026-10-27', '周二', Object.fromEntries(['protein_at_lunch_and_dinner', 'vegetables_at_lunch_and_dinner', 'controlled_staple_and_no_sugary_drink'].map(key => [key, { status: 'pending' }])), [{}], true)
assert.match(historical, /饮食约束 · 50分/)
assert.equal((historical.match(/class="diet-check-row/g) || []).length, 6)
assert.equal((historical.match(/disabled=""/g) || []).length, 6, 'historical facts must not be interpreted as restored rules')
assert.match(historical, /breakfast_on_time.*?0\/11分 · 历史日期已锁定，最新计划仅供查看/)
const current = render('2026-10-28', '周三', Object.fromEntries(rules.map(key => [key, { status: 'pending' }])))
assert.equal((current.match(/class="diet-check-row/g) || []).length, 6)
assert.ok(current.indexOf('不喝含糖饮料') < current.indexOf('不吃精米白面') && current.indexOf('不吃精米白面') < current.indexOf('不吃零食'))
assert.doesNotMatch(current, /disabled=""/)
assert.match(render('2026-10-28', '周三', {}), /该日新规则未生效或记录待同步，暂不可打卡/)
assert.equal((render('2026-10-25', '日', {}).match(/class="diet-check-row/g) || []).length, 0)
const migrated = render('2026-11-02', '周一', {}, [{}], false, true)
assert.doesNotMatch(migrated, /饮食约束|diet-check-row/, 'migrated training day must show exercise only')
const hook = readFileSync(new URL('../../hooks/useExercise.ts', import.meta.url), 'utf8')
const helperSource = hook.match(/const V5_RULE_KEYS=.+\nconst hasLatestV5Plan=.+/g)?.[0]
assert.ok(helperSource, 'V5 completeness check exists')
const helperModule = { exports: {} }
vm.runInNewContext(ts.transpileModule(`${helperSource}\nexports.hasLatestV5Plan=hasLatestV5Plan`, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: helperModule.exports })
assert.equal(helperModule.exports.hasLatestV5Plan(definition([{}])), true)
assert.equal(helperModule.exports.hasLatestV5Plan({ ...definition([{}]), diet: definition([{}]).diet.slice(3) }), false)
console.log('V5 plan presentation tests passed')
