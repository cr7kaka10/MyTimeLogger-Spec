import { memo, useEffect, useMemo, useState } from 'react'
import type { BackpackEvent, BackpackFragment, BackpackItem } from '../../types'
import type { UseBackpackReturn } from '../../hooks/useBackpack'

export const backpackFilters = [['available', '可使用'], ['used', '已使用']] as const
const eventLabels: Record<BackpackEvent['event_type'], string> = { acquired: '获得', used: '使用', discarded: '丢弃', revoked: '撤销', fragment_acquired: '获得碎片', fragment_expired: '碎片过期', fragment_revoked: '碎片撤销', fragment_composed: '自动合成' }
export type BackpackFilter = typeof backpackFilters[number][0]
export const DEFAULT_BACKPACK_FILTER: BackpackFilter = 'available'
export const BACKPACK_MINIMUM_SLOTS = 14
export const canUseBackpackItem = (item: BackpackItem) => !item.is_used
export const getBackpackItemDescription = (item: BackpackItem) => item.description || '暂无物品说明'
export const formatBackpackEvent = (event: BackpackEvent) => `[${event.created_at}]${eventLabels[event.event_type]}${event.item_title || '已下架奖励'}*${event.quantity ?? 1}${event.detail ? `（${event.detail}）` : ''}`
export const groupBackpackItems = (items: BackpackItem[], filter: BackpackFilter) => {
  const filtered = items.filter(item => filter === 'available' ? !item.is_used : item.is_used)
  return [...new Map(filtered.map(item => [`${item.title}\u0000${item.icon}\u0000${item.is_used}`, { item, quantity: 0 }])).values()].map(group => ({ ...group, quantity: filtered.filter(item => item.title === group.item.title && item.icon === group.item.icon && item.is_used === group.item.is_used).length }))
}

export const BackpackPage = memo(({ items, fragments, events, isLoading, hasMoreEvents, isLoadingMoreEvents, useItem, loadMoreEvents }: UseBackpackReturn) => {
  const [filter, setFilter] = useState<BackpackFilter>(DEFAULT_BACKPACK_FILTER)
  const [selectedId, setSelectedId] = useState<string | number | null>(null)
  const [error, setError] = useState('')
  const visible = useMemo(() => groupBackpackItems(items, filter), [items, filter])
  const visibleFragments = filter === 'available' ? fragments : []
  useEffect(() => { if (![...visible.map(group => group.item.id), ...visibleFragments.map(fragment => fragment.id)].includes(selectedId ?? '')) setSelectedId(visible.find(group => !group.item.is_used)?.item.id ?? visibleFragments[0]?.id ?? visible[0]?.item.id ?? null) }, [visible, visibleFragments, selectedId])
  const selected = items.find(item => item.id === selectedId) as BackpackItem | undefined
  const selectedFragment = fragments.find(fragment => fragment.id === selectedId) as BackpackFragment | undefined
  const run = async (action: () => Promise<void>, question: string) => { if (!selected || !window.confirm(question)) return; setError(''); try { await action() } catch (reason: any) { setError(reason?.message || '操作失败') } }
  if (isLoading) return <div className="min-h-full bg-[var(--page-bg,#f7f8fb)] p-5"><div className="h-72 animate-pulse rounded-lg bg-gray-200" /></div>
  return <div className="theme-page min-h-full p-4 pb-[calc(7rem+env(safe-area-inset-bottom))] md:p-7 md:pb-[calc(7rem+env(safe-area-inset-bottom))]">
    <div className="mx-auto grid max-w-[1080px] gap-4 md:grid-cols-[minmax(0,1fr)_260px]">
      <section className="theme-surface rounded-2xl border p-5 shadow-[0_3px_12px_rgba(15,23,42,.14)]">
        <header className="mb-4 flex items-center gap-2"><span className="text-2xl">🎁</span><h1 className="text-2xl font-black text-gray-950">背包</h1></header>
        <div className="mb-4 flex border-b border-gray-100">{backpackFilters.map(([key, label]) => <button key={key} onClick={() => setFilter(key)} className={`px-4 py-2 text-base font-bold ${filter === key ? 'border-b-2 border-emerald-500 bg-emerald-50 text-gray-950' : 'text-gray-600 hover:bg-gray-50'}`}>{label}</button>)}</div>
        <div className="grid grid-cols-7 gap-2">{Array.from({ length: Math.max(BACKPACK_MINIMUM_SLOTS, visible.length + visibleFragments.length) }, (_, index) => {
          const group = visible[index]
          const item = group?.item
          const fragment = visibleFragments[index - visible.length]
          return item ? <button key={item.id} onClick={() => setSelectedId(item.id)} className={`relative aspect-square rounded-lg border-2 p-1 text-4xl transition ${selectedId === item.id ? 'border-emerald-400 bg-emerald-100 shadow-[0_0_10px_rgba(34,197,94,.8)]' : 'border-dashed border-gray-300 bg-gray-50'} ${item.is_used ? 'grayscale opacity-45' : ''}`} title={item.title}>{item.icon || '🎁'}{group.quantity > 1 && <span className="absolute right-1 top-1 rounded bg-slate-900 px-1 text-xs font-black text-white">x{group.quantity}</span>}<span className="sr-only">{item.title}</span></button> : fragment ? <button key={fragment.id} onClick={() => setSelectedId(fragment.id)} className={`relative aspect-square rounded-lg border-2 border-dashed border-gray-400 bg-gray-100 p-1 text-4xl grayscale opacity-55 transition ${selectedId === fragment.id ? 'border-emerald-400 ring-2 ring-emerald-200' : ''}`} title={`${fragment.title}进度 ${fragment.progress_percent ?? fragment.current_count}%`}>{fragment.icon || '🧩'}<span className="absolute right-1 top-1 rounded bg-slate-700 px-1 text-xs font-black text-white">{fragment.progress_percent ?? fragment.current_count}%</span><span className="sr-only">{fragment.title}进度</span></button> : <div key={`empty-${index}`} className="aspect-square rounded-lg border-2 border-dashed border-gray-300 bg-gray-50" />
        })}</div>
      </section>
      <aside className="theme-surface rounded-2xl border p-5 shadow-[0_3px_12px_rgba(15,23,42,.14)]">
        <h2 className="mb-4 flex items-center gap-2 text-xl font-black">🎁 物品详情</h2>{selected ? <><div className="flex items-center gap-3 border-b pb-4"><span className="grid h-16 w-16 place-items-center rounded bg-emerald-50 text-4xl">{selected.icon || '🎁'}</span><div><h3 className="text-2xl font-black">{selected.title}</h3><p className={selected.is_used ? 'text-gray-400' : 'font-bold text-emerald-500'}>{selected.is_used ? '已使用' : '可使用'}</p></div></div><p className="mt-4 min-h-12 text-sm leading-6 text-gray-800">{getBackpackItemDescription(selected)}</p><dl className="mt-3 space-y-2 border-t pt-3 text-sm"><div><dt className="inline font-bold">状态：</dt><dd className="inline text-emerald-600">{selected.is_used ? '已使用' : '可使用'}</dd></div><div><dt className="inline font-bold">添加：</dt><dd className="inline">{selected.created_at}</dd></div><div><dt className="inline font-bold">已用：</dt><dd className="inline">{selected.used_at || '[未提及]'}</dd></div></dl>{canUseBackpackItem(selected) && <div className="mt-6"><button onClick={() => run(() => useItem(selected.id), `确定使用“${selected.title}”？`)} className="w-full rounded-lg bg-emerald-500 py-3 text-lg font-black text-white shadow-[0_0_10px_rgba(34,197,94,.7)]">立即使用</button></div>}</> : selectedFragment ? <><div className="flex items-center gap-3 border-b pb-4 grayscale opacity-65"><span className="grid h-16 w-16 place-items-center rounded bg-gray-100 text-4xl">{selectedFragment.icon || '🧩'}</span><div><h3 className="text-2xl font-black">{selectedFragment.title}进度</h3><p className="font-bold text-gray-500">未合成，暂不可使用</p></div></div><p className="mt-4 min-h-12 text-sm leading-6 text-gray-800">{selectedFragment.description || '累计到 100% 后自动合成完整卡片。'}</p><dl className="mt-3 space-y-2 border-t pt-3 text-sm"><div><dt className="inline font-bold">进度：</dt><dd className="inline">{selectedFragment.progress_percent ?? selectedFragment.current_count}%</dd></div>{selectedFragment.inventory_limit && <div><dt className="inline font-bold">完整卡片：</dt><dd className="inline">本月 {selectedFragment.inventory_used || 0}/{selectedFragment.inventory_limit}{selectedFragment.inventory_limit_reached ? '，本月已满' : ''}</dd></div>}<div><dt className="inline font-bold">最早到期：</dt><dd className="inline">{selectedFragment.earliest_expires_at}</dd></div><div><dt className="inline font-bold">状态：</dt><dd className="inline text-gray-500">未合成，不可使用</dd></div></dl></> : <div className="grid min-h-56 place-items-center text-sm text-gray-400">选择一个物品查看详情</div>}
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </aside>
    </div>
    <section className="mx-auto mt-4 max-w-[1080px] rounded-2xl bg-slate-800 p-4 text-gray-100 shadow-[0_3px_12px_rgba(15,23,42,.24)] dark:bg-slate-950"><h2 className="mb-3 text-xl font-black">📜 物品流水记录</h2><div className="min-h-32 max-h-56 space-y-1 overflow-auto rounded-lg bg-black/30 p-3 font-mono text-sm">{events.length ? events.map(event => <div key={event.id}>{formatBackpackEvent(event)}</div>) : <div className="text-gray-400">暂无新的物品流水</div>}</div>{hasMoreEvents && <button onClick={loadMoreEvents} disabled={isLoadingMoreEvents} className="mt-3 w-full border border-slate-500 py-2 text-sm font-bold text-slate-200 disabled:opacity-50">{isLoadingMoreEvents ? '加载中' : '加载更多'}</button>}</section>
  </div>
})

BackpackPage.displayName = 'BackpackPage'
