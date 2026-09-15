// ui/src/components/Habits/HabitAddSheet.tsx
import { memo, useCallback, useState } from 'react'
import type { HabitFormData } from '../../types'
import { BottomSheet } from '../common/BottomSheet'

const EMOJIS = ['✅', '🏃', '📖', '💧', '🧘', '🎯', '💤', '🍎', '✍️', '🎵', '📵', '🌱', '💪', '🧹', '☀️', '🙏', '🚶', '🏋️', '🎨', '📝']
const DIFFICULTIES: Array<{ key: HabitFormData['difficulty']; label: string; coins: string }> = [
  { key: 'trivial', label: '微小', coins: '0.5' },
  { key: 'easy', label: '简单', coins: '1' },
  { key: 'medium', label: '中等', coins: '2.5' },
  { key: 'hard', label: '困难', coins: '5' },
]

interface Props {
  habit?: HabitFormData
  onSave: (data: HabitFormData) => void
  onClose: () => void
}

export const HabitAddSheet = memo(({ habit, onSave, onClose }: Props) => {
  const [title, setTitle] = useState(habit?.title || '')
  const [icon, setIcon] = useState(habit?.icon || '✅')
  const [difficulty, setDifficulty] = useState<HabitFormData['difficulty']>(habit?.difficulty || 'easy')

  const handleSave = useCallback(() => {
    if (!title.trim()) return
    onSave({ id: habit?.id, title: title.trim(), icon, difficulty })
  }, [title, icon, difficulty, habit, onSave])

  return (
    <BottomSheet open onClose={onClose}>
      <div className="space-y-4 p-4">
        <h3 className="text-lg font-bold text-gray-900">{habit?.id ? '编辑习惯' : '新建习惯'}</h3>
        <input type="text" value={title} onChange={e => setTitle(e.target.value)} placeholder="习惯名称" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        <div>
          <span className="text-xs text-gray-400">图标</span>
          <div className="mt-1 flex flex-wrap gap-2">{EMOJIS.map(e => (
            <button key={e} type="button" onClick={() => setIcon(e)} className={`h-9 w-9 rounded-lg text-lg ${icon === e ? 'bg-blue-100 ring-2 ring-blue-400' : 'bg-gray-50 active:bg-gray-100'}`}>{e}</button>
          ))}</div>
        </div>
        <div>
          <span className="text-xs text-gray-400">难度</span>
          <div className="mt-1 flex gap-2">{DIFFICULTIES.map(d => (
            <button key={d.key} type="button" onClick={() => setDifficulty(d.key)} className={`flex-1 rounded-lg py-2 text-center text-sm ${difficulty === d.key ? 'bg-blue-500 text-white font-semibold' : 'bg-gray-50 text-gray-600'}`}>{d.label} +{d.coins}</button>
          ))}</div>
        </div>
        <button onClick={handleSave} className="h-12 w-full rounded-xl bg-blue-500 text-base font-semibold text-white active:bg-blue-600">保存</button>
      </div>
    </BottomSheet>
  )
})

HabitAddSheet.displayName = 'HabitAddSheet'
