import { useEffect, useState } from 'react'
import type { Habit } from '@models/Database'
import { getDatabase } from '../../db'
import { useEventRefresh } from '../../hooks/useEventRefresh'
import { LOCAL_HABITS_UPDATED } from '../../hooks/useLocalHabitMutation'
import { BottomSheet } from '../../components/common/BottomSheet'
import { HabitActions } from './HabitActions'

export function LocalHabitHistory() {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<Habit[]>([])
  const [selected, setSelected] = useState<Habit | null>(null)
  const [error, setError] = useState('')
  const refresh = useEventRefresh([LOCAL_HABITS_UPDATED, 'sync-pull-complete'])
  useEffect(() => {
    if (!open) return
    let active = true
    getDatabase().then(db => { if (active) { setRows(db.getArchivedLocalHabits()); setError('') } })
      .catch(reason => { if (active) setError(reason?.message || '历史读取失败') })
    return () => { active = false }
  }, [open, refresh])
  return <>
    <button type="button" className="px-1 text-xs text-gray-500" onClick={() => setOpen(true)}>已删除的本地习惯</button>
    {open && (selected ? <HabitActions habit={selected} onClose={() => setSelected(null)} /> : <BottomSheet open onClose={() => setOpen(false)}>
      <h3 className="mb-3 font-bold">已删除的本地习惯</h3>
      {error ? <p role="alert">{error}</p> : rows.length ? rows.map(row => <button key={row.id} type="button" className="block py-2" onClick={() => setSelected(row)}>{row.icon} {row.name}</button>) : <p>暂无已删除的本地习惯</p>}
    </BottomSheet>)}
  </>
}
