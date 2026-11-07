// @ts-ignore Node's strip-types runner requires the explicit .ts extension.
import { projectAuthoritativeScore } from './exerciseAuthoritativeScore.ts'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const v6 = (earned: number, maximum: number) => ({
  total: earned, cats: { 运动训练: { s: earned, m: maximum } }, plan_version: 'v6',
})

assert(JSON.stringify(projectAuthoritativeScore(v6(0, 0), 'v6')) === JSON.stringify(v6(0, 0)), 'V6 Monday 0/0 must remain unchanged')
assert(JSON.stringify(projectAuthoritativeScore(v6(65, 100), 'v6')) === JSON.stringify(v6(65, 100)), 'V6 partial score must remain unchanged')
assert(JSON.stringify(projectAuthoritativeScore(v6(100, 100), 'v6')) === JSON.stringify(v6(100, 100)), 'V6 full score must remain unchanged')
assert(projectAuthoritativeScore(v6(101, 100), 'v6').total === 0, 'V6 over maximum must be rejected')
assert(projectAuthoritativeScore({ ...v6(50, 100), cats: { ...v6(50, 100).cats, 饮食约束: { s: 0, m: 0 } } }, 'v6').total === 0, 'V6 diet domain must be rejected')
assert(projectAuthoritativeScore({ ...v6(50, 100), total: 40 }, 'v6').total === 0, 'V6 inconsistent total must be rejected')

console.log('exercise V6 authoritative score contract passed')
