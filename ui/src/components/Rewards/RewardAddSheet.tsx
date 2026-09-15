// ui/src/components/Rewards/RewardAddSheet.tsx
import { memo, useCallback, useEffect, useState } from 'react'
import type { Reward, SourceRewardType } from '../../types'
import { BottomSheet } from '../common/BottomSheet'
import { getDatabase } from '../../db'

const EMOJIS = ['🎁', '☕', '🎮', '🍜', '🎬', '📱', '🍰', '🎵', '📚', '✈️', '🏖️', '🎪', '🍕', '💆', '🛍️', '🎧', '🚴', '🍿', '💻', '🎨']

interface TaskOption {
  id: string
  title: string
  sourceType: 'checklist_task' | 'habit' | 'learning_task' | 'learning_objective'
}
interface GoalOption { id: string; title: string }

interface Props {
  reward?: Reward | null
  lockedSource?: { sourceType: SourceRewardType; sourceId: string; title: string }
  layerClass?: string
  onSave: (data: { title: string; icon: string; price: number; redemption_mode: NonNullable<Reward['redemption_mode']>; description: string; unlock_task_id: string | null; unlock_task_title: string | null; unlock_source_type: string | null; unlock_source_id: string | null; inventory_mode: string; inventory_limit: number | null; unlock_required_count: number; fulfillment_mode: NonNullable<Reward['fulfillment_mode']>; fragment_target_count: number }) => Promise<void>
  onClose: () => void
}

const normalizeInventoryMode = (value?: string | null): NonNullable<Reward['inventory_mode']> => (
  value === 'daily' || value === 'monthly' ? value : 'unlimited'
)

export const RewardAddSheet = memo(({ reward, lockedSource, layerClass, onSave, onClose }: Props) => {
  const [title, setTitle] = useState(reward?.title || '')
  const [icon, setIcon] = useState(reward?.icon || '🎁')
  const [price, setPrice] = useState(reward?.price || 10)
  const [desc, setDesc] = useState(reward?.description || '')
  const [mode, setMode] = useState<NonNullable<Reward['redemption_mode']>>(reward?.redemption_mode === 'coins' || reward?.redemption_mode === 'custom_spend' ? reward.redemption_mode : 'task')
  const [selectedTaskId, setSelectedTaskId] = useState<string>(lockedSource?.sourceId || reward?.unlock_source_id || (reward?.unlock_task_id?.startsWith('goal_') ? '' : reward?.unlock_task_id || ''))
  const [taskSourceType, setTaskSourceType] = useState<TaskOption['sourceType']>(lockedSource?.sourceType || (reward?.unlock_source_type === 'habit' || reward?.unlock_source_type === 'learning_task' ? reward.unlock_source_type : 'checklist_task'))
  const [selectedGoalId, setSelectedGoalId] = useState<string>(reward?.unlock_task_id?.replace(/^goal_/, '') || '')
  const [taskOptions, setTaskOptions] = useState<TaskOption[]>([])
  const [goalOptions, setGoalOptions] = useState<GoalOption[]>([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [inventoryMode, setInventoryMode] = useState<NonNullable<Reward['inventory_mode']>>(normalizeInventoryMode(reward?.inventory_mode))
  const [inventoryLimit, setInventoryLimit] = useState<number>(reward?.inventory_limit || 1)
  const [fragmentTargetCount, setFragmentTargetCount] = useState<number>(reward?.fragment_target_count || reward?.unlock_required_count || 1)
  const isFragmentSource = mode === 'task'

  useEffect(() => {
    getDatabase().then(db => {
      // 读取所有的今日/活跃/同步回来的清单任务作为绑定解锁条件的来源
      const raw = db.getActiveTasks ? db.getActiveTasks() : []
      const options: TaskOption[] = raw.map((r: any) => ({ id: r.ticktick_id || String(r.id), title: r.title, sourceType: 'checklist_task' }))
      options.push(...(db.getHabits?.() || []).map((habit: any) => ({ id: String(habit.id), title: habit.name, sourceType: 'habit' as const })))
      options.push(...((db.allRaw?.('SELECT id, title FROM learning_tasks WHERE status <> 2') || []) as any[]).map(task => ({ id: String(task.id), title: task.title, sourceType: 'learning_task' as const })))
      if (lockedSource && !options.some(option => option.id === lockedSource.sourceId && option.sourceType === lockedSource.sourceType)) options.push({ id: lockedSource.sourceId, title: lockedSource.title, sourceType: lockedSource.sourceType })
      setTaskOptions(options)
      setGoalOptions((db.getGoals ? db.getGoals() : []).filter((goal: any) => goal.is_active).map((goal: any) => ({ id: String(goal.id), title: goal.title })))
    })
  }, [lockedSource])

  const handleSave = useCallback(async () => {
    if (!title.trim()) return setError('请填写奖励名称')
    const isTask = mode === 'task'
    if (inventoryMode !== 'unlimited' && (!Number.isInteger(inventoryLimit) || inventoryLimit < 1)) return setError('请设置正整数商品数量')
    if (isTask && (!Number.isInteger(fragmentTargetCount) || fragmentTargetCount < 1)) return setError('碎片目标数必须是正整数')
    setSaving(true); setError('')
    try {
      const fragmentTarget = isTask ? fragmentTargetCount : 1
      await onSave({ title: title.trim(), icon, price: isTask || mode === 'custom_spend' ? 0 : price, redemption_mode: mode, description: desc.trim(), unlock_task_id: null, unlock_task_title: null, unlock_source_type: null, unlock_source_id: null, inventory_mode: inventoryMode, inventory_limit: inventoryMode === 'unlimited' ? null : inventoryLimit, unlock_required_count: fragmentTarget, fulfillment_mode: isTask ? 'fragment' : 'immediate', fragment_target_count: fragmentTarget })
    } catch (reason: any) {
      setError(reason?.message || '奖励保存失败')
    } finally { setSaving(false) }
  }, [title, icon, price, desc, mode, onSave, inventoryMode, inventoryLimit, fragmentTargetCount])

  return (
    <BottomSheet open onClose={onClose} layerClass={layerClass}>
      <div className="space-y-4 p-4 max-h-[85vh] overflow-y-auto">
        <h3 className="text-lg font-bold text-gray-900">{reward ? '编辑商品' : '添加商品'}</h3>

        <div>
          <span className="text-xs text-gray-400">商品名称</span>
          <input type="text" value={title} onChange={e => setTitle(e.target.value)} placeholder="名称，如：大保健一次" className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        </div>

        <div>
          <span className="text-xs text-gray-400">图标</span>
          <div className="mt-1 flex flex-wrap gap-2">{EMOJIS.map(e => (
            <button key={e} type="button" onClick={() => setIcon(e)} className={`h-9 w-9 rounded-lg text-lg ${icon === e ? 'bg-blue-100 ring-2 ring-blue-400' : 'bg-gray-50 active:bg-gray-100'}`}>{e}</button>
          ))}</div>
        </div>

        <div>
          <span className="text-xs text-gray-400">兑换类型</span>
          <div className="mt-1.5 flex gap-4 text-sm font-semibold">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" checked={mode === 'coins'} onChange={() => setMode('coins')} className="text-blue-500" />
              <span>金币购买型</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" checked={mode === 'task'} onChange={() => setMode('task')} className="text-blue-500" />
              <span>完成奖励型</span>
            </label>
          </div>
        </div>

        {mode === 'coins' ? (
          <div>
            <span className="text-xs text-gray-400">价格 🪙</span>
            <input type="number" value={price} onChange={e => setPrice(Number(e.target.value))} min={1} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
          </div>
        ) : <p className="text-sm text-gray-500">完成奖励型商品由习惯、任务或学习目标的奖励界面绑定；商品页不设置绑定来源。</p>}

        {isFragmentSource && <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:bg-blue-950/40 dark:text-blue-200">
          <div className="font-semibold">物品碎片</div>
          <p className="mt-1 text-xs">任一绑定来源每次完成获得 1 枚；集满 n 枚自动合成，单枚有效期也是 n 天。</p>
          <label className="mt-3 block text-xs">碎片目标数（也是有效期天数）
            <input type="number" min={1} step={1} value={fragmentTargetCount} onChange={e => setFragmentTargetCount(Number(e.target.value))} className="mt-1 w-full rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-400" />
          </label>
        </div>}

        <div>
          <span className="text-xs text-gray-400">商品数量</span>
          <select value={inventoryMode} onChange={e => setInventoryMode(e.target.value as NonNullable<Reward['inventory_mode']>)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400 bg-white">
            <option value="unlimited">不限量</option><option value="daily">每天更新</option><option value="monthly">每月更新</option>
          </select>
          {inventoryMode !== 'unlimited' && <input type="number" min={1} step={1} value={inventoryLimit} onChange={e => setInventoryLimit(Number(e.target.value))} className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" placeholder="每个周期的数量" />}
        </div>

        <div>
          <span className="text-xs text-gray-400">描述</span>
          <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400 resize-none" placeholder="选填商品说明..." />
        </div>

        {error && <div className="text-sm text-red-500">{error}</div>}
        <button disabled={saving} onClick={handleSave} className="h-12 w-full rounded-xl bg-blue-500 text-base font-semibold text-white active:bg-blue-600 transition-colors disabled:bg-gray-300">{saving ? '保存中…' : '保存'}</button>
      </div>
    </BottomSheet>
  )
})

RewardAddSheet.displayName = 'RewardAddSheet'
