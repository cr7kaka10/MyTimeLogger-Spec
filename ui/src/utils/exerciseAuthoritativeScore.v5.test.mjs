import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('./exerciseAuthoritativeScore.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText
const { projectAuthoritativeScore } = await import(`data:text/javascript,${encodeURIComponent(js)}`)

const future = projectAuthoritativeScore({
  plan_version: 'v5', total: 29,
  cats: { 运动训练: { s: 18, m: 49.99999999999999 }, 饮食约束: { s: 11, m: 50 }, 身体记录: { s: 0, m: 0 } },
}, 'v5')
assert.equal(future.total, 29, 'a server rounding tail must not erase earned points')
assert.deepEqual(Object.fromEntries(Object.entries(future.cats).map(([key, value]) => [key, value.m])),
  { 运动训练: 50, 饮食约束: 50, 身体记录: 0 })

const invalid = projectAuthoritativeScore({
  plan_version: 'v5', total: 29,
  cats: { 运动训练: { s: 18, m: 48 }, 饮食约束: { s: 11, m: 50 }, 身体记录: { s: 0, m: 0 } },
}, 'v5')
assert.equal(invalid.total, 0, 'materially wrong score maxima must still be rejected')

const historical = projectAuthoritativeScore({
  plan_version: 'v5', total: 10,
  cats: { 运动训练: { s: 0, m: 75 }, 饮食约束: { s: 5, m: 15 }, 身体记录: { s: 5, m: 10 } },
}, 'v5')
assert.equal(historical.total, 10)
assert.equal(historical.cats['饮食约束'].m, 15)

const rest = projectAuthoritativeScore({
  plan_version: 'v5', total: 0,
  cats: { 运动训练: { s: 0, m: 0 }, 饮食约束: { s: 0, m: 0 }, 身体记录: { s: 0, m: 0 } },
}, 'v5')
assert.deepEqual(Object.values(rest.cats).map(value => value.m), [0, 0, 0], 'new V5 rest day must not fall back to 75/15/10')
console.log('exercise V5 authoritative score tests passed')
