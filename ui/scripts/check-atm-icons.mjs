import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { validateAtmIconSet } from './atm-icon-contract.mjs'

const target = resolve(import.meta.dirname, '..', 'public', 'icons', 'atm')
if (!existsSync(target)) {
  throw new Error('Local ATM icon directory is missing. Run icons:import-atm first.')
}
const result = validateAtmIconSet(target)
console.log(`ATM icons valid and required for Android staging: Total=${result.actual}`)
