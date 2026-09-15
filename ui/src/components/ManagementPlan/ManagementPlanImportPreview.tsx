import { useState } from 'react'
import { useManagementPlanVersions } from '../../hooks/useManagementPlanVersions'
import type { ManagementPlanRuntime } from '../../hooks/useManagementPlan'

export function ManagementPlanImportPreview({ runtime }: { runtime: ManagementPlanRuntime }) {
  const versions = useManagementPlanVersions(runtime)
  const [text, setText] = useState('')
  const [preview, setPreview] = useState<any>(null)
  const inspect = async () => { try { setPreview(await versions.importPreview(JSON.parse(text))) } catch (cause: any) { setPreview({ error: String(cause?.message || '导入文件无效') }) } }
  return <section className="space-y-2" aria-label="管理方案导入预检"><h3 className="text-sm font-semibold">导入预检</h3><textarea value={text} onChange={event => setText(event.target.value)} rows={4} placeholder="粘贴 JSON manifest" className="w-full rounded-xl border bg-transparent p-3 text-xs" /><button type="button" disabled={!text.trim()} onClick={() => void inspect()} className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">检查导入</button>{preview?.error && <p className="rounded-lg bg-red-50 p-2 text-xs text-red-700">{preview.error}</p>}{preview?.changes && <div className="space-y-1 text-xs">{preview.changes.map((change: any) => <div key={change.logical_key} className="flex justify-between rounded-lg border p-2"><span className="truncate">{change.logical_key}</span><strong>{change.change_type}</strong></div>)}</div>}</section>
}
