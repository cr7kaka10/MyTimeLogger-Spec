export type AuthoritativePlanVersion = 'v4' | 'v5'
export type AuthoritativeScore = { total: number; cats: Record<string, { s: number; m: number }>; plan_version: AuthoritativePlanVersion }

const limits = { 运动训练: 75, 饮食约束: 15, 身体记录: 10 }
export const isAuthoritativeExercisePlan = (version: string): version is AuthoritativePlanVersion => version === 'v4' || version === 'v5'
const zero = (planVersion: AuthoritativePlanVersion): AuthoritativeScore => ({
  total: 0, cats: Object.fromEntries(Object.entries(limits).map(([name, maximum]) => [name, { s: 0, m: maximum }])), plan_version: planVersion,
})

export function projectAuthoritativeScore(raw: unknown, planVersion: AuthoritativePlanVersion): AuthoritativeScore {
  let value: any = raw
  if (typeof raw === 'string') try { value = JSON.parse(raw) } catch { return zero(planVersion) }
  if (value?.plan_version !== planVersion || !value?.cats) return zero(planVersion)
  const entries = Object.entries(limits).map(([name, defaultMaximum]) => {
    const score = value.cats[name], earned = Number(score?.s), maximum = Number(score?.m)
    const validMaximum = name === '运动训练' ? maximum === 0 || maximum === defaultMaximum : maximum === defaultMaximum
    return score && validMaximum && Number.isFinite(earned) && earned >= 0 && earned <= maximum
      ? [name, { s: earned, m: maximum }] : null
  })
  if (entries.some(entry => entry === null)) return zero(planVersion)
  const cats = Object.fromEntries(entries as [string, { s: number; m: number }][]) as Record<string, { s: number; m: number }>
  const total = Object.values(cats).reduce((sum, score) => sum + score.s, 0)
  return Number(value.total) === total ? { total, cats, plan_version: planVersion } : zero(planVersion)
}
