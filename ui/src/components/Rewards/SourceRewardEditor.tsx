import { useEffect, useMemo, useState } from 'react'
import type { Reward, SourceRewardType } from '../../types'
import { useRewards } from '../../hooks/useRewards'
import { useSourceRewards } from '../../hooks/useSourceRewards'
import { BottomSheet } from '../common/BottomSheet'
import { RewardAddSheet } from './RewardAddSheet'

interface Props { sourceType: SourceRewardType; sourceId: string; sourceTitle: string; onClose: () => void }
type RewardDraft = Parameters<React.ComponentProps<typeof RewardAddSheet>['onSave']>[0]

export const SourceRewardEditor = ({ sourceType, sourceId, sourceTitle, onClose }: Props) => {
  const catalog = useRewards()
  const source = useSourceRewards(sourceType, sourceId)
  const [coins, setCoins] = useState(0)
  const [sheetReward, setSheetReward] = useState<Reward | null | undefined>(undefined)
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { if (source.summary) setCoins(source.summary.coins) }, [source.summary])
  const available = useMemo(() => catalog.rewards.filter(item => item.redemption_mode === 'task' && item.fulfillment_mode === 'fragment'), [catalog.rewards])
  const itemRewards = source.summary?.itemRewards || (source.summary?.itemReward ? [source.summary.itemReward] : [])
  const fragmentHint = '物品进度：每次完成按绑定规则增加百分比；多个来源共同累计到 100% 后合成完整卡片。'

  const saveItem = async (data: RewardDraft) => {
    if (sheetReward) await catalog.updateReward(sheetReward.id, data.title, data.icon, data.price, data.description, null, null, null, null, data.inventory_mode, data.inventory_limit, data.unlock_required_count, data.redemption_mode, data.fulfillment_mode, data.fragment_target_count)
    else {
      const created: any = await catalog.addReward(data.title, data.icon, data.price, data.description, null, null, null, null, data.inventory_mode, data.inventory_limit, data.unlock_required_count, 'task', 'fragment', data.fragment_target_count)
      if (created?.reward_id) await source.bindItem(created.reward_id)
    }
    setSheetReward(undefined); await source.refresh()
  }

  const bindSelected = async () => {
    const item = available.find(reward => String(reward.id) === selectedId)
    if (!item) return
    await source.bindItem(item.id)
    setSelectedId(''); await source.refresh()
  }

  return <>
    <BottomSheet open onClose={onClose} layerClass="z-[70]">
      <div className="space-y-4 p-1 text-gray-900 dark:text-gray-100">
        <h3 className="text-lg font-bold">更新奖励</h3>
        <div className="rounded-xl border border-gray-200 p-3 dark:border-gray-700">
          <label className="text-xs text-gray-500">金币奖励</label>
          <div className="mt-2 flex gap-2"><input type="number" min={0} value={coins} onChange={event => setCoins(Number(event.target.value))} className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-900" /><button type="button" onClick={() => void source.saveCoins(coins).catch(reason => setError(reason.message))} className="rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white">保存</button></div>
        </div>
        <div className="rounded-xl border border-gray-200 p-3 dark:border-gray-700">
          <div className="text-xs text-gray-500">物品奖励</div>
          <p className="mt-1 text-xs text-blue-600 dark:text-blue-300">{fragmentHint}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">{itemRewards.length ? itemRewards.map(item => { const progress = source.summary?.fragmentProgress?.[String(item.id)]; return <span key={item.id} className="rounded-lg bg-gray-100 px-2 py-1 dark:bg-gray-800">{item.icon} {item.title} · {progress?.percent ?? progress?.activeUnits ?? 0}%{progress?.inventoryLimitReached ? ' · 本月已满' : ''}<button type="button" onClick={() => void source.unbindItem(item.id).catch(reason => setError(reason.message))} className="ml-1 text-red-500">×</button></span> }) : <span>未设置</span>}</div>
          <div className="mt-3 flex gap-2"><select value={selectedId} onChange={event => setSelectedId(event.target.value)} className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-2 py-2 text-sm dark:border-gray-700 dark:bg-gray-900"><option value="">选择完成奖励型商品</option>{available.map(item => <option key={item.id} value={String(item.id)}>{item.icon} {item.title} · 累计到 100%</option>)}</select><button type="button" disabled={!selectedId} onClick={() => void bindSelected().catch(reason => setError(reason.message))} className="rounded-lg bg-blue-600 px-3 text-sm text-white disabled:bg-gray-300">绑定</button></div>
          <button type="button" onClick={() => setSheetReward(null)} className="mt-3 text-sm font-semibold text-blue-600">+ 创建完成奖励型商品</button>
        </div>
        {(error || source.error) && <div className="text-sm text-red-500">{error || source.error}</div>}
      </div>
    </BottomSheet>
    {sheetReward !== undefined && <RewardAddSheet reward={sheetReward} layerClass="z-[80]" onSave={saveItem} onClose={() => setSheetReward(undefined)} />}
  </>
}
