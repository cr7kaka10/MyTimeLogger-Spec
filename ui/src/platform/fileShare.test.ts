import { shareTextFile } from './fileShare'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const calls: string[] = []
const filesystem = {
  writeFile: async ({ path, directory }: any) => { calls.push(`write:${directory}:${path}`); return { uri: 'file://cache/config.json' } },
  deleteFile: async ({ path }: any) => { calls.push(`delete:${path}`) },
}
const share = { share: async ({ files }: any) => { calls.push(`share:${files[0]}`) } }
await shareTextFile('config.csv', '中文', { mimeType: 'text/csv;charset=utf-8', dialogTitle: '分享金币流水' }, 'capacitor-android', filesystem as any, share as any)
assert(calls.join(',') === 'write:CACHE:exports/config.csv,share:file://cache/config.json,delete:exports/config.csv', 'Android CSV sharing should use Cache and clean the temporary file')
calls.length = 0
try { await shareTextFile('failed.csv', 'x', {}, 'capacitor-android', filesystem as any, { share: async () => { throw new Error('cancelled') } } as any) } catch {}
assert(calls.includes('delete:exports/failed.csv'), 'temporary file should be removed when sharing fails')
calls.length = 0
try { await shareTextFile('write-failed.csv', 'x', {}, 'capacitor-android', { ...filesystem, writeFile: async () => { throw new Error('disk') } } as any, share as any) } catch {}
assert(calls.length === 0, 'a failed write must not share or delete an unsaved file')

const originalUrl = globalThis.URL
const originalDocument = globalThis.document
let blobType = ''; let revoked = ''; let clicked = false
;(globalThis as any).URL = { createObjectURL: (blob: Blob) => { blobType = blob.type; return 'blob:csv' }, revokeObjectURL: (url: string) => { revoked = url } }
;(globalThis as any).document = { body: { appendChild: () => {} }, createElement: () => ({ click: () => { clicked = true }, remove: () => {} }) }
await shareTextFile('ledger.csv', 'data', { mimeType: 'text/csv;charset=utf-8' }, 'web')
assert(clicked && revoked === 'blob:csv' && blobType === 'text/csv;charset=utf-8', 'desktop CSV must download and release its Blob URL')
;(globalThis as any).URL = originalUrl; (globalThis as any).document = originalDocument
console.log('platform file share tests passed')
