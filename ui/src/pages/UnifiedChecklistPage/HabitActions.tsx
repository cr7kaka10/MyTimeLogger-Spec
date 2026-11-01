import { useState } from 'react'
import type { Habit } from '@models/Database'
import { BottomSheet } from '../../components/common/BottomSheet'
import { HabitEditor } from './HabitEditor'
import { HabitDetails } from './HabitDetails'
import { HabitJournalSheet } from './HabitJournalSheet'
import { useLocalHabitMutation } from '../../hooks/useLocalHabitMutation'
import type { HabitEdits, HabitWindowEdits } from '@models/HabitEdits'
import { getCurrentTimerClient, syncNow } from '../../db'

interface Props { habit: Habit; categories?: Array<{ id: number; name: string; is_active?: number }>; onClose: () => void; onEditReward: (habit: Habit) => void }

export function HabitActions({ habit, categories = [], onClose, onEditReward }: Props) {
  const [mode, setMode] = useState<'view' | 'edit' | 'delete'>('view')
  const [journal, setJournal] = useState<{ date: string; note: string } | null>(null)
  const [journalRefresh, setJournalRefresh] = useState(0)
  const [journalPrompt, setJournalPrompt] = useState(habit.journal_prompt_enabled !== 0)
  const [windowError, setWindowError] = useState('')
  const mutation = useLocalHabitMutation()
  const save = async (fields: HabitEdits, window: HabitWindowEdits) => {
    setWindowError('')
    const changed = window.start_minute !== (habit.window_start_minute ?? null) || window.end_minute !== (habit.window_end_minute ?? null)
    if (changed) {
      const api = getCurrentTimerClient()
      if (!api) { setWindowError('尚未连接服务器，时间段未保存'); return false }
      const response = await api.put(`/api/habits/${encodeURIComponent(String(habit.id))}/window`, window)
      if (!response.ok || response.data?.status !== 'ok') {
        setWindowError('时间段未保存，请检查网络或输入后重试'); return false
      }
      await syncNow({ reason: 'habit-window-update' }).catch(() => ({ ok: false }))
    }
    return mutation.run(db => db.updateHabit(habit.id, fields, habit.updated_at), 'update')
  }
  if (journal) return <HabitJournalSheet habitId={String(habit.id)} name={habit.name} date={journal.date} initialNote={journal.note}
    onClose={() => setJournal(null)} onSaved={() => setJournalRefresh(value => value + 1)} />
  if (mode === 'edit') return <HabitEditor habit={habit} categories={categories} {...mutation} message={windowError || mutation.message} onClose={onClose}
    onSave={save} />
  return <BottomSheet open ariaLabel={`管理习惯 ${habit.name}`} onClose={() => { if (!mutation.busy) onClose() }} panelClass="overflow-hidden p-0 sm:mb-6 sm:max-w-xl sm:rounded-3xl">
    <div className="flex max-h-[calc(100dvh-1rem)] flex-col text-gray-900 dark:text-gray-100">
      <header className="flex items-center gap-3 border-b border-gray-200 px-5 py-4 dark:border-gray-700">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-blue-50 text-2xl dark:bg-blue-950/40">{habit.icon || '✅'}</span>
        <div className="min-w-0 flex-1"><p className="text-xs font-medium text-gray-500 dark:text-gray-400">习惯管理</p><h2 className="truncate text-lg font-bold">{habit.name}</h2></div>
        <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">进行中</span>
        <button type="button" disabled={mutation.busy} onClick={onClose} aria-label="关闭习惯管理" className="rounded-xl p-2 text-xl text-gray-400 hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 dark:hover:bg-gray-800">×</button>
      </header>
      <main className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
        <label className="flex items-center justify-between gap-3 rounded-xl border border-gray-200 p-3 text-sm dark:border-gray-700"><span>打卡后弹出日志</span><input type="checkbox" checked={journalPrompt} disabled={mutation.busy} onChange={event => { const enabled = event.target.checked; void mutation.run(db => db.setHabitJournalPrompt(habit.id, enabled)).then(ok => { if (ok) setJournalPrompt(enabled) }) }} aria-label="本习惯打卡后弹出日志" /></label>
        <HabitDetails id={habit.id} onEditHabit={() => setMode('edit')} onEditReward={() => onEditReward(habit)} onEditJournal={(date, note) => setJournal({ date, note })} refreshKey={journalRefresh} />
        {mode === 'delete' ? <section aria-label="删除确认" className="rounded-2xl border border-red-200 bg-red-50/70 p-4 dark:border-red-900 dark:bg-red-950/30">
          <h3 className="font-semibold text-red-700 dark:text-red-300">从清单隐藏，保留历史</h3><p className="mt-1 text-sm text-red-600 dark:text-red-300">历史打卡和已结算奖励不会删除，变更会同步到其他设备。</p>
          <div className="mt-3 flex gap-2"><button type="button" disabled={mutation.busy} onClick={() => void mutation.run(db => db.deleteHabit(habit.id, habit.updated_at), 'delete').then(ok => { if (ok) onClose() })} className="rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">确认删除</button><button type="button" disabled={mutation.busy} onClick={() => setMode('view')} className="rounded-xl border px-4 py-2 text-sm font-semibold">取消</button></div>
        </section> : <section aria-label="危险操作" className="border-t border-gray-200 pt-4 dark:border-gray-700"><button type="button" className="text-sm font-medium text-red-600 hover:text-red-700 dark:text-red-400" onClick={() => setMode('delete')}>删除习惯</button></section>}
        {mutation.message && <p role="status" className="text-sm text-red-600 dark:text-red-400">{mutation.message}</p>}
      </main>
      {mode === 'view' && <footer className="grid grid-cols-2 gap-2 border-t border-gray-200 p-4 dark:border-gray-700"><button type="button" onClick={() => setMode('edit')} className="theme-accent-button rounded-xl px-4 py-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500">编辑习惯</button><button type="button" onClick={() => onEditReward(habit)} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 dark:border-gray-700 dark:hover:bg-gray-800">奖励设置</button></footer>}
    </div>
  </BottomSheet>
}
