import type { ExerciseItem, ExercisePlanDefinition, PlanDay } from '@models/ExercisePlanSampleDataInitializer'

export type CheckState = { status: number; completed_time?: string | null }
export const roundScore = (value: number) => Math.round(value * 100) / 100
export const formatScore = (value: number | null | undefined) => Number(roundScore(Number(value || 0)).toFixed(2)).toString()

const timing = (actual: string | undefined | null, target: string, max: number, lateFloor = false) => {
  if (!actual) return 0
  const minutes = (value: string) => {
    const [hour, minute] = value.split(':').map(Number)
    return hour * 60 + minute
  }
  const delta = minutes(actual) - minutes(target)
  return roundScore(delta <= 0 ? max : delta <= 15 ? max * .6 : delta <= 30 ? max * .3 : lateFloor ? max * .1 : 0)
}

export const itemWeight = (item: ExerciseItem) => {
  if (item.stairs) return 5
  if (item.s === '有氧') {
    const mins = parseInt(item.sets) || 0
    if (mins >= 25) return 5
    if (mins >= 20) return 4
    if (mins >= 15) return 3
    return 2
  }
  if (item.floor && item.core) return 2
  if (item.hang) return 2
  if (item.core) return 2
  if (item.s === '无氧') return 3
  return 2
}

export const exerciseItemPoints = (items: ExerciseItem[], pool: number) => {
  if (!items.length) return []
  const weights = items.map(itemWeight), sum = weights.reduce((a, b) => a + b, 0) || 1
  const raw = weights.map(weight => pool * weight / sum), points = raw.map(Math.floor)
  ;[...items.keys()].sort((a, b) => (raw[b] - points[b]) - (raw[a] - points[a]) || a - b)
    .slice(0, Math.max(0, pool - points.reduce((a, b) => a + b, 0))).forEach(index => { points[index]++ })
  return points
}

export function scheduleItemScore(day: PlanDay, date: string, index: number, state: CheckState | undefined, plan: ExercisePlanDefinition) {
  const rules = (day === '六' ? plan.saturdayScore : day === '日' ? plan.sundayScore : plan.weekdayScore).filter(rule => rule[0] === index && Number(rule[1]) > 0)
  const max = roundScore(rules.reduce((sum, rule) => sum + Number(rule[1]), 0))
  const earned = roundScore(rules.reduce((sum, [, points, , target]) => sum + (target ? timing(state?.completed_time, target, Number(points), plan.version === 'v2') : state?.status === 1 ? Number(points) : 0), 0))
  return { earned, max }
}

export function calcScore(
  day: PlanDay,
  date: string,
  rain: boolean,
  states: Record<string, CheckState>,
  planDefinition: ExercisePlanDefinition,
) {
  const cats: Record<string, { s: number; m: number }> = {}
  const add = (category: string, score: number, max: number) => {
    cats[category] ??= { s: 0, m: 0 }
    cats[category].s += score
    cats[category].m += max
  }
  let total = 0
  const cfg = day === '六' ? planDefinition.saturdayScore : day === '日' ? planDefinition.sundayScore : planDefinition.weekdayScore
  cfg.forEach(([index, points, category, target]) => {
    if (!points) return
    const state = states[`sc-${date}-${index}`]
    const earned = target ? timing(state?.completed_time, target, points, planDefinition.version === 'v2') : state?.status === 1 ? points : 0
    add(category, earned, points)
    total += earned
  })
  if (planDefinition.version === 'v4' || (day !== '六' && day !== '日')) {
    const items = planDefinition.exercisePlan[day]?.[rain ? 'rain' : 'gym'] || []
    let earned = 0
    if (items.length > 0) {
      const points = planDefinition.version === 'v4'
        ? items.map(item => Number(item.scorePoints || 0))
        : exerciseItemPoints(items, planDefinition.exercisePoints)
      items.forEach((_, index) => {
        if (states[`ex-${date}-${rain ? 'r' : 'g'}-${index}`]?.status === 1) {
          earned += points[index]
        }
      })
    }
    add(planDefinition.version === 'v4' ? '运动训练' : '运动', roundScore(earned), planDefinition.exercisePoints)
    total += earned
  }
  return { total: roundScore(total), cats, plan_version: planDefinition.version }
}
