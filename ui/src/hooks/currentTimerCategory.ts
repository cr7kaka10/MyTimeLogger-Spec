import type { Category } from '../types'

export const resolveCurrentTimerCategory = (
  categories: Category[],
  categoryId: number | string | null | undefined,
  categoryName?: string | null,
): Category | null => {
  const id = Number(categoryId)
  const byId = Number.isFinite(id) ? categories.find(category => Number(category.id) === id) : null
  if (byId) return byId
  const name = String(categoryName || '').trim()
  const byUniqueName = name ? categories.filter(category => String(category.name || '').trim() === name) : []
  if (byUniqueName.length === 1) return byUniqueName[0]
  if (!Number.isFinite(id)) return null
  return {
    id,
    name: categoryName || '未知分类',
    icon: '',
    color: '',
    group_name: '',
    sort_order: 0,
  }
}
