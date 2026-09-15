import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const defaultManifest = resolve(root, 'src', 'assets', 'atmIconManifest.ts')
export const expectedAtmIconEntries = (manifestPath = defaultManifest) => {
  const source = readFileSync(manifestPath, 'utf8')
  return [...source.matchAll(/\{ name: '([^']+)', group: '(free|premium)' \}/g)]
    .map(match => ({ name: match[1], group: match[2] })).sort((a, b) => a.name.localeCompare(b.name))
}
export const expectedAtmIconNames = manifestPath => expectedAtmIconEntries(manifestPath).map(item => `${item.name}.png`)
const sha256 = value => createHash('sha256').update(value).digest('hex')

export const buildAndroidIconManifest = (directory = resolve(root, 'public', 'icons', 'atm'), manifestPath) =>
  expectedAtmIconEntries(manifestPath).map(item => {
    const file = resolve(directory, `${item.name}.png`)
    if (!existsSync(file)) throw new Error(`Missing PNG for atm:${item.name}`)
    return { key: `atm:${item.name}`, group: item.group, path: `icons/atm/${item.name}.png`, sha256: sha256(readFileSync(file)) }
  })

export const writeAndroidIconManifest = (target = resolve(root, 'public', 'atm-icon-android-manifest.json')) => {
  const output = `${JSON.stringify(buildAndroidIconManifest(), null, 2)}\n`
  if (!existsSync(target) || readFileSync(target, 'utf8') !== output) writeFileSync(target, output)
  return { target, count: JSON.parse(output).length, sha256: sha256(output) }
}

export const validateAtmIconSet = (directory, manifestPath) => {
  if (!existsSync(directory)) throw new Error(`ATM icon directory is missing: ${directory}`)
  const expected = expectedAtmIconNames(manifestPath)
  const actual = readdirSync(directory).filter(name => name.endsWith('.png')).sort()
  const expectedSet = new Set(expected)
  const actualSet = new Set(actual)
  const missing = expected.filter(name => !actualSet.has(name))
  const extra = actual.filter(name => !expectedSet.has(name))
  if (missing.length || extra.length || expected.length !== 1130) {
    throw new Error(`ATM icon set mismatch: expected=${expected.length} actual=${actual.length} missing=${missing.slice(0, 3)} extra=${extra.slice(0, 3)}`)
  }
  for (const file of actual) {
    if (readFileSync(resolve(directory, file)).subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') throw new Error(`Invalid PNG: ${file}`)
  }
  return { expected: expected.length, actual: actual.length }
}

if (process.argv[1]?.replaceAll('\\', '/').endsWith('/atm-icon-contract.mjs'))
  console.log(`Android ATM manifest generated: ${JSON.stringify(writeAndroidIconManifest())}`)
