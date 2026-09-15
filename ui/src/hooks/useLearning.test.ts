import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./useLearning.ts', import.meta.url)), 'utf8')

test('learning mutations use the authenticated server command and never local SQL writes', () => {
  if (!source.includes('/api/learning/plans')) throw new Error('learning hook must call the server command endpoint')
  if (!source.includes("action: 'create_objective'") || !source.includes("action: 'toggle_task'") || !source.includes("action: 'set_task_status'")) throw new Error('learning CRUD commands are incomplete')
  if (/\.runRaw\(|enqueueSync\(|createOutboxOperation\(/.test(source)) throw new Error('learning hook must not write learning tables directly')
})

test('learning command success pulls before refreshing the local read cache', () => {
  if (!/await pullSync\(\)[\s\S]*setRefreshTrigger/.test(source)) throw new Error('learning writes must converge through pull before reload')
})

test('KR display order uses its numeric prefix and a stable fallback', () => {
  if (!source.includes('sortLearningKrs(krs.filter')) throw new Error('learning objective assembly must sort KRs on every platform')
  if (!/^export function sortLearningKrs[\s\S]*KR\\s\*\(\\d\+\)/m.test(source)) throw new Error('KR numeric prefix must drive the natural order')
  if (!/left\.created_at\.localeCompare\(right\.created_at\) \|\| left\.id\.localeCompare\(right\.id\)/.test(source)) throw new Error('un-numbered KRs need a cross-platform stable fallback')
})
