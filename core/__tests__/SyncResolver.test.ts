import { describe, it, expect } from 'vitest'
import { resolve, SyncAction } from '../core/SyncResolver'

describe('SyncResolver', () => {
  it('规则1: 仅服务端有 → PULL', () => {
    expect(resolve(null, { id: 1, updated_at: '2026-01-01' })).toBe(SyncAction.PULL)
  })

  it('规则2: 仅本地有且无 outbox → SKIP', () => {
    expect(resolve({ id: 1, updated_at: '2026-01-01' }, null)).toBe(SyncAction.SKIP)
  })

  it('规则3: pushed_at 为空但无 outbox → PULL', () => {
    expect(resolve(
      { id: 1, updated_at: '2026-01-01', pushed_at: null },
      { id: 1, updated_at: '2026-01-01' },
    )).toBe(SyncAction.PULL)
  })

  it('规则4: 服务端更新 → PULL', () => {
    expect(resolve(
      { id: 1, updated_at: '2026-01-01', pushed_at: '2026-01-01' },
      { id: 1, updated_at: '2026-06-01' },
    )).toBe(SyncAction.PULL)
  })

  it('规则5: 本地时间较新但无 outbox → PULL', () => {
    expect(resolve(
      { id: 1, updated_at: '2026-06-01', pushed_at: '2026-01-01' },
      { id: 1, updated_at: '2026-01-01' },
    )).toBe(SyncAction.PULL)
  })

  it('规则6: 收到服务端版本且无 outbox → PULL', () => {
    expect(resolve(
      { id: 1, updated_at: '2026-01-01', pushed_at: '2026-01-01' },
      { id: 1, updated_at: '2026-01-01' },
    )).toBe(SyncAction.PULL)
  })

  it('边界: 都为 null → SKIP', () => {
    expect(resolve(null, null)).toBe(SyncAction.SKIP)
  })

  it('边界: 空字符串 pushed_at 不影响 PULL', () => {
    expect(resolve(
      { id: 1, updated_at: '2026-01-01', pushed_at: '' },
      { id: 1, updated_at: '2026-01-01' },
    )).toBe(SyncAction.PULL)
  })

  it('存在持久化 outbox → PUSH', () => {
    expect(resolve(
      { id: 1, updated_at: '2026-06-01', pushed_at: null },
      { id: 1, updated_at: '2026-06-02' },
      true,
    )).toBe(SyncAction.PUSH)
  })
})
