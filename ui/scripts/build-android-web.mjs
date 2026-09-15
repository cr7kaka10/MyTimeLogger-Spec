import { existsSync, readdirSync, rmSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { stageWebBuild } from './stage-web-build.mjs'
import { validateAtmIconSet } from './atm-icon-contract.mjs'

const root = resolve(import.meta.dirname, '..')
const temporary = resolve(tmpdir(), `mytimelogger-vite-${process.pid}`)
const dist = resolve(root, 'dist')
const removeTree = directory => rmSync(directory, { force: true, recursive: true, maxRetries: 5, retryDelay: 200 })
const run = (command, args) => {
  const executable = process.platform === 'win32' ? process.env.ComSpec || 'cmd.exe' : command
  const commandArgs = process.platform === 'win32' ? ['/d', '/s', '/c', `${command} ${args.join(' ')}`] : args
  const result = spawnSync(executable, commandArgs, { cwd: root, stdio: 'inherit' })
  if (result.status !== 0) process.exit(result.status || 1)
}
const hasDatabase = directory => readdirSync(directory, { withFileTypes: true }).some(entry => {
  const path = resolve(directory, entry.name)
  return entry.isDirectory() ? hasDatabase(path) : entry.name.toLowerCase().endsWith('.db')
})

removeTree(temporary)
run('npm', ['run', 'typecheck'])
run('npx', ['vite', 'build', '--outDir', temporary, '--emptyOutDir'])
stageWebBuild(temporary, dist)
validateAtmIconSet(resolve(dist, 'icons', 'atm'))
if (!existsSync(resolve(dist, 'index.html')) || hasDatabase(dist)) throw new Error('Android web preflight failed')
removeTree(temporary)
console.log('android web staging passed')
