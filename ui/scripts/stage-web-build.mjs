import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs'
import { relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const walk = directory => readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
  const path = resolve(directory, entry.name)
  return entry.isDirectory() ? walk(path) : [path]
})

export const stageWebBuild = (source, target) => {
  rmSync(target, { force: true, recursive: true })
  mkdirSync(target, { recursive: true })
  for (const name of ['index.html', 'assets', 'icons/atm', 'atm-icon-android-manifest.json']) {
    const input = resolve(source, name)
    if (existsSync(input)) {
      mkdirSync(resolve(target, name, '..'), { recursive: true })
      cpSync(input, resolve(target, name), { recursive: true })
    }
  }
  const databases = walk(target).filter(file => file.toLowerCase().endsWith('.db'))
  if (databases.length) throw new Error(`database blocked from staging: ${databases.map(file => relative(target, file)).join(', ')}`)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  stageWebBuild(resolve(import.meta.dirname, '..', '.vite-tmp'), resolve(import.meta.dirname, '..', 'dist'))
}
