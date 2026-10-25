export type AuthoritativePlanVersion = 'v4' | 'v5'
export type AuthoritativeScore = { total: number; cats: Record<string, { s: number; m: number }>; plan_version: AuthoritativePlanVersion }

const legacyLimits = { 运动训练: 75, 饮食约束: 15, 身体记录: 10 }
const v5MealLimits = { 运动训练: 50, 饮食约束: 50, 身体记录: 0 }
export const isAuthoritativeExercisePlan = (version: string): version is AuthoritativePlanVersion => version === 'v4' || version === 'v5'
const zero = (planVersion: AuthoritativePlanVersion, currentV5Policy = false): AuthoritativeScore => ({
  total: 0, cats: Object.fromEntries(Object.entries(currentV5Policy ? v5MealLimits : legacyLimits).map(([name, maximum]) => [name, { s: 0, m: maximum }])), plan_version: planVersion,
})

export function projectAuthoritativeScore(raw: unknown, planVersion: AuthoritativePlanVersion): AuthoritativeScore {
  let value: any = raw
  if (typeof raw === 'string') try { value = JSON.parse(raw) } catch { return zero(planVersion) }
  const currentV5Policy = planVersion === 'v5' && Number(value?.cats?.['饮食约束']?.m) === 50
  if (value?.plan_version !== planVersion || !value?.cats) return zero(planVersion, currentV5Policy)
  const entries = Object.entries(currentV5Policy ? v5MealLimits : legacyLimits).map(([name, defaultMaximum]) => {
    const score = value.cats[name], earned = Number(score?.s), maximum = Number(score?.m)
    const validMaximum = name === '运动训练' ? maximum === 0 || maximum === defaultMaximum : maximum === defaultMaximum
    return score && validMaximum && Number.isFinite(earned) && earned >= 0 && earned <= maximum
      ? [name, { s: earned, m: maximum }] : null
  })
  if (entries.some(entry => entry === null)) return zero(planVersion, currentV5Policy)
  const cats = Object.fromEntries(entries as [string, { s: number; m: number }][]) as Record<string, { s: number; m: number }>
  const total = Object.values(cats).reduce((sum, score) => sum + score.s, 0)
  return Number(value.total) === total ? { total, cats, plan_version: planVersion } : zero(planVersion, currentV5Policy)
}
