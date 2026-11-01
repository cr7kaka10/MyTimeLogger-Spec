export type AuthoritativePlanVersion = 'v4' | 'v5'
export type AuthoritativeScore = { total: number; cats: Record<string, { s: number; m: number }>; plan_version: AuthoritativePlanVersion }

const legacyLimits = { 运动训练: 75, 饮食约束: 15, 身体记录: 10 }
const v5MealLimits = { 运动训练: 50, 饮食约束: 50, 身体记录: 0 }
const v5ExerciseLimits = { 运动训练: 50, 饮食约束: 0, 身体记录: 0 }
const v5RestLimits = { 运动训练: 0, 饮食约束: 0, 身体记录: 0 }
const samePoints = (left: number, right: number) => Math.abs(left - right) < 1e-6
export const isAuthoritativeExercisePlan = (version: string): version is AuthoritativePlanVersion => version === 'v4' || version === 'v5'
export const currentV5PlanScore = (): AuthoritativeScore => zero('v5', true)
export const isCurrentV5Score = (score: AuthoritativeScore): boolean =>
  score.plan_version === 'v5' && score.cats['运动训练']?.m === 50 && [0, 50].includes(Number(score.cats['饮食约束']?.m)) && score.cats['身体记录']?.m === 0
const zero = (planVersion: AuthoritativePlanVersion, currentV5Policy = false, currentV5Rest = false, exerciseOnly = false): AuthoritativeScore => ({
  total: 0, cats: Object.fromEntries(Object.entries(currentV5Rest ? v5RestLimits : exerciseOnly ? v5ExerciseLimits : currentV5Policy ? v5MealLimits : legacyLimits).map(([name, maximum]) => [name, { s: 0, m: maximum }])), plan_version: planVersion,
})

export function projectAuthoritativeScore(raw: unknown, planVersion: AuthoritativePlanVersion): AuthoritativeScore {
  let value: any = raw
  if (typeof raw === 'string') try { value = JSON.parse(raw) } catch { return zero(planVersion) }
  const currentV5Policy = planVersion === 'v5' && Number(value?.cats?.['饮食约束']?.m) === 50
  const currentV5Rest = planVersion === 'v5' && Object.keys(v5RestLimits).every(name => Number(value?.cats?.[name]?.m) === 0)
  const exerciseOnly = planVersion === 'v5' && Number(value?.cats?.['运动训练']?.m) === 50 && Number(value?.cats?.['饮食约束']?.m) === 0 && Number(value?.cats?.['身体记录']?.m) === 0
  if (value?.plan_version !== planVersion || !value?.cats) return zero(planVersion, currentV5Policy, currentV5Rest, exerciseOnly)
  const limits = currentV5Rest ? v5RestLimits : exerciseOnly ? v5ExerciseLimits : currentV5Policy ? v5MealLimits : legacyLimits
  const entries = Object.entries(limits).map(([name, defaultMaximum]) => {
    const score = value.cats[name], earned = Number(score?.s), maximum = Number(score?.m)
    const validMaximum = name === '运动训练' ? maximum === 0 || samePoints(maximum, defaultMaximum) : samePoints(maximum, defaultMaximum)
    return score && validMaximum && Number.isFinite(earned) && earned >= 0 && earned <= maximum + 1e-6
      ? [name, { s: earned, m: maximum === 0 ? 0 : defaultMaximum }] : null
  })
  if (entries.some(entry => entry === null)) return zero(planVersion, currentV5Policy, currentV5Rest, exerciseOnly)
  const cats = Object.fromEntries(entries as [string, { s: number; m: number }][]) as Record<string, { s: number; m: number }>
  const total = Object.values(cats).reduce((sum, score) => sum + score.s, 0)
  return samePoints(Number(value.total), total) ? { total: Number(value.total), cats, plan_version: planVersion } : zero(planVersion, currentV5Policy, currentV5Rest, exerciseOnly)
}

export function projectV5ScoreView(raw: unknown) {
  const actual = projectAuthoritativeScore(raw, 'v5')
  const current = raw != null && isCurrentV5Score(actual)
  return {
    current,
    planScore: current ? actual : currentV5PlanScore(),
    historicalScore: raw != null && !current && actual.cats['饮食约束'].m === 15 ? actual : null,
  }
}
