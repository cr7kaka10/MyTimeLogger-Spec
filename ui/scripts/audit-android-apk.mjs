import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { expectedAtmIconNames, validateAtmIconSet } from './atm-icon-contract.mjs'

export const auditAndroidAssets = (entries, staging = resolve(import.meta.dirname, '..', 'dist', 'icons', 'atm')) => {
  const prefix = 'assets/public/icons/atm/'
  const expected = expectedAtmIconNames()
  const actual = entries.filter(name => name.startsWith(prefix) && name.endsWith('.png')).map(name => name.slice(prefix.length)).sort()
  validateAtmIconSet(staging)
  const actualSet = new Set(actual)
  const expectedSet = new Set(expected)
  const missing = expected.filter(name => !actualSet.has(name))
  const extra = actual.filter(name => !expectedSet.has(name))
  const blocked = entries.filter(name => /\.(?:db|wasm)$/i.test(name))
  if (missing.length || extra.length || blocked.length) throw new Error(`APK asset mismatch: missing=${missing.slice(0, 3)} extra=${extra.slice(0, 3)} blocked=${blocked}`)
  return { manifest: expected.length, staging: expected.length, apk: actual.length, blocked: blocked.length }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const apk = resolve(process.argv[2] || '')
  if (!existsSync(apk)) throw new Error(`APK is missing: ${apk}`)
  const jar = process.env.JAVA_HOME ? resolve(process.env.JAVA_HOME, 'bin', 'jar.exe') : 'jar'
  const listed = spawnSync(jar, ['tf', apk], { encoding: 'utf8' })
  if (listed.status !== 0) throw new Error(listed.stderr || 'jar tf failed')
  console.log(JSON.stringify(auditAndroidAssets(listed.stdout.split(/\r?\n/).filter(Boolean))))
}
