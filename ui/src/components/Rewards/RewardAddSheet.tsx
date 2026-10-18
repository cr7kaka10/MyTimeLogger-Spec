// ui/src/components/Rewards/RewardAddSheet.tsx
import { memo, useCallback, useEffect, useMemo, useState } from 'react'
import type { Reward, SourceRewardType } from '../../types'
import { BottomSheet } from '../common/BottomSheet'
import { ConfirmSheet } from '../common/ConfirmSheet'
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
  onSave: (data: { title: string; icon: string; price: number; redemption_mode: NonNullable<Reward['redemption_mode']>; description: string; unlock_task_id: string | null; unlock_task_title: string | null; unlock_source_type: string | null; unlock_source_id: string | null; inventory_mode: string; inventory_limit: number | null; unlock_required_count: number; fulfillment_mode: NonNullable<Reward['fulfillment_mode']>; fragment_target_count: number; convert_fragment_to_count?: true }) => Promise<void>
  onClose: () => void
}

const normalizeInventoryMode = (value?: string | null): NonNullable<Reward['inventory_mode']> => (
  value === 'daily' || value === 'weekly' || value === 'monthly' ? value : 'unlimited'
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
  const [discardOpen, setDiscardOpen] = useState(false)
  const [inventoryMode, setInventoryMode] = useState<NonNullable<Reward['inventory_mode']>>(normalizeInventoryMode(reward?.inventory_mode))
  const [inventoryLimit, setInventoryLimit] = useState<number>(reward?.inventory_limit || 1)
  const [fragmentTargetCount, setFragmentTargetCount] = useState<number>(reward?.fragment_target_count || reward?.unlock_required_count || 1)
  const [convertToCount, setConvertToCount] = useState(false)
  const isFragmentSource = mode === 'task'
  const legacyPercent = reward?.fragment_measure_mode === 'percent' || Number(reward?.legacy_percent_binding_count || 0) > 0
  const periodLabel = inventoryMode === 'daily' ? '今日' : inventoryMode === 'weekly' ? '本周' : inventoryMode === 'monthly' ? '本月' : ''
  const initialMode = reward?.redemption_mode === 'coins' || reward?.redemption_mode === 'custom_spend' ? reward.redemption_mode : 'task'
  const initialInventoryMode = normalizeInventoryMode(reward?.inventory_mode)
  const dirty = useMemo(() => title.trim() !== (reward?.title || '').trim() || icon !== (reward?.icon || '🎁')
    || mode !== initialMode || desc.trim() !== (reward?.description || '').trim()
    || (mode === 'coins' && price !== (reward?.price || 10)) || inventoryMode !== initialInventoryMode
    || (inventoryMode !== 'unlimited' && inventoryLimit !== (reward?.inventory_limit || 1))
    || convertToCount || (mode === 'task' && fragmentTargetCount !== (reward?.fragment_target_count || reward?.unlock_required_count || 1)),
  [title, reward, icon, mode, initialMode, desc, price, inventoryMode, initialInventoryMode, inventoryLimit, fragmentTargetCount, convertToCount])
  const requestClose = useCallback(() => {
    if (saving) return
    if (dirty) setDiscardOpen(true)
    else onClose()
  }, [dirty, onClose, saving])

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
    if (saving) return
    if (!title.trim()) return setError('请填写奖励名称')
    const isTask = mode === 'task'
    if (inventoryMode !== 'unlimited' && (!Number.isInteger(inventoryLimit) || inventoryLimit < 1)) return setError('请设置正整数商品数量')
    if (isTask && (!Number.isInteger(fragmentTargetCount) || fragmentTargetCount < 1)) return setError('碎片目标数必须是正整数')
    setSaving(true); setError('')
    try {
      const fragmentTarget = isTask ? fragmentTargetCount : 1
      await onSave({ title: title.trim(), icon, price: isTask || mode === 'custom_spend' ? 0 : price, redemption_mode: mode, description: desc.trim(), unlock_task_id: null, unlock_task_title: null, unlock_source_type: null, unlock_source_id: null, inventory_mode: inventoryMode, inventory_limit: inventoryMode === 'unlimited' ? null : inventoryLimit, unlock_required_count: fragmentTarget, fulfillment_mode: isTask ? 'fragment' : 'immediate', fragment_target_count: fragmentTarget, ...(convertToCount ? { convert_fragment_to_count: true as const } : {}) })
    } catch (reason: any) {
      setError(reason?.message || '奖励保存失败')
    } finally { setSaving(false) }
  }, [title, icon, price, desc, mode, onSave, inventoryMode, inventoryLimit, fragmentTargetCount, convertToCount, saving])

  return (
    <>
    <BottomSheet open onClose={requestClose} layerClass={layerClass} ariaLabel={reward ? '编辑商品' : '添加商品'} panelClass="flex max-h-[calc(100dvh-1rem)] w-full flex-col overflow-hidden p-0 sm:mb-4 sm:max-w-3xl sm:rounded-2xl">
      <div className="flex min-h-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center gap-3 border-b border-gray-100 px-4 py-3 dark:border-gray-800 sm:px-5">
          <button type="button" aria-label="返回" disabled={saving} onClick={requestClose} className="rounded-lg px-2 py-1 text-sm font-medium text-blue-600 hover:bg-blue-50 disabled:opacity-40 dark:text-blue-300 dark:hover:bg-blue-950/40">← 返回</button>
          <h3 className="text-base font-bold text-gray-900 dark:text-gray-100">{reward ? '编辑商品' : '添加商品'}</h3>
        </header>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-3 sm:overflow-visible sm:px-5">

        <div>
          <span className="text-xs text-gray-400">商品名称</span>
          <input type="text" value={title} onChange={e => setTitle(e.target.value)} placeholder="名称，如：大保健一次" className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        </div>

        <div>
          <span className="text-xs text-gray-400">图标</span>
          <div className="mt-1 flex flex-nowrap gap-1.5 overflow-x-auto pb-1 sm:gap-1 sm:overflow-x-visible">{EMOJIS.map(e => (
            <button key={e} type="button" onClick={() => setIcon(e)} className={`h-8 w-8 shrink-0 rounded-lg text-base sm:h-7 sm:w-7 sm:text-sm ${icon === e ? 'bg-blue-100 ring-2 ring-blue-400' : 'bg-gray-50 active:bg-gray-100 dark:bg-gray-800'}`}>{e}</button>
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

        <div className="grid gap-3 sm:grid-cols-2">
        {isFragmentSource && <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:bg-blue-950/40 dark:text-blue-200">
          <div className="font-semibold">物品碎片</div>
          <p className="mt-1 text-xs">任一绑定来源每次完成获得 1 枚；集满 n 枚自动合成。周期商品的碎片和完整商品都只在当期有效。</p>
          {legacyPercent && <label className="mt-2 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-2 text-amber-800"><input type="checkbox" checked={convertToCount} onChange={event => setConvertToCount(event.target.checked)} /><span>当前是历史百分比掉落；勾选后转换为按枚计数，并从新规则版本开始累计。</span></label>}
          <label className="mt-2 block text-xs">每张所需碎片数
            <input type="number" min={1} step={1} value={fragmentTargetCount} onChange={e => setFragmentTargetCount(Number(e.target.value))} className="mt-1 w-full rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-sm text-gray-900 outline-none focus:border-blue-400" />
          </label>
          <p className="mt-1 text-xs font-medium">{fragmentTargetCount} 枚合成 1 张{periodLabel ? `；${periodLabel}最多 ${inventoryLimit} 张` : '；完整商品不限量'}</p>
        </div>}

        <div>
          <span className="text-xs text-gray-400">每周期最多完整商品数</span>
          <select value={inventoryMode} onChange={e => setInventoryMode(e.target.value as NonNullable<Reward['inventory_mode']>)} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400 bg-white">
            <option value="unlimited">不限量</option><option value="daily">每天更新</option><option value="weekly">每周更新</option><option value="monthly">每月更新</option>
          </select>
          {inventoryMode === 'weekly' && <p className="mt-1 text-xs text-gray-500">按北京时间自然周计算：周一 00:00 至下周一 00:00。</p>}
          {inventoryMode !== 'unlimited' && <input type="number" min={1} step={1} value={inventoryLimit} onChange={e => setInventoryLimit(Number(e.target.value))} className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm outline-none focus:border-blue-400" placeholder="每个周期的数量" />}
        </div>
        </div>

        <div>
          <span className="text-xs text-gray-400">描述</span>
          <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={1} className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm outline-none focus:border-blue-400 resize-none" placeholder="选填商品说明..." />
        </div>

        {error && <div className="text-sm text-red-500">{error}</div>}
        </div>
        <footer className="shrink-0 border-t border-gray-100 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-gray-800 sm:px-5">
          <button disabled={saving} onClick={handleSave} className="h-10 w-full rounded-xl bg-blue-500 text-sm font-semibold text-white active:bg-blue-600 transition-colors disabled:bg-gray-300">{saving ? '保存中…' : '保存'}</button>
        </footer>
      </div>
    </BottomSheet>
    <ConfirmSheet open={discardOpen} title="放弃修改？" message="当前修改尚未保存，返回后将不会保留。" confirmLabel="放弃修改" busy={saving} onClose={() => setDiscardOpen(false)} onConfirm={() => { setDiscardOpen(false); onClose() }} />
    </>
  )
})

RewardAddSheet.displayName = 'RewardAddSheet'
