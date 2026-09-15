// ui/src/components/Goals/GoalEditSheet.tsx
import { memo, useCallback, useState } from 'react'
import type { GoalFormData } from '../../types'
import { BottomSheet } from '../common/BottomSheet'

interface Props {
  goal?: GoalFormData
  categories: Array<{ id: number; name: string }>
  onSave: (data: GoalFormData) => Promise<void>
  onClose: () => void
}

export const GoalEditSheet = memo(({ goal, categories, onSave, onClose }: Props) => {
  const [title, setTitle] = useState(goal?.title || '')
  const [categoryIds, setCategoryIds] = useState<number[]>(goal?.category_ids ?? (goal?.category_id == null ? [] : [goal.category_id]))
  const [metric, setMetric] = useState<'duration' | 'count'>(goal?.metric || 'duration')
  const [targetValue, setTargetValue] = useState(goal?.target_value || 60)
  const [period, setPeriod] = useState<GoalFormData['period']>(goal?.period || 'daily')
  const [operator, setOperator] = useState<'<=' | '>='>(goal?.operator || '>=')
  const [rewardCoins, setRewardCoins] = useState(goal?.reward_coins || 5)
  const [penaltyCoins, setPenaltyCoins] = useState(goal?.penalty_coins || 5)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = useCallback(async () => {
    if (!title.trim() || targetValue <= 0 || categoryIds.length === 0) return setError('请填写目标名称、至少一个分类和大于零的目标值')
    setSaving(true); setError('')
    try {
      await onSave({ id: goal?.id, title: title.trim(), category_id: categoryIds[0] ?? null, category_ids: categoryIds, metric, target_value: targetValue, period, operator, reward_coins: rewardCoins, penalty_coins: penaltyCoins })
    } catch (reason: any) {
      setError(reason?.message || '目标保存失败')
    } finally { setSaving(false) }
  }, [title, categoryIds, metric, targetValue, period, operator, rewardCoins, penaltyCoins, goal, onSave])

  return (
    <BottomSheet open onClose={onClose}>
      <div className="space-y-4 p-4">
        <h3 className="text-lg font-bold text-gray-900">{goal?.id ? '编辑目标' : '新建目标'}</h3>
        <input type="text" value={title} onChange={e => setTitle(e.target.value)} placeholder="目标标题" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        <div className="space-y-2 rounded-lg border border-gray-200 p-3">
          <span className="text-xs text-gray-400">统计分类（可多选）</span>
          <div className="flex flex-wrap gap-2">
            {categories.map(c => {
              const checked = categoryIds.includes(c.id)
              return <label key={c.id} className={`cursor-pointer rounded-md border px-2.5 py-1.5 text-sm ${checked ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 text-gray-600'}`}>
                <input className="sr-only" type="checkbox" checked={checked} onChange={() => setCategoryIds(ids => checked ? ids.filter(id => id !== c.id) : [...ids, c.id])} />
                {c.name}
              </label>
            })}
          </div>
        </div>
        <div className="flex gap-2">
          <select value={metric} onChange={e => setMetric(e.target.value as any)} className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400">
            <option value="duration">时长（分钟）</option><option value="count">次数</option>
          </select>
          <input type="number" value={targetValue} onChange={e => setTargetValue(Number(e.target.value))} className="w-24 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        </div>
        <div className="flex gap-2">
          <select value={period} onChange={e => setPeriod(e.target.value as any)} className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400">
            <option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option><option value="per_session">每次专注</option>
          </select>
          <select value={operator} onChange={e => setOperator(e.target.value as any)} className="w-24 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400">
            <option value=">=">≥</option><option value="<=">≤</option>
          </select>
        </div>
        <div className="flex gap-2">
          <label className="flex-1"><span className="text-xs text-gray-400">奖励 🪙</span><input type="number" value={rewardCoins} onChange={e => setRewardCoins(Number(e.target.value))} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" /></label>
          <label className="flex-1"><span className="text-xs text-gray-400">惩罚 🪙</span><input type="number" value={penaltyCoins} onChange={e => setPenaltyCoins(Number(e.target.value))} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" /></label>
        </div>
        {error && <div className="text-sm text-red-500">{error}</div>}
        <button disabled={saving} onClick={handleSave} className="h-12 w-full rounded-xl bg-blue-500 text-base font-semibold text-white active:bg-blue-600 disabled:bg-gray-300">{saving ? '保存中…' : '保存'}</button>
      </div>
    </BottomSheet>
  )
})

GoalEditSheet.displayName = 'GoalEditSheet'
