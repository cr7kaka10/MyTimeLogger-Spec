import { projectV4Score } from './exerciseV4Score'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const dates = ['2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11', '2026-09-12', '2026-09-13']
const names = ['运动训练', '饮食约束', '身体记录']

for (const date of dates) {
  const score = projectV4Score(null)
  assert(score.total === 0 && names.every((name, index) => score.cats[name].m === [75, 15, 10][index]), `${date} must use the V4 zero baseline`)
}

const authoritative = projectV4Score({
  plan_version: 'v4', total: 19,
  cats: { 运动训练: { s: 9, m: 75 }, 饮食约束: { s: 5, m: 15 }, 身体记录: { s: 5, m: 10 } },
})
assert(authoritative.total === 19 && Object.keys(authoritative.cats).join(',') === names.join(','), 'valid V4 settlement must retain exactly three domains')
assert(projectV4Score({ plan_version: 'v2', cats: { 守时: { s: 5, m: 5 } } }).total === 0, 'old snapshots must not be projected as V4')

console.log('exercise V4 score projection contracts passed')
