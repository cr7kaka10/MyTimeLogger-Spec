import { useState } from 'react'
import type { Habit } from '@models/Database'
import type { HabitEdits } from '@models/HabitEdits'
import { BottomSheet } from '../../components/common/BottomSheet'

interface Props {
  habit: Habit; busy: boolean; message: string; onClose: () => void
  onSave: (fields: HabitEdits) => Promise<boolean>
}

export function HabitEditor({ habit, busy, message, onClose, onSave }: Props) {
  const [name, setName] = useState(habit.name)
  const [icon, setIcon] = useState(habit.icon || '✅')
  const [difficulty, setDifficulty] = useState(habit.difficulty || 'easy')
  return <BottomSheet open onClose={() => { if (!busy) onClose() }}>
    <form className="space-y-4" onSubmit={async event => {
      event.preventDefault()
      if (await onSave({ name, icon, difficulty })) onClose()
    }}>
      <h3 className="font-bold">编辑本地习惯</h3>
      <label className="block">名称<input className="block w-full rounded border p-2" required value={name} onChange={event => setName(event.target.value)} /></label>
      <label className="block">图标<input className="block w-full rounded border p-2" value={icon} onChange={event => setIcon(event.target.value)} /></label>
      <label className="block">难度<select className="ml-2 rounded border p-2" value={difficulty} onChange={event => setDifficulty(event.target.value)}>
        <option value="trivial">轻松</option><option value="easy">简单</option>
        <option value="medium">中等</option><option value="hard">困难</option>
      </select></label>
      <p className="text-sm text-gray-500">修改难度不会覆盖已配置的奖励。</p>
      {message && <p role="status">{message}</p>}
      <button type="submit" disabled={busy || !name.trim()} className="theme-accent-button rounded px-4 py-2 disabled:opacity-50">{busy ? '保存中…' : '保存'}</button>
      <button type="button" disabled={busy} onClick={onClose} className="ml-3">取消</button>
    </form>
  </BottomSheet>
}
