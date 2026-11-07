import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import * as jsxRuntime from 'react/jsx-runtime'

const source = readFileSync(new URL('./GoalEditSheet.tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText
const module = { exports: {} }
const mocks = { react: React, 'react/jsx-runtime': jsxRuntime,
  '../common/BottomSheet': { BottomSheet: ({ children }) => children },
  '../Rewards/SourceRewardEditor': { SourceRewardEditor: () => null } }
vm.runInNewContext(compiled, { module, exports: module.exports, require: id => mocks[id] ?? (() => { throw Error(id) })() })
const { GoalEditSheet } = module.exports
const render = goal => renderToStaticMarkup(React.createElement(GoalEditSheet, { goal,
  categories: [{ id: 1, name: '学习' }], onSave: async () => {}, onClose: () => {} }))
const existing = render({ id: 7, title: '每周学习', category_id: 1, category_ids: [1], metric: 'duration', target_value: 60, period: 'weekly', operator: '>=', reward_coins: 0, penalty_coins: 0 })
assert.match(existing, /设置本目标物品奖励/)
assert.match(existing, /奖励 🪙/)
assert.match(existing, /惩罚 🪙/)
assert.ok((existing.match(/value="0"/g) || []).length >= 2, 'zero coin values must survive edit')
assert.match(render(), /保存目标后可在目标卡片设置物品奖励/)
console.log('goal item reward editor contract passed')
