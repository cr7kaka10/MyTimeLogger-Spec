import { validateMealWheelItems, type MealWheelItem } from './config'

const UINT32_RANGE = 0x1_0000_0000

/** 拒绝模数尾部，避免整数映射偏向前几项。 */
export function pickMealWheelItem(
  items: MealWheelItem[], nextUint32: () => number = () => crypto.getRandomValues(new Uint32Array(1))[0],
): MealWheelItem {
  const error = validateMealWheelItems(items)
  if (error) throw new Error(error)
  const total = items.reduce((sum, item) => sum + item.weight, 0)
  const limit = Math.floor(UINT32_RANGE / total) * total
  let value: number
  do { value = nextUint32() } while (value >= limit)
  let ticket = value % total
  for (const item of items) {
    if (ticket < item.weight) return item
    ticket -= item.weight
  }
  throw new Error('转盘抽取失败')
}
