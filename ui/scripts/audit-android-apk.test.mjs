import { resolve } from 'node:path'
import { auditAndroidAssets } from './audit-android-apk.mjs'
import { expectedAtmIconNames } from './atm-icon-contract.mjs'

const entries = expectedAtmIconNames().map(name => `assets/public/icons/atm/${name}`)
const result = auditAndroidAssets(entries, resolve(import.meta.dirname, '..', 'public', 'icons', 'atm'))
if (result.manifest !== 1130 || result.apk !== 1130 || result.blocked !== 0) throw new Error(JSON.stringify(result))
console.log('Android APK ATM asset contract passed')
