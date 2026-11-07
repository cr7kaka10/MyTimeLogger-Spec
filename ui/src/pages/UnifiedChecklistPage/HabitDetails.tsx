import { useEffect, useState } from 'react'
import type { Database } from '@models/Database'
import { getDatabase } from '../../db'
import { SourceRewardSummary } from '../../components/Rewards/SourceRewardSummary'
import { formatHabitRepeatRule } from '@core/HabitSchedule'
import { HabitMonthView } from './HabitMonthView'

interface Props { id: string | number; onEditHabit?: () => void; onEditReward?: () => void; onEditJournal: (date: string, note: string) => void; refreshKey?: number }

export function HabitDetails({ id, onEditHabit, onEditReward, onEditJournal, refreshKey }: Props) {
  const [details, setDetails] = useState<ReturnType<Database['getLocalHabitDetails']>>()
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    getDatabase().then(db => {
      const next = db.getLocalHabitDetails(id)
      if (active) { setDetails(next); if (!next) setError('本地习惯不存在') }
    }).catch(reason => { if (active) setError(reason?.message || '详情读取失败') })
    return () => { active = false }
  }, [id])
  if (error) return <p role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</p>
  if (!details) return <p className="rounded-2xl border p-4 text-sm text-gray-500 dark:border-gray-700">正在读取详情…</p>
  return <div className="space-y-4 text-sm">
    <section aria-label="习惯概览" className="grid grid-cols-2 gap-3">
      <button type="button" aria-label="编辑习惯排期" onClick={onEditHabit} className="rounded-2xl border border-gray-200 bg-gray-50/70 p-3 text-left hover:border-blue-300 hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 dark:border-gray-700 dark:bg-gray-800/60 dark:hover:border-blue-700 dark:hover:bg-blue-950/30"><p className="text-xs text-gray-500 dark:text-gray-400">排期</p><p className="mt-1 font-semibold">{formatHabitRepeatRule(details.habit.repeat_rule)}</p></button>
      <button type="button" aria-label="编辑习惯分类" onClick={onEditHabit} className="rounded-2xl border border-gray-200 bg-gray-50/70 p-3 text-left hover:border-blue-300 hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 dark:border-gray-700 dark:bg-gray-800/60 dark:hover:border-blue-700 dark:hover:bg-blue-950/30"><p className="text-xs text-gray-500 dark:text-gray-400">分类</p><p className="mt-1 truncate font-semibold">{details.category || '未分类'}</p></button>
    </section>
    <section aria-label="奖励" className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4 dark:border-amber-900 dark:bg-amber-950/20"><h3 className="mb-2 text-sm font-semibold">完成奖励</h3><SourceRewardSummary sourceType="habit" sourceId={String(id)} onEdit={onEditReward} /></section>
    <HabitMonthView id={id} onEditJournal={onEditJournal} refreshKey={refreshKey} />
  </div>
}
