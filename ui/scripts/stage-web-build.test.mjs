import { createHash } from 'node:crypto'
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { stageWebBuild } from './stage-web-build.mjs'

const root = mkdtempSync(resolve(tmpdir(), 'mtl-stage-'))
const source = resolve(root, 'source')
const target = resolve(root, 'dist')
mkdirSync(resolve(source, 'assets'), { recursive: true })
mkdirSync(resolve(source, 'icons', 'atm'), { recursive: true })
writeFileSync(resolve(source, 'index.html'), '<main />')
writeFileSync(resolve(source, 'assets', 'app.js'), 'ok')
writeFileSync(resolve(source, 'icons', 'atm', 'cat_1.png'), 'png')
writeFileSync(resolve(source, 'atm-icon-android-manifest.json'), '[]')
const database = resolve(source, 'my_time_logger.db')
writeFileSync(database, 'private')
const before = createHash('sha256').update(readFileSync(database)).digest('hex')
stageWebBuild(source, target)
if (!existsSync(resolve(target, 'assets', 'app.js')) || !existsSync(resolve(target, 'icons', 'atm', 'cat_1.png'))
    || !existsSync(resolve(target, 'atm-icon-android-manifest.json')) || existsSync(resolve(target, 'my_time_logger.db'))) throw new Error('allowlist staging failed')
const after = createHash('sha256').update(readFileSync(database)).digest('hex')
if (before !== after) throw new Error('source database changed')
writeFileSync(resolve(source, 'assets', 'unsafe.db'), 'blocked')
let blocked = false
try { stageWebBuild(source, target) } catch { blocked = true }
rmSync(root, { force: true, recursive: true })
if (!blocked) throw new Error('database in staging was not blocked')
console.log('web staging fixtures passed')
