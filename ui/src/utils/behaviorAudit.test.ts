import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const audit = readFileSync(fileURLToPath(new URL('./behaviorAudit.ts', import.meta.url)), 'utf8')
if (!audit.includes('const sensitive = /token|password|secret|cookie|authorization|content|text|note|body')) throw new Error('sensitive metadata filter is missing')
if (!audit.includes("['string', 'number', 'boolean'].includes(typeof item)")) throw new Error('metadata type whitelist is missing')
const app = readFileSync(fileURLToPath(new URL('../App.tsx', import.meta.url)), 'utf8')
if (!app.includes("const surface = dialog?.getAttribute('aria-label')?.includes('管理方案') ? 'management_plan' : activeTab")) throw new Error('control events must carry a stable surface')
console.log('behavior audit contract passed')
