import { readdirSync, readFileSync } from 'node:fs'
import { extname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const binaryAssets = new Set(['.gif', '.ico', '.jpeg', '.jpg', '.mp3', '.png', '.svg', '.webp'])

export const classifyReleaseAsset = (source, content = '') => {
  const normalized = source.replaceAll('\\', '/').toLowerCase()
  const text = Buffer.isBuffer(content) ? content.toString('utf8') : content
  if (normalized.endsWith('.db')) return 'database'
  if (normalized.endsWith('.wasm')) return 'deprecated-wasm'
  if (/(^|\/)icons\/atm\/[^/]+\.png$/.test(normalized)) return 'required-atm-icon'
  if (/(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]+/i.test(text)) return 'secret-pattern'
  if (/usescleartexttraffic\s*=\s*['\"]true|http:\/\//i.test(text)) return 'debug-cleartext'
  if (binaryAssets.has(extname(normalized))) return 'license-unknown'
  return 'allowed'
}

const walk = directory => readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
  const path = resolve(directory, entry.name)
  return entry.isDirectory() ? walk(path) : [path]
})

if (resolve(process.argv[1] || '') === fileURLToPath(import.meta.url)) {
  const root = resolve(import.meta.dirname, '..', 'public')
  for (const file of walk(root)) {
    const source = relative(resolve(import.meta.dirname, '..'), file)
    console.log(`${classifyReleaseAsset(source, readFileSync(file))}\t${source}`)
  }
}
