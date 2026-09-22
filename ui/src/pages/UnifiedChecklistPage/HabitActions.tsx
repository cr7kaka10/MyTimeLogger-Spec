import { useState } from 'react'
import type { Habit } from '@models/Database'
import { BottomSheet } from '../../components/common/BottomSheet'
import { HabitEditor } from './HabitEditor'
import { HabitDetails } from './HabitDetails'
import { useLocalHabitMutation } from '../../hooks/useLocalHabitMutation'

export function HabitActions({ habit, onClose }: { habit: Habit; onClose: () => void }) {
  const [mode, setMode] = useState<'view' | 'edit' | 'delete'>('view')
  const mutation = useLocalHabitMutation()
  if (mode === 'edit') return <HabitEditor habit={habit} {...mutation} onClose={onClose}
    onSave={fields => mutation.run(db => db.updateHabit(habit.id, fields, habit.updated_at))} />
  return <BottomSheet open onClose={() => { if (!mutation.busy) onClose() }}>
    <div className="space-y-4">
      <h3 className="font-bold">{habit.icon} {habit.name}</h3>
      <p>{habit.source === 'local' ? '本地习惯' : '滴答镜像'} · {habit.is_active === 0 ? '活动' : '已逻辑删除'}</p>
      {mode === 'delete' ? <>
        <p>确认删除这个本地习惯？将从活动清单隐藏，保留历史打卡和已结算奖励，并同步到其他设备。</p>
        <button type="button" disabled={mutation.busy} className="rounded bg-red-600 px-4 py-2 text-white" onClick={() => void mutation.run(db => db.deleteHabit(habit.id, habit.updated_at)).then(ok => { if (ok) onClose() })}>确认逻辑删除</button>
        <button type="button" disabled={mutation.busy} className="ml-3" onClick={() => setMode('view')}>取消</button>
      </> : <>
        <p>难度：{habit.difficulty} · 排期：{habit.repeat_rule || '每天'}</p>
        {habit.source === 'local' && <HabitDetails id={habit.id} />}
        {habit.source === 'local' && habit.is_active === 0 && <div className="flex gap-4">
          <button type="button" onClick={() => setMode('edit')}>编辑</button>
          <button type="button" className="text-red-600" onClick={() => setMode('delete')}>删除（保留历史）</button>
        </div>}
        {habit.source !== 'local' && <p>归档、恢复与删除请在滴答清单操作。</p>}
      </>}
      {mutation.message && <p role="status">{mutation.message}</p>}
      <button type="button" disabled={mutation.busy} onClick={onClose}>关闭</button>
    </div>
  </BottomSheet>
}
