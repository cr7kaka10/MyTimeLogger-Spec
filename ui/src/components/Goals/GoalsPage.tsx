// ui/src/components/Goals/GoalsPage.tsx
import { memo, useCallback, useState } from 'react'
import type { GoalFormData, HabitSection } from '../../types'
import type { UseGoalsReturn } from '../../hooks/useGoals'
import { EmptyState } from '../common/EmptyState'
import { ProgressBar } from '../common/ProgressBar'
import { GoalEditSheet } from './GoalEditSheet'

interface GoalsPageProps extends UseGoalsReturn {
  balance?: number
  activeSection: HabitSection
  onSectionChange: (section: HabitSection) => void
  categories: Array<{ id: number; name: string }>
}

const colorForPercent = (percent: number): string => {
  if (percent >= 100) return '#22C55E'
  if (percent >= 50) return '#2563EB'
  return '#999999'
}

export const GoalsPage = memo(({ goals, progressMap, historyMap, addGoal, updateGoal, deleteGoal, balance = 0, categories }: GoalsPageProps) => {
  const [showAdd, setShowAdd] = useState(false)
  const [editingGoal, setEditingGoal] = useState<GoalFormData | null>(null)
  const [error, setError] = useState('')

  const handleSave = useCallback(async (data: GoalFormData) => {
    setError('')
    const { id, ...goal } = data
    try {
      if (id != null) await updateGoal(id, goal as any)
      else await addGoal(goal as any)
      setShowAdd(false)
      setEditingGoal(null)
    } catch (reason: any) {
      setError(reason?.message || '目标保存失败')
      throw reason
    }
  }, [addGoal, updateGoal])

  const removeGoal = useCallback(async (id: string | number) => {
    if (!window.confirm('删除后不会影响已有结算和背包历史，确定继续吗？')) return
    try {
      await deleteGoal(id)
      setEditingGoal(null)
    } catch (reason: any) {
      setError(reason?.message || '目标删除失败')
    }
  }, [deleteGoal])

  return (
    <div className="flex min-h-full flex-col gap-4 bg-[#FAFAFA] p-6 font-sans">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">目标</h1>
          <div className="mt-2 text-sm text-gray-400">挑战进度与奖惩</div>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowAdd(true)} className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold text-blue-600">+ 新增</button>
          <div className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold">💰 {typeof balance === 'number' ? parseFloat(balance.toFixed(2)) : balance}</div>
        </div>
      </header>
      {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</div>}
      {goals.length === 0 ? (
        <EmptyState icon="🏆" title="设定一个目标" description="让专注更有方向。" actionLabel="+ 新建目标" onAction={() => setShowAdd(true)} />
      ) : <div className="flex-1 space-y-3">
        {goals.map((goal) => {
          const progress = (progressMap as any)[goal.id] || { current: 0, target: goal.target_value, percent: 0 }
          return (
            <div key={goal.id} className="relative rounded-xl border border-gray-100 bg-white p-4 group shadow-sm">
              <button onClick={() => setEditingGoal({ id: goal.id, title: goal.title, category_id: goal.category_id, category_ids: goal.category_ids ?? (goal.category_id == null ? [] : [goal.category_id]), metric: goal.metric as any, target_value: goal.target_value, period: goal.period as any, operator: goal.operator as any, reward_coins: goal.reward_coins, penalty_coins: goal.penalty_coins })}
                className="absolute right-3 top-3 text-xs text-gray-300 opacity-0 group-hover:opacity-100 hover:text-blue-500 transition-all font-semibold">编辑</button>
              <div className="font-semibold text-gray-900">{goal.title}</div>
              <div className="mt-1 text-sm text-gray-400">{goal.period === 'daily' ? '日目标' : goal.period === 'weekly' ? '周目标' : goal.period === 'monthly' ? '月目标' : '单次目标'} · {goal.metric === 'duration' ? '时长' : '次数'} · {goal.operator} {goal.target_value}</div>
              <div className="mt-1 text-xs text-gray-400">分类：{(goal.category_ids ?? (goal.category_id == null ? [] : [goal.category_id])).map(id => categories.find(category => category.id === id)?.name || id).join(' + ')}</div>
              <div className="mt-4"><ProgressBar percent={progress.percent} color={colorForPercent(progress.percent)} /></div>

              {/* 30天专注热力图 */}
              {goal.period !== 'per_session' && <GoalHistoryGrid history={(historyMap as any)[goal.id]} target={goal.target_value} period={goal.period} metric={goal.metric} />}

              <div className="mt-3 flex items-center justify-between gap-4 text-xs text-gray-400 border-t border-gray-50 pt-2.5">
                <span>当前进度: {progress.current} / {progress.target}</span>
                <span>达标 +{goal.reward_coins}💰 / 失败 -{goal.penalty_coins}💰</span>
                <button type="button" onClick={() => removeGoal(goal.id)} className="text-red-400 hover:text-red-600">删除</button>
              </div>
            </div>
          )
        })}
      </div>}

      {showAdd && <GoalEditSheet categories={categories} onSave={handleSave} onClose={() => setShowAdd(false)} />}
      {editingGoal && (
        <GoalEditSheet goal={editingGoal} categories={categories} onSave={handleSave} onClose={() => setEditingGoal(null)} />
      )}
    </div>
  )
})

const GoalHistoryGrid = memo(({ history, target, period, metric }: { history?: Record<string, number>; target: number; period: string; metric: string }) => {
  if (!history) return null

  // Determine proportional daily target
  let dailyTarget = target
  if (period === 'weekly') dailyTarget = target / 7
  else if (period === 'monthly') dailyTarget = target / 30

  // Sort dates to show oldest first
  const entries = Object.entries(history).sort((a, b) => a[0].localeCompare(b[0]))

  return (
    <div className="mt-3">
      <div className="text-[10px] font-bold text-gray-400 mb-1.5 uppercase tracking-wider">过去 30 天日均热力图</div>
      <div className="flex flex-wrap gap-1">
        {entries.map(([date, val]) => {
          let bg = 'bg-gray-100'
          let title = `${date}: 无专注`

          if (val > 0) {
            const ratio = val / (dailyTarget || 1)
            const unit = metric === 'duration' ? 'm' : '次'
            title = `${date}: 专注 ${Math.round(val)}${unit} (${Math.round(ratio * 100)}%)`

            if (ratio >= 1.0) bg = 'bg-green-600'
            else if (ratio >= 0.5) bg = 'bg-green-400'
            else bg = 'bg-green-200'
          }

          return (
            <div
              key={date}
              className={`h-2.5 w-2.5 rounded-sm ${bg} transition-all duration-150 hover:scale-125`}
              title={title}
            />
          )
        })}
      </div>
    </div>
  )
})

GoalHistoryGrid.displayName = 'GoalHistoryGrid'
GoalsPage.displayName = 'GoalsPage'
