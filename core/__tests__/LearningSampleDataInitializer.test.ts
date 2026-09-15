import { describe, expect, it } from 'vitest'
import { LEARNING_SEED_TASKS } from '../models/LearningSampleDataInitializer'

describe('learning sample categories', () => {
  it('defines all 32 tasks as the fixed 20 input / 12 output mapping', () => {
    expect(LEARNING_SEED_TASKS).toHaveLength(32)
    expect(LEARNING_SEED_TASKS.every(task => task.category_name === '输入' || task.category_name === '输出')).toBe(true)
    expect(LEARNING_SEED_TASKS.filter(task => task.category_name === '输入')).toHaveLength(20)
    expect(LEARNING_SEED_TASKS.filter(task => task.category_name === '输出')).toHaveLength(12)
    expect(LEARNING_SEED_TASKS.some(task => 'category_id' in task)).toBe(false)
  })
})
