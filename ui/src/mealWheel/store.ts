import { getDatabase, syncNow } from '../db'
import { formatBeijingDateTime } from '@core/BeijingTime'
import { MEAL_WHEEL_KEY, parseMealWheel, validateMealWheelItems, type MealWheelConfig, type MealWheelItem } from './config'

export async function loadMealWheel(): Promise<MealWheelConfig> {
  const db = await getDatabase()
  return parseMealWheel(db.getConfig(MEAL_WHEEL_KEY))
}

export async function saveMealWheel(items: MealWheelItem[], expectedRevision: string, overwrite = false):
  Promise<{ ok: true; config: MealWheelConfig } | { ok: false; reason: string; conflict: boolean }> {
  const error = validateMealWheelItems(items)
  if (error) return { ok: false, reason: error, conflict: false }
  const db = await getDatabase()
  const current = parseMealWheel(db.getConfig(MEAL_WHEEL_KEY))
  if (!overwrite && current.revision !== expectedRevision) {
    return { ok: false, reason: '其他设备已更新转盘，请重新载入或确认覆盖', conflict: true }
  }
  const config: MealWheelConfig = {
    schemaVersion: 1, revision: crypto.randomUUID(), updatedAt: formatBeijingDateTime(),
    items: items.map(item => ({ id: item.id, name: item.name.trim(), weight: item.weight })),
  }
  db.setConfig(MEAL_WHEEL_KEY, JSON.stringify(config), '选餐转盘配置')
  window.dispatchEvent(new Event('mtl:meal-wheel-changed'))
  void syncNow({ reason: 'meal-wheel-save' }).catch(() => {})
  return { ok: true, config }
}
