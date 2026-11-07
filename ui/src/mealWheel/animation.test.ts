import assert from 'node:assert/strict'
import { mealWheelKeyframes, mealWheelLanding } from './animation'

for (const count of [2, 6, 12]) {
  const items = Array.from({ length: count }, (_, index) => ({ id: String(index), name: String(index), weight: index + 1 }))
  for (const start of [0, 47, 2217]) for (let index = 0; index < count; index++) {
    const end = mealWheelLanding(items, String(index), start)
    const total = items.reduce((sum, item) => sum + item.weight, 0)
    const before = items.slice(0, index).reduce((sum, item) => sum + item.weight, 0)
    const pointer = ((before + items[index].weight / 2) / total * 360 + end) % 360
    assert.ok(Math.min(pointer, 360 - pointer) < 1e-8, `${count} options, index ${index}`)
    assert.ok(end > start + 2160 && end < start + 2520)
    const frames = mealWheelKeyframes(start, end)
    assert.equal(frames[0].transform, `rotate(${start}deg)`)
    assert.equal(frames[3].transform, `rotate(${end}deg)`)
    assert.deepEqual(frames.map(frame => frame.offset), [0, .16, .72, 1])
  }
}
console.log('meal wheel animation tests passed')
