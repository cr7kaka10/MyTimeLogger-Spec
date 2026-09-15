export type V4Score = { total: number; cats: Record<string, { s: number; m: number }>; plan_version: 'v4' }

const limits = { 运动训练: 75, 饮食约束: 15, 身体记录: 10 }
const zero = (): V4Score => ({
  total: 0,
  cats: Object.fromEntries(Object.entries(limits).map(([name, maximum]) => [name, { s: 0, m: maximum }])),
  plan_version: 'v4',
})

export function projectV4Score(raw: unknown): V4Score {
  let value: any = raw
  if (typeof raw === 'string') try { value = JSON.parse(raw) } catch { return zero() }
  if (value?.plan_version !== 'v4' || !value?.cats) return zero()
  const entries = Object.entries(limits).map(([name, maximum]) => {
    const score = value.cats[name]
    const earned = Number(score?.s)
    return score && Number(score.m) === maximum && Number.isFinite(earned) && earned >= 0 && earned <= maximum
      ? [name, { s: earned, m: maximum }]
      : null
  })
  if (entries.some(entry => entry === null)) return zero()
  const cats = Object.fromEntries(entries as [string, { s: number; m: number }][])
  const total = Object.values(cats).reduce((sum, score) => sum + score.s, 0)
  return Number(value.total) === total ? { total, cats, plan_version: 'v4' } : zero()
}
