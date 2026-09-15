import { useEffect, useMemo, useState } from 'react'
import type { TaskItem } from '../../types'
import { useSourceRewards } from '../../hooks/useSourceRewards'
import { SourceRewardEditor } from '../Rewards/SourceRewardEditor'

type Patch = { title?: string; startDate?: string | null; dueDate?: string | null }
type Props = { task: TaskItem | null; onClose: () => void; onSave: (task: TaskItem, patch: Patch) => Promise<{ status: string; error_code?: string } | null> }

const inputDate = (value?: string | null) => value ? value.replace(' ', 'T').slice(0, 16) : ''
const providerDate = (value: string) => value ? `${value}:00` : null

function postpone(value: string, days: number): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})$/)
  if (!match) return value
  const day = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days))
  return `${day.getUTCFullYear()}-${String(day.getUTCMonth() + 1).padStart(2, '0')}-${String(day.getUTCDate()).padStart(2, '0')}T${match[4]}`
}

export function TaskEditDialog({ task, onClose, onSave }: Props) {
  const initial = useMemo(() => ({ title: task?.title || '', start: inputDate(task?.start_date), due: inputDate(task?.provider_due_date) }), [task])
  const [draft, setDraft] = useState(initial)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [coins, setCoins] = useState(0)
  const [editingItem, setEditingItem] = useState(false)
  const sourceReward = useSourceRewards('checklist_task', task?.id || '', Boolean(task))
  useEffect(() => { setDraft(initial); setError('') }, [initial])
  useEffect(() => { if (sourceReward.summary) setCoins(sourceReward.summary.coins) }, [sourceReward.summary])
  if (!task) return null
  const zone = task.time_zone || 'Asia/Shanghai'
  const canPostpone = Boolean(draft.start || draft.due)
  const applyPostpone = (days: number) => setDraft(current => ({ ...current, start: current.start ? postpone(current.start, days) : '', due: current.due ? postpone(current.due, days) : '' }))
  const save = async () => {
    if (!draft.title.trim()) return setError('任务标题不能为空')
    if (draft.start && draft.due && draft.start > draft.due) return setError('开始时间不能晚于截止时间')
    const patch: Patch = {}
    if (draft.title !== initial.title) patch.title = draft.title.trim()
    if (draft.start !== initial.start) patch.startDate = providerDate(draft.start)
    if (draft.due !== initial.due) patch.dueDate = providerDate(draft.due)
    const rewardChanged = Boolean(sourceReward.summary && coins !== sourceReward.summary.coins)
    if (!Object.keys(patch).length && !rewardChanged) return onClose()
    setSaving(true); setError('')
    try {
      if (Object.keys(patch).length) {
        const result = await onSave(task, patch)
        if (result?.status !== 'confirmed') return setError(result?.status === 'conflict' ? '任务已在其他设备更新，请刷新后重新编辑' : result?.status === 'unknown' ? '更新结果未确认，请刷新后核对任务' : result?.error_code === 'task_timezone_unavailable' ? '服务器缺少任务时区数据，请稍后重试' : '更新失败，请检查任务后重试')
      }
      if (rewardChanged) await sourceReward.saveCoins(coins)
      onClose()
    } catch (reason: any) { setError(reason?.message || '奖励保存失败，请修正后重试') }
    finally { setSaving(false) }
  }
  return <><div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4" onClick={onClose}>
    <section className="w-full max-w-md space-y-4 rounded-t-lg bg-white p-5 shadow-xl sm:rounded-lg" onClick={event => event.stopPropagation()} aria-label="更新任务">
      <div className="flex items-center justify-between"><h2 className="text-base font-semibold text-gray-900">更新任务</h2><button type="button" onClick={onClose} className="h-8 w-8 text-gray-500" title="关闭">×</button></div>
      <label className="block text-sm text-gray-700">任务标题<input value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} className="mt-1 h-10 w-full rounded border border-gray-300 px-3" /></label>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-sm text-gray-700">开始日期<input type="datetime-local" value={draft.start} onChange={event => setDraft({ ...draft, start: event.target.value })} className="mt-1 h-10 w-full rounded border border-gray-300 px-2" /></label>
        <label className="text-sm text-gray-700">截止日期<input type="datetime-local" value={draft.due} onChange={event => setDraft({ ...draft, due: event.target.value })} className="mt-1 h-10 w-full rounded border border-gray-300 px-2" /></label>
      </div>
      <div className="flex items-center justify-between text-xs text-gray-500"><span>{task.is_all_day ? '全天任务' : '定时任务'}</span><span>{zone}</span></div>
      <div className="flex gap-2"><button type="button" disabled={!canPostpone} onClick={() => applyPostpone(1)} className="h-9 flex-1 rounded border border-blue-200 text-xs text-blue-700 disabled:opacity-40">推迟 1 天</button><button type="button" disabled={!canPostpone} onClick={() => applyPostpone(2)} className="h-9 flex-1 rounded border border-blue-200 text-xs text-blue-700 disabled:opacity-40">推迟 2 天</button><button type="button" disabled={!canPostpone} onClick={() => applyPostpone(7)} className="h-9 flex-1 rounded border border-blue-200 text-xs text-blue-700 disabled:opacity-40">推迟 7 天</button></div>
      <label className="block text-sm text-gray-700">金币奖励<input aria-label="金币奖励" type="number" min={0} value={coins} onChange={event => setCoins(Number(event.target.value))} className="mt-1 h-10 w-full rounded border border-gray-300 px-3" /></label>
      <div className="flex items-center justify-between rounded border border-gray-200 px-3 py-2 text-sm"><span>物品奖励：{sourceReward.summary?.itemReward ? `${sourceReward.summary.itemReward.icon} ${sourceReward.summary.itemReward.title}` : '未设置'}</span><button type="button" onClick={() => setEditingItem(true)} className="font-semibold text-blue-600">设置</button></div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex justify-end gap-2"><button type="button" onClick={onClose} className="h-10 px-4 text-sm text-gray-600">取消</button><button type="button" disabled={saving} onClick={save} className="h-10 rounded bg-blue-600 px-4 text-sm font-medium text-white disabled:opacity-50">{saving ? '确认中…' : '保存'}</button></div>
    </section>
  </div>
    {editingItem && <SourceRewardEditor sourceType="checklist_task" sourceId={task.id} sourceTitle={task.title} onClose={() => setEditingItem(false)} />}
  </>
}
