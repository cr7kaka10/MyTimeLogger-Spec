import { useEffect } from 'react'
import { useManagementPlanVersions } from '../../hooks/useManagementPlanVersions'
import type { ManagementPlanRuntime } from '../../hooks/useManagementPlan'

export function ManagementPlanHistory({ runtime, onSelect }: { runtime: ManagementPlanRuntime; onSelect?: (revision: any) => void }) {
  const versions = useManagementPlanVersions(runtime)
  useEffect(() => { void versions.load() }, [versions.load])
  return <section className="space-y-2" aria-label="管理方案版本历史">
    <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">方案版本</h3><button type="button" onClick={() => void versions.load()} className="rounded-lg border px-2 py-1 text-xs">刷新</button></div>
    {versions.error && <p className="rounded-lg bg-red-50 p-2 text-xs text-red-700">{versions.error}</p>}
    {versions.revisions.length === 0 ? <p className="text-xs text-gray-500">还没有已发布版本。草案请在首页 AI 管理方案窗口中审阅，确认应用后才会出现在这里。</p> : versions.revisions.map(revision => <button type="button" key={revision.id} onClick={() => onSelect?.(revision)} className="flex w-full items-center justify-between rounded-xl border p-3 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"><span><strong>{revision.version}</strong><span className="ml-2 text-xs text-gray-500">{revision.revision_kind}</span></span><span className="font-mono text-[10px] text-gray-400">{String(revision.manifest_digest).slice(0, 8)}</span></button>)}
  </section>
}
