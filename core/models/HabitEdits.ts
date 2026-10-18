export type HabitEdits = {
  name?: string; title?: string; icon?: string; color?: string
  category_id?: number | null; sort_order?: number; repeat_rule?: string | null
}

export function normalizeHabitEdits(fields: HabitEdits): Record<string, unknown> {
  const allowed = new Set(['name', 'title', 'icon', 'color', 'category_id', 'sort_order', 'repeat_rule'])
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(fields)) {
    if (!allowed.has(key)) throw new Error('不可修改习惯的来源或系统字段')
    if (value === undefined) continue
    if (key === 'name' || key === 'title') {
      if (typeof value !== 'string' || !value.trim()) throw new Error('习惯名称不能为空')
      if (result.name !== undefined && result.name !== value.trim()) throw new Error('习惯名称字段冲突')
      result.name = value.trim()
    } else if (key === 'sort_order' || key === 'category_id') {
      if (!(key === 'category_id' && value === null) && !Number.isSafeInteger(value)) throw new Error('分类和排序必须是整数')
      result[key] = value
    } else {
      if (!(key === 'repeat_rule' && value === null) && typeof value !== 'string') throw new Error('习惯字段格式无效')
      result[key] = value
    }
  }
  return result
}

export function assertLocalHabitEditable(row: any, expected?: string): void {
  if (!row) throw new Error('习惯不存在')
  if (row.source !== 'local') throw new Error('滴答镜像请在滴答清单中修改')
  if (row.is_active !== 0) throw new Error('习惯已删除，不能修改')
  if (expected !== undefined && row.updated_at !== expected) throw new Error('习惯已更新，请重新打开后修改')
}
