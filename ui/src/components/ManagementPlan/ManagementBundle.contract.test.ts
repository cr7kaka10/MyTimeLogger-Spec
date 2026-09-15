import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8')
const mindmap = read('./ManagementPlanMindmap.tsx')
const modal = read('./ManagementBundleImportModal.tsx')
const hook = read('../../hooks/useManagementBundle.ts')

// Hook Assertions
assert(hook.includes('/api/v1/management-plan/export'), 'useManagementBundle must have export endpoint')
assert(hook.includes('/api/v1/management-plan/import/preview'), 'useManagementBundle must have preview endpoint')
assert(hook.includes('/api/v1/management-plan/import/apply'), 'useManagementBundle must have apply endpoint')
assert(hook.includes('text()'), 'exportBundle must process response as text')
assert(hook.includes('new Blob([textData]'), 'exportBundle must convert text to Blob on web')
assert(hook.includes('import { Capacitor }'), 'Hook must import Capacitor core')
assert(hook.includes('import { Filesystem'), 'Hook must import Filesystem plugin')
assert(hook.includes('import { Share }'), 'Hook must import Share plugin')
assert(hook.includes('Capacitor.isNativePlatform()'), 'Hook must sniff native platform')
assert(hook.includes('Filesystem.writeFile'), 'Hook must use Filesystem to persist on native')
assert(hook.includes('Share.share'), 'Hook must use Share to broadcast on native')
assert(hook.includes("a.download = fileName"), 'exportBundle must fallback to trigger file download on web')

// Mindmap Component Assertions
assert(mindmap.includes('导出 JSON'), 'Mindmap must contain export button')
assert(mindmap.includes('导入 JSON'), 'Mindmap must contain import button')
assert(mindmap.includes('exportBundle()'), 'Mindmap must call exportBundle hook')
assert(mindmap.includes('type="file"'), 'Mindmap must contain hidden file input for import')
assert(mindmap.includes('ManagementBundleImportModal'), 'Mindmap must render the import modal')
assert(mindmap.includes('当前为只读导图'), 'Mindmap must state that editing is unavailable')
assert(mindmap.includes('完整导图编辑器尚未开放'), 'Mindmap must not claim the full editor is complete')

// Modal Component Assertions
assert(modal.includes('previewBundle({ bundle, mode })'), 'Modal must call previewBundle on mount/mode change')
assert(modal.includes('mode === \'merge\''), 'Modal must support merge mode')
assert(modal.includes('mode === \'synchronize\''), 'Modal must support synchronize mode')
assert(modal.includes('applyBundle({ bundle, mode, idempotency_key: idempotencyKey })'), 'Modal must apply bundle with idempotency key')
assert(modal.includes('added = preview?.nodes?.filter'), 'Modal must count added nodes')
assert(modal.includes('updated = preview?.nodes?.filter'), 'Modal must count updated nodes')
assert(modal.includes('archived = preview?.nodes?.filter'), 'Modal must count archived nodes')
assert(modal.includes('⚠️ 警告：'), 'Modal must display warning for unresolved relations')
assert(modal.includes('当前仅支持分类、任务、习惯和学习目标'), 'Modal must disclose the supported apply domains')
assert(modal.includes('整次导入会被拒绝，不会部分写入'), 'Modal must disclose atomic rejection for unsupported changes')

console.log('ManagementBundle contracts passed')
