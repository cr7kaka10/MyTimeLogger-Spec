import type { MealWheelItem } from './config'

export function mealWheelLanding(items: MealWheelItem[], selectedId: string, rotation: number) {
  const total = items.reduce((sum, item) => sum + item.weight, 0)
  const index = items.findIndex(item => item.id === selectedId)
  if (index < 0 || total <= 0) throw new Error('转盘落点无效')
  const before = items.slice(0, index).reduce((sum, item) => sum + item.weight, 0)
  const midpoint = (before + items[index].weight / 2) / total * 360
  const target = (360 - midpoint) % 360
  return rotation + 2160 + (target - rotation % 360 + 360) % 360
}

export function mealWheelKeyframes(start: number, end: number): Keyframe[] {
  const distance = end - start
  return [
    { transform: `rotate(${start}deg)`, offset: 0, easing: 'cubic-bezier(.52,.02,.85,.42)' },
    { transform: `rotate(${start + distance * .12}deg)`, offset: .16, easing: 'linear' },
    { transform: `rotate(${start + distance * .76}deg)`, offset: .72, easing: 'cubic-bezier(.12,.6,.16,1)' },
    { transform: `rotate(${end}deg)`, offset: 1 },
  ]
}
