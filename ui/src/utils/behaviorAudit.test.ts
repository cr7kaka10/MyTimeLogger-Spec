import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { BEHAVIOR_EVENT_FIELDS } from './behaviorEventCatalog'
import { normalizeSleepAutomationAudit } from '../platform/sleepAutomation'

const audit = readFileSync(fileURLToPath(new URL('./behaviorAudit.ts', import.meta.url)), 'utf8')
if (!audit.includes('const sensitive = /token|password|secret|cookie|authorization|content|text|note|body')) throw new Error('sensitive metadata filter is missing')
if (!audit.includes("['string', 'number', 'boolean'].includes(typeof item)")) throw new Error('metadata type whitelist is missing')
const app = readFileSync(fileURLToPath(new URL('../App.tsx', import.meta.url)), 'utf8')
if (!app.includes("const surface = dialog?.getAttribute('aria-label')?.includes('管理方案') ? 'management_plan' : activeTab")) throw new Error('control events must carry a stable surface')
const sleepFields = ['stage', 'result', 'reason', 'huaweiVersion', 'selectorType', 'attempt', 'durationMs']
if (JSON.stringify(BEHAVIOR_EVENT_FIELDS['sleep.automation.result']) !== JSON.stringify(sleepFields)) throw new Error('sleep automation catalog must use the exact safe field list')
const sleepAudit = normalizeSleepAutomationAudit({ stage: 'upload', result: 'failed', reason: 'https://secret/token', huaweiVersion: '17.0.8.300', selectorType: 'text', attempt: 2, durationMs: 800, token: 'secret', image: 'base64' })
if (Object.keys(sleepAudit).join(',') !== 'stage,result,huaweiVersion,selectorType,attempt,durationMs' || 'token' in sleepAudit || 'image' in sleepAudit) throw new Error('sleep automation audit must drop unsafe fields and values')
console.log('behavior audit contract passed')
