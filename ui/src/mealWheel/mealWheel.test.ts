import assert from 'node:assert/strict'
import { defaultMealWheel, mealWheelDisplayPercentages, mealWheelProbabilities, parseMealWheel, validateMealWheelItems } from './config'
import { pickMealWheelItem } from './selection'

const items = [{ id: 'a', name: '面条', weight: 1 }, { id: 'b', name: '米饭', weight: 3 }]
assert.deepEqual(mealWheelProbabilities(items), [0.25, 0.75])
assert.deepEqual(mealWheelDisplayPercentages(items), [25, 75])
assert.deepEqual(mealWheelDisplayPercentages(defaultMealWheel().items), [16.7, 16.7, 16.7, 16.7, 16.6, 16.6])
assert.deepEqual([0, 1, 2, 3].map(ticket => pickMealWheelItem(items, () => ticket).id), ['a', 'b', 'b', 'b'])
assert.equal(validateMealWheelItems([{ ...items[0], name: '面条' }, { ...items[1], name: '面条' }]), '餐食名称不能重复')
assert.equal(validateMealWheelItems([{ ...items[0], weight: 0 }, items[1]]), '权重需为 1–100 的整数')
assert.equal(parseMealWheel('{broken').items.length, defaultMealWheel().items.length)
let calls = 0
assert.equal(pickMealWheelItem([{ ...items[0] }, { ...items[1], weight: 2 }], () => ++calls === 1 ? 0xffff_ffff : 0).id, 'a')
assert.equal(calls, 2)
console.log('meal wheel logic tests passed')
