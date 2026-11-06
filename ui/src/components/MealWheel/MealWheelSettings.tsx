import { useEffect, useRef, useState } from 'react'
import { getDatabase } from '../../db'
import { MEAL_WHEEL_KEY, mealWheelDisplayPercentages, validateMealWheelItems, type MealWheelConfig, type MealWheelItem } from '../../mealWheel/config'
import { loadMealWheel, saveMealWheel } from '../../mealWheel/store'

export function MealWheelSettings({ onClose }: { onClose: () => void }) {
  const [baseline, setBaseline] = useState<MealWheelConfig | null>(null)
  const [items, setItems] = useState<MealWheelItem[]>([])
  const [message, setMessage] = useState('')
  const [conflict, setConflict] = useState(false)
  const [pending, setPending] = useState(false)
  const [saving, setSaving] = useState(false)
  const baselineRef = useRef<MealWheelConfig | null>(null)
  const itemsRef = useRef<MealWheelItem[]>([])
  useEffect(() => { itemsRef.current = items }, [items])
  const adopt = (value: MealWheelConfig) => { baselineRef.current = value; setBaseline(value); setItems(value.items.map(item => ({ ...item }))); setConflict(false); setMessage('') }
  useEffect(() => {
    let active = true
    const refresh = () => { void loadMealWheel().then(value => {
      if (!active) return
      if (!baselineRef.current) adopt(value)
      else if (baselineRef.current.revision !== value.revision) {
        if (JSON.stringify(itemsRef.current) === JSON.stringify(baselineRef.current.items)) adopt(value)
        else setConflict(true)
      }
    }).catch(() => { if (active) setMessage('读取转盘配置失败') }) }
    const checkPending = () => { void getDatabase().then(db => { if (active) setPending(db.hasPendingOutbox('system_config', MEAL_WHEEL_KEY)) }) }
    refresh(); checkPending()
    window.addEventListener('sync-pull-complete', refresh)
    window.addEventListener('mtl:sync-status', checkPending)
    return () => { active = false; window.removeEventListener('sync-pull-complete', refresh); window.removeEventListener('mtl:sync-status', checkPending) }
  }, [])
  const update = (id: string, field: 'name' | 'weight', value: string) => setItems(previous => previous.map(item => item.id === id ? { ...item, [field]: field === 'weight' ? Number(value) : value } : item))
  const move = (index: number, direction: number) => setItems(previous => {
    const next = [...previous], target = index + direction
    if (target < 0 || target >= next.length) return previous
    ;[next[index], next[target]] = [next[target], next[index]]
    return next
  })
  const save = async (overwrite = false) => {
    if (!baseline || saving) return
    const error = validateMealWheelItems(items)
    if (error) { setMessage(error); return }
    setSaving(true)
    try {
      const result = await saveMealWheel(items, baseline.revision, overwrite)
      if (!result.ok) { setMessage(result.reason); setConflict(result.conflict); return }
      adopt(result.config)
      setPending((await getDatabase()).hasPendingOutbox('system_config', MEAL_WHEEL_KEY))
      setMessage('已保存到本机，正在同步')
    } catch { setMessage('保存失败，请重试') } finally { setSaving(false) }
  }
  const probabilities = items.length && items.every(item => Number.isInteger(item.weight) && item.weight > 0)
    ? mealWheelDisplayPercentages(items) : []
  const duplicateNames = items.map(item => item.name.trim().toLocaleLowerCase())
  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section role="dialog" aria-modal="true" aria-label="转盘设置" className="theme-surface max-h-[94dvh] w-full max-w-[560px] overflow-y-auto rounded-3xl border p-5 shadow-2xl">
      <header className="mb-3 flex items-center justify-between"><h2 className="text-lg font-bold">转盘设置</h2><button type="button" onClick={onClose} className="rounded-lg px-3 py-1 text-sm hover:bg-gray-100 dark:hover:bg-gray-700">关闭</button></header>
      <p className="mb-3 text-sm text-gray-500 dark:text-gray-300">权重越高，被选中的概率越大；配置会同步到同一账号的其他设备。</p>
      {!baseline ? <p role="status">正在读取配置…</p> : <>
        <div className="space-y-2">{items.map((item, index) => {
          const badName = !item.name.trim() || Array.from(item.name.trim()).length > 20 || duplicateNames.indexOf(duplicateNames[index]) !== index
          const badWeight = !Number.isInteger(item.weight) || item.weight < 1 || item.weight > 100
          return <div key={item.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 p-2 dark:border-gray-700">
            <span className="w-5 text-xs text-gray-400">{index + 1}</span>
            <input aria-label={`餐食 ${index + 1} 名称`} aria-invalid={badName} value={item.name} maxLength={20} onChange={event => update(item.id, 'name', event.target.value)} className={`min-w-0 flex-1 rounded-lg border bg-transparent px-2 py-1 ${badName ? 'border-red-500' : 'border-gray-200 dark:border-gray-600'}`} />
            <input aria-label={`餐食 ${index + 1} 权重`} aria-invalid={badWeight} type="number" min="1" max="100" value={item.weight || ''} onChange={event => update(item.id, 'weight', event.target.value)} className={`w-14 rounded-lg border bg-transparent px-2 py-1 ${badWeight ? 'border-red-500' : 'border-gray-200 dark:border-gray-600'}`} />
            <span className="w-12 text-right text-xs">{probabilities[index]?.toFixed(1) ?? '—'}%</span>
            <button type="button" aria-label={`上移 ${item.name}`} disabled={index === 0} onClick={() => move(index, -1)} className="disabled:opacity-30">↑</button>
            <button type="button" aria-label={`下移 ${item.name}`} disabled={index === items.length - 1} onClick={() => move(index, 1)} className="disabled:opacity-30">↓</button>
            <button type="button" aria-label={`删除 ${item.name}`} disabled={items.length <= 2} onClick={() => setItems(previous => previous.filter(row => row.id !== item.id))} className="text-xl text-red-600 disabled:opacity-30">×</button>
          </div>
        })}</div>
        <button type="button" disabled={items.length >= 12} onClick={() => setItems(previous => [...previous, { id: crypto.randomUUID(), name: '', weight: 1 }])} className="mt-3 rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-gray-600">添加餐食</button>
        {conflict && <div role="alert" className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-900/30 dark:text-amber-100">其他设备已更新转盘。<button type="button" onClick={() => { void loadMealWheel().then(adopt) }} className="ml-2 underline">重新载入</button><button type="button" onClick={() => { void save(true) }} className="ml-2 underline">确认覆盖</button></div>}
        {message && <p role="status" className="mt-3 text-sm text-gray-600 dark:text-gray-300">{message}</p>}
        <p className="mt-2 text-xs text-gray-500">{pending ? '本机已保存，等待多端同步' : baseline.revision ? '配置已保存' : '默认示例，尚未保存'}</p>
        <button type="button" disabled={saving || conflict} onClick={() => { void save() }} className="mt-4 w-full rounded-xl bg-blue-600 py-3 font-bold text-white disabled:opacity-50">保存配置</button>
      </>}
    </section>
  </div>
}
