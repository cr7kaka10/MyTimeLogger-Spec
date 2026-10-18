import { useState } from 'react'
import type { Habit } from '@models/Database'
import type { HabitEdits } from '@models/HabitEdits'
import { BottomSheet } from '../../components/common/BottomSheet'
import { buildHabitRepeatRule, HABIT_WEEKDAYS, parseHabitRepeatRule, type HabitWeekday } from '@core/HabitSchedule'

interface Props {
  habit: Habit; categories?: Array<{ id: number; name: string; is_active?: number }>; busy: boolean; message: string; onClose: () => void
  onSave: (fields: HabitEdits) => Promise<boolean>
}

export function HabitEditor({ habit, categories = [], busy, message, onClose, onSave }: Props) {
  const [name, setName] = useState(habit.name)
  const [icon, setIcon] = useState(habit.icon || '✅')
  const initialDays = parseHabitRepeatRule(habit.repeat_rule)
  const [daily, setDaily] = useState(initialDays === null)
  const [days, setDays] = useState<HabitWeekday[]>(initialDays || [])
  const [categoryId, setCategoryId] = useState(categories.some(item => item.is_active !== 0 && Number(item.id) === Number(habit.category_id)) ? String(habit.category_id) : '')
  return <BottomSheet open ariaLabel="编辑本地习惯" onClose={() => { if (!busy) onClose() }} panelClass="overflow-hidden p-0 sm:mb-6 sm:max-w-lg sm:rounded-3xl">
    <form className="text-gray-900 dark:text-gray-100" onSubmit={async event => {
      event.preventDefault()
      if (await onSave({ name, icon, repeat_rule: daily ? 'FREQ=DAILY' : buildHabitRepeatRule(days), category_id: categoryId ? Number(categoryId) : null })) onClose()
    }}>
      <header className="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-gray-700"><div><p className="text-xs text-gray-500 dark:text-gray-400">习惯管理</p><h2 className="text-lg font-bold">编辑本地习惯</h2></div><button type="button" disabled={busy} onClick={onClose} aria-label="关闭编辑" className="rounded-xl p-2 text-xl text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">×</button></header>
      <div className="space-y-4 p-5"><label className="block text-sm font-medium" htmlFor="habit-name">名称<input id="habit-name" className="mt-2 block w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 outline-none focus:border-blue-500 dark:border-gray-700 dark:bg-gray-950" required value={name} onChange={event => setName(event.target.value)} /></label>
      <label className="block text-sm font-medium" htmlFor="habit-icon">图标<input id="habit-icon" className="mt-2 block w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-xl outline-none focus:border-blue-500 dark:border-gray-700 dark:bg-gray-950" value={icon} onChange={event => setIcon(event.target.value)} /></label>
      <fieldset className="rounded-xl border border-gray-200 p-3 dark:border-gray-700"><legend className="px-1 text-sm font-medium">排期</legend><label className="flex gap-2"><input type="checkbox" checked={daily} onChange={event => setDaily(event.target.checked)} />每天</label>{!daily && <div className="mt-3 flex flex-wrap gap-2">{HABIT_WEEKDAYS.map(([code, label]) => <label key={code} className="rounded-lg border px-2 py-1"><input className="mr-1" type="checkbox" checked={days.includes(code)} onChange={() => setDays(current => current.includes(code) ? current.filter(item => item !== code) : [...current, code])} />周{label}</label>)}</div>}</fieldset>
      <label className="block text-sm font-medium" htmlFor="habit-category">分类<select id="habit-category" className="mt-2 block w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 dark:border-gray-700 dark:bg-gray-950" value={categoryId} onChange={event => setCategoryId(event.target.value)}><option value="">未分类</option>{categories.filter(category => category.is_active !== 0).map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      {message && <p role="status" className="text-sm text-red-600 dark:text-red-400">{message}</p>}</div>
      <footer className="grid grid-cols-2 gap-2 border-t border-gray-200 p-4 dark:border-gray-700"><button type="button" disabled={busy} onClick={onClose} className="rounded-xl border border-gray-200 px-4 py-3 text-sm font-semibold disabled:opacity-50 dark:border-gray-700">取消</button><button type="submit" disabled={busy || !name.trim()} className="theme-accent-button rounded-xl px-4 py-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 disabled:opacity-50">{busy ? '保存中…' : '保存更改'}</button></footer>
    </form>
  </BottomSheet>
}
