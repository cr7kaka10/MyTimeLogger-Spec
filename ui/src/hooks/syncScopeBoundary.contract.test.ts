import { readFileSync, readdirSync } from 'node:fs'
import { dirname, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
const srcRoot = dirname(dirname(fileURLToPath(import.meta.url)))
const walk = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
  const path = join(dir, entry.name)
  return entry.isDirectory() ? walk(path) : [path]
})
const production = walk(srcRoot).filter(path => ['.ts', '.tsx'].includes(extname(path)) && !path.includes('.test.'))
const sources = new Map(production.map(path => [path, readFileSync(path, 'utf8')]))
const checklistPath = join(srcRoot, 'hooks', 'useChecklist.ts')
const dbPath = join(srcRoot, 'db.ts')

for (const [path, source] of sources) {
  if (path !== dbPath) assert(!source.includes('pullSync(true)'), `${path} must not upgrade a server readback to provider sync`)
  if (path !== checklistPath && path !== dbPath) {
    assert(!source.includes('refreshTickTick'), `${path} must not expose the legacy provider refresh flag`)
    assert(!source.includes('syncChecklistNow'), `${path} must not call the checklist-only sync entry`)
  }
}
assert(sources.get(dbPath)?.includes('export async function syncChecklistNow'), 'db must expose an explicit checklist sync entry')
assert(sources.get(checklistPath)?.includes('syncChecklistNow'), 'only useChecklist may call the checklist sync entry')

console.log('sync scope boundary contract passed')
