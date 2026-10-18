import { describe, expect, it } from 'vitest'
import { canHandoffFocusCategory, focusCategoryPolicy, focusGroupFor, resolveFocusCommandPolicy, sameFocusGroup } from '../core/FocusCategoryPolicy'

describe('FocusCategoryPolicy', () => {
  it('defines the three structured focus groups and ordinary count-up categories', () => {
    expect(focusGroupFor(' 输入 ')).toBe('input-output')
    expect(focusGroupFor('副业研发')).toBe('side-business')
    expect(focusGroupFor('工作')).toBe('work')
    expect(focusCategoryPolicy('娱乐')).toEqual({ group: null, timerMode: 'countup', structured: false, allowedTargets: [] })
    expect(focusCategoryPolicy('副业营销')).toMatchObject({ timerMode: 'countdown', structured: true })
  })

  it('allows only a different member of the active group while actively studying', () => {
    expect(sameFocusGroup('输入', '输出')).toBe(true)
    expect(sameFocusGroup('副业生产', '副业研发')).toBe(true)
    expect(sameFocusGroup('工作', '工作')).toBe(true)
    expect(sameFocusGroup('工作', '输出')).toBe(false)
    expect(canHandoffFocusCategory('studying', false, '输入', '输出')).toBe(true)
    expect(canHandoffFocusCategory('studying', true, '输入', '输出')).toBe(false)
    expect(canHandoffFocusCategory('short_breaking', false, '输入', '输出')).toBe(false)
    expect(canHandoffFocusCategory('long_break_finished', false, '输入', '输出')).toBe(false)
    expect(canHandoffFocusCategory('studying', false, '工作', '工作')).toBe(false)
  })

  it('can roll back extended groups without disabling input/output', () => {
    ;(globalThis as any).__MTL_EXTENDED_FOCUS_GROUPS__ = false
    expect(focusGroupFor('副业研发')).toBeNull()
    expect(focusGroupFor('工作')).toBeNull()
    expect(focusGroupFor('输入')).toBe('input-output')
    delete (globalThis as any).__MTL_EXTENDED_FOCUS_GROUPS__
  })

  it('builds one launch policy for every source', () => {
    for (const name of ['输入', '输出', '工作', '副业生产', '副业研发', '副业营销']) {
      expect(resolveFocusCommandPolicy(name, 1800)).toEqual({ timerMode: 'countdown', durationMs: 1_800_000 })
    }
    expect(resolveFocusCommandPolicy('娱乐', 1800)).toEqual({ timerMode: 'countup', durationMs: 0 })
  })
})
