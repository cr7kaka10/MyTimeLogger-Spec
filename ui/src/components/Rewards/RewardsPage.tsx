// ui/src/components/Rewards/RewardsPage.tsx
import { memo, useCallback, useRef, useState } from 'react'
import type { HabitSection, Reward } from '../../types'
import type { UseRewardsReturn } from '../../hooks/useRewards'
import type { UseLedgerReturn } from '../../hooks/useLedger'
import { BottomSheet } from '../common/BottomSheet'
import { EmptyState } from '../common/EmptyState'
import { RewardAddSheet } from './RewardAddSheet'
import { LedgerSheet } from './LedgerSheet'

interface RewardsPageProps extends UseRewardsReturn {
  activeSection: HabitSection
  onSectionChange: (section: HabitSection) => void
  ledgerHook: UseLedgerReturn
}

export const RewardsPage = memo(({ balance, rewards, ledger, unclaimedRewards, buyReward, addReward, updateReward, deleteReward, claimRewards, activeSection, onSectionChange, ledgerHook }: RewardsPageProps) => {
  const [selectedReward, setSelectedReward] = useState<Reward | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [showLedger, setShowLedger] = useState(false)
  const [editingReward, setEditingReward] = useState<Reward | null>(null)
  const [deleteCandidate, setDeleteCandidate] = useState<Reward | null>(null)
  const [error, setError] = useState('')
  const [customSpend, setCustomSpend] = useState('')
  const [customSpendNote, setCustomSpendNote] = useState('')
  const [purchaseError, setPurchaseError] = useState('')
  const [isBuying, setIsBuying] = useState(false)
  const customSpendInputRef = useRef<HTMLInputElement>(null)
  const customSpendNoteInputRef = useRef<HTMLInputElement>(null)
  const lastCustomSpendFocus = useRef<'amount' | 'note'>('amount')

  const updateCustomSpend = (value: string) => {
    const normalized = value.replace(/[^\d.]/g, '')
    const [whole = '', ...fractionParts] = normalized.split('.')
    const fraction = fractionParts.join('').slice(0, 2)
    setCustomSpend(fractionParts.length ? `${whole}.${fraction}` : whole)
    setPurchaseError('')
  }

  const updateCustomSpendNote = (value: string) => {
    setCustomSpendNote(value)
    setPurchaseError('')
  }

  const focusCustomSpendInput = () => (lastCustomSpendFocus.current === 'note' ? customSpendNoteInputRef.current : customSpendInputRef.current)?.focus()

  const closePurchaseSheet = () => {
    if (isBuying) return
    setSelectedReward(null)
    setCustomSpend('')
    setCustomSpendNote('')
    setPurchaseError('')
  }

  const confirmPurchase = async () => {
    if (!selectedReward || isBuying) return
    const amount = selectedReward.redemption_mode === 'custom_spend' ? Number(customSpend) : undefined
    if (amount !== undefined && (!Number.isFinite(amount) || amount <= 0)) {
      setPurchaseError('请输入有效消费金额')
      customSpendInputRef.current?.focus()
      return
    }
    if (selectedReward.redemption_mode === 'custom_spend' && !customSpendNote.trim()) {
      setPurchaseError('请填写购买内容')
      customSpendNoteInputRef.current?.focus()
      return
    }
    setPurchaseError('')
    setIsBuying(true)
    try {
      await buyReward(selectedReward.id, amount, customSpendNote.trim())
      setSelectedReward(null)
      setCustomSpend('')
      setCustomSpendNote('')
    } catch (reason: any) {
      setPurchaseError(reason?.message || '购买失败，请修改金额后重试')
      window.requestAnimationFrame(focusCustomSpendInput)
    } finally {
      setIsBuying(false)
    }
  }

  const handleSave = useCallback(async (data: { title: string; icon: string; price: number; redemption_mode: NonNullable<Reward['redemption_mode']>; description: string; unlock_task_id: string | null; unlock_task_title: string | null; unlock_source_type: string | null; unlock_source_id: string | null; inventory_mode: string; inventory_limit: number | null; unlock_required_count: number; fulfillment_mode: NonNullable<Reward['fulfillment_mode']>; fragment_target_count: number }) => {
    setError('')
    try {
      if (editingReward) {
        await updateReward(editingReward.id, data.title, data.icon, data.price, data.description, data.unlock_task_id, data.unlock_task_title, data.unlock_source_type, data.unlock_source_id, data.inventory_mode, data.inventory_limit, data.unlock_required_count, data.redemption_mode, data.fulfillment_mode, data.fragment_target_count)
      } else {
        await addReward(data.title, data.icon, data.price, data.description, data.unlock_task_id, data.unlock_task_title, data.unlock_source_type, data.unlock_source_id, data.inventory_mode, data.inventory_limit, data.unlock_required_count, data.redemption_mode, data.fulfillment_mode, data.fragment_target_count)
      }
      setShowAdd(false)
      setEditingReward(null)
    } catch (reason: any) {
      setError(reason?.message || '奖励保存失败')
      throw reason
    }
  }, [editingReward, addReward, updateReward])

  const removeReward = useCallback(async (id: string | number) => {
    try {
      await deleteReward(id)
      setEditingReward(null)
      setDeleteCandidate(null)
    } catch (reason: any) {
      setError(reason?.message || '奖励删除失败')
    }
  }, [deleteReward])

  const bal = typeof balance === 'number' ? parseFloat(balance.toFixed(2)) : balance

  return (
    <div className="flex min-h-full flex-col gap-4 bg-[#FAFAFA] p-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">商店</h1>
          <div className="mt-2 text-sm text-gray-400">可用余额 {bal}💰</div>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowAdd(true)} className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold text-blue-600">+ 添加商品</button>
          <button onClick={() => setShowLedger(true)} className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold hover:bg-gray-50 active:bg-gray-100 transition-colors">💰 {bal}</button>
        </div>
      </header>

      {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}

      {unclaimedRewards.length > 0 && (
        <div className="flex items-center justify-between p-3.5 bg-blue-50/70 border border-blue-100 rounded-xl mb-1">
          <div className="text-sm text-blue-800 font-semibold flex items-center gap-1.5">
            <span>🎁</span>
            <span>待领取 ({unclaimedRewards.length} 项，共 {unclaimedRewards.reduce((s, x) => s + x.coins, 0).toFixed(2)} 🪙)</span>
          </div>
          <button
            onClick={() => claimRewards(unclaimedRewards.map(r => r.id))}
            className="px-4 py-2 text-xs font-bold text-white bg-blue-600 rounded-lg active:bg-blue-700 transition-colors shadow-sm"
          >
            一键领取
          </button>
        </div>
      )}

      {rewards.length === 0 ? (
        <EmptyState icon="🎁" title="还没有商品" description="创建一个可以兑换或解锁的商品。" actionLabel="+ 添加商品" onAction={() => setShowAdd(true)} />
      ) : <div className="grid flex-1 grid-cols-2 gap-3">
        {rewards.map((reward) => {
          const isUnlock = reward.redemption_mode === 'task' || reward.redemption_mode === 'goal'
          const isPending = reward.redemption_mode === 'pending_binding'
          const isCustomSpend = reward.redemption_mode === 'custom_spend'
          const fragmentPercent = Number(reward.fragment_progress_units || 0)
          const inventoryFull = reward.inventory_mode !== 'unlimited' && Number(reward.inventory_limit || 0) > 0 && Number(reward.inventory_used || 0) >= Number(reward.inventory_limit)
          const disabled = isUnlock || isPending || (!isCustomSpend && balance < reward.price)
          return (
            <div key={reward.id} className="relative flex min-h-40 flex-col rounded-xl border border-gray-100 bg-white p-4">
              <div className="absolute right-3 top-3 flex items-center gap-2 text-xs font-semibold">
                <button type="button" onClick={() => setEditingReward(reward)} className="text-blue-600 hover:text-blue-700">编辑</button>
                <button type="button" onClick={() => setDeleteCandidate(reward)} className="text-red-400 hover:text-red-600">删除</button>
              </div>
              <div className="text-3xl">{reward.icon}</div>
              <div className="mt-3 pr-20 font-semibold text-gray-900">{reward.title}</div>
              <div className="mt-1 text-sm text-gray-400">{isUnlock ? '完成奖励型 · 请在任务、习惯或学习目标中绑定' : isPending ? '暂未绑定任务' : isCustomSpend ? '填写消费金额 · 1 金币 = 1 元' : `${reward.price}💰`}</div>
              <div className="mt-1 text-xs text-gray-400">{reward.inventory_mode === 'daily' ? `完整卡片今日 ${reward.inventory_used || 0}/${reward.inventory_limit}` : reward.inventory_mode === 'monthly' ? `完整卡片本月 ${reward.inventory_used || 0}/${reward.inventory_limit}` : '完整卡片不限量'}{reward.fulfillment_mode === 'fragment' ? ` · 进度 ${fragmentPercent}%` : ''}{inventoryFull ? ' · 本月已满' : ''}</div>
              <button
                type="button"
                disabled={disabled}
                onClick={() => setSelectedReward(reward)}
                className={`mt-auto h-10 rounded-lg text-sm font-semibold ${disabled ? 'bg-gray-200 text-gray-400' : 'bg-blue-600 text-white active:bg-blue-700'}`}
              >{isUnlock ? '完成后自动入库' : isPending ? '等待绑定' : disabled ? '余额不足' : isCustomSpend ? '填写金额消费' : '兑换'}</button>
            </div>
          )
        })}
      </div>}

      {/* 兑换确认 */}
      <BottomSheet open={selectedReward !== null} onClose={closePurchaseSheet}>
        <div className="text-lg font-semibold text-gray-900">确认兑换</div>
        <div className="mt-3 text-sm text-gray-500">{selectedReward?.redemption_mode === 'custom_spend' ? `填写 ${selectedReward.title} 实际消费金额，1 金币 = 1 元。` : `确定用 ${selectedReward?.price}💰 兑换 ${selectedReward?.title} 吗？`}</div>
        {selectedReward?.redemption_mode === 'custom_spend' && <><input ref={customSpendInputRef} autoFocus type="text" inputMode="decimal" value={customSpend} onFocus={() => { lastCustomSpendFocus.current = 'amount' }} onChange={event => updateCustomSpend(event.target.value)} aria-describedby={purchaseError ? 'custom-spend-error' : undefined} placeholder="消费金额（元）" className="mt-3 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-500" /><input ref={customSpendNoteInputRef} type="text" value={customSpendNote} maxLength={120} onFocus={() => { lastCustomSpendFocus.current = 'note' }} onChange={event => updateCustomSpendNote(event.target.value)} aria-describedby={purchaseError ? 'custom-spend-error' : undefined} placeholder="具体买了什么（必填）" className="mt-3 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-500" />{purchaseError && <p id="custom-spend-error" className="mt-2 text-sm text-red-600">{purchaseError}</p>}</>}
        <div className="mt-6 grid grid-cols-2 gap-3">
          <button type="button" disabled={isBuying} onClick={closePurchaseSheet} className="h-12 rounded-xl bg-gray-100 font-semibold disabled:opacity-60">取消</button>
          <button type="button" disabled={isBuying} onClick={() => void confirmPurchase()} className="h-12 rounded-xl bg-blue-600 font-semibold text-white disabled:opacity-60">{isBuying ? '处理中…' : '确认'}</button>
        </div>
      </BottomSheet>

      {/* 新增/编辑 */}
      {showAdd && <RewardAddSheet onSave={handleSave} onClose={() => setShowAdd(false)} />}

      {editingReward && <RewardAddSheet reward={editingReward} onSave={handleSave} onClose={() => setEditingReward(null)} />}

      {deleteCandidate && (
        <BottomSheet open onClose={() => setDeleteCandidate(null)}>
          <div className="space-y-4">
            <h3 className="text-lg font-bold text-gray-900">确认删除商品</h3>
            <p className="text-sm text-gray-500">下架“{deleteCandidate.title}”后，已有背包历史会保留。</p>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" onClick={() => setDeleteCandidate(null)} className="h-12 rounded-xl bg-gray-100 font-semibold text-gray-600">取消</button>
              <button type="button" onClick={() => removeReward(deleteCandidate.id)} className="h-12 rounded-xl bg-red-50 font-semibold text-red-500">删除</button>
            </div>
          </div>
        </BottomSheet>
      )}

      {/* 流水 */}
      {showLedger && <LedgerSheet {...ledgerHook} onClose={() => setShowLedger(false)} />}
    </div>
  )
})

RewardsPage.displayName = 'RewardsPage'
