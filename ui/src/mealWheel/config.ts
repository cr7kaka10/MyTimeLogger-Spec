export const MEAL_WHEEL_KEY = 'meal_wheel_v1'
export type MealWheelItem = { id: string; name: string; weight: number }
export type MealWheelConfig = { schemaVersion: 1; revision: string; updatedAt: string; items: MealWheelItem[] }

const names = ['家常菜', '面条', '米饭套餐', '饺子', '火锅', '轻食']
export const defaultMealWheel = (): MealWheelConfig => ({
  schemaVersion: 1, revision: '', updatedAt: '',
  items: names.map((name, index) => ({ id: `default-${index}`, name, weight: 1 })),
})

export function validateMealWheelItems(items: MealWheelItem[]): string | null {
  if (items.length < 2 || items.length > 12) return '请设置 2–12 个餐食选项'
  const seen = new Set<string>()
  for (const item of items) {
    if (!item || typeof item.id !== 'string' || typeof item.name !== 'string') return '餐食配置格式无效'
    const name = item.name.trim()
    if (!name || Array.from(name).length > 20) return '餐食名称需为 1–20 个字'
    if (seen.has(name.toLocaleLowerCase())) return '餐食名称不能重复'
    if (!Number.isInteger(item.weight) || item.weight < 1 || item.weight > 100) return '权重需为 1–100 的整数'
    if (!item.id) return '餐食标识不能为空'
    seen.add(name.toLocaleLowerCase())
  }
  return null
}

export function parseMealWheel(raw: string | null): MealWheelConfig {
  if (!raw) return defaultMealWheel()
  try {
    const value = JSON.parse(raw) as MealWheelConfig
    if (value.schemaVersion !== 1 || typeof value.revision !== 'string' || typeof value.updatedAt !== 'string' ||
      !Array.isArray(value.items) || validateMealWheelItems(value.items)) return defaultMealWheel()
    if (new Set(value.items.map(item => item.id)).size !== value.items.length) return defaultMealWheel()
    return value
  } catch { return defaultMealWheel() }
}

export function mealWheelProbabilities(items: MealWheelItem[]): number[] {
  const total = items.reduce((sum, item) => sum + item.weight, 0)
  return items.map(item => item.weight / total)
}

export function mealWheelDisplayPercentages(items: MealWheelItem[]): number[] {
  const exact = mealWheelProbabilities(items).map(value => value * 1000)
  const tenths = exact.map(Math.floor)
  const order = exact.map((value, index) => ({ index, remainder: value - tenths[index] }))
    .sort((a, b) => b.remainder - a.remainder || a.index - b.index)
  const missing = 1000 - tenths.reduce((sum, value) => sum + value, 0)
  for (let index = 0; index < missing; index++) tenths[order[index].index]++
  return tenths.map(value => value / 10)
}
