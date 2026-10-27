import type { ChecklistItem } from '../types'

export const parseChecklistItems = (value: unknown): ChecklistItem[] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item && typeof item === 'object' &&
      typeof item.id === 'string' && item.id.length > 0 &&
      typeof item.title === 'string' && Number.isInteger(item.status))
    .sort((a, b) => (Number.isFinite(a.item.sortOrder) ? a.item.sortOrder : a.index) -
      (Number.isFinite(b.item.sortOrder) ? b.item.sortOrder : b.index) || a.index - b.index)
    .map(({ item, index }) => ({
      id: item.id, title: item.title, status: item.status,
      sortOrder: Number.isFinite(item.sortOrder) ? item.sortOrder : index,
    }))
}
