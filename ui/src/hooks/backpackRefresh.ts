import type { BackpackItem } from '../types'

export const BACKPACK_REFRESH_EVENTS = ['reward-catalog-updated', 'sync-pull-complete'] as const

export const normalizeBackpackItems = (items: BackpackItem[]): BackpackItem[] => items.map(item => ({
  ...item,
  description: typeof item.description === 'string' ? item.description : '',
  is_used: Boolean(item.is_used),
}))

export const preserveBackpackSnapshot = <T,>(previous: T): T => previous
