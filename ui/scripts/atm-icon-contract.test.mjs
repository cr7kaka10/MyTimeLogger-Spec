import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expectedAtmIconEntries, expectedAtmIconNames, validateAtmIconSet, writeAndroidIconManifest } from './atm-icon-contract.mjs'

const root = resolve(import.meta.dirname, '..')
const names = expectedAtmIconNames()
const result = validateAtmIconSet(resolve(root, 'public', 'icons', 'atm'))
if (names.length !== new Set(names).size) throw new Error('ATM manifest contains duplicate paths')
if (result.expected !== 1130 || result.actual !== 1130) throw new Error(`Unexpected ATM contract: ${JSON.stringify(result)}`)
const target = resolve(root, 'public', 'atm-icon-android-manifest.json')
const first = writeAndroidIconManifest(target)
const before = readFileSync(target, 'utf8')
const second = writeAndroidIconManifest(target)
if (before !== readFileSync(target, 'utf8') || first.sha256 !== second.sha256) throw new Error('Android ATM manifest drifted')
const android = JSON.parse(before)
if (android.length !== expectedAtmIconEntries().length) throw new Error('Android/Web key count diverged')
for (const entry of android) {
  const premium = entry.key.startsWith('atm:flat_') || entry.key.startsWith('atm:swift_')
  if ((entry.group === 'premium') !== premium || !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new Error(`ATM group/hash mismatch: ${entry.key}`)
}
for (const file of ['CategoryIconResourceMap.java', 'TimerWidgetViewsFactory.java', 'TimerWidgetRenderer.java']) {
  const source = readFileSync(resolve(root, 'android', 'app', 'src', 'main', 'java', 'com', 'mytimelogger', 'app', file), 'utf8')
  if (source.includes('ic_timer_cat_') || source.includes('ic_timer_sp_')) throw new Error(`Independent pixel resource referenced: ${file}`)
}
console.log(`ATM icon manifest contract passed (${result.actual})`)
