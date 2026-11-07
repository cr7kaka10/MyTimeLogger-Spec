import { useEffect, useMemo, useState } from 'react'
import type { HabitCheckin } from '@models/Database'
import { getDatabase } from '../../db'
import { dateToShanghaiDateString } from '../../utils/shanghaiDate'

interface Props { id: string | number; onEditJournal: (date: string, note: string) => void; refreshKey?: number }
const weekdays = ['一', '二', '三', '四', '五', '六', '日']
const moveMonth = (month: string, delta: number) => {
  const [year, part] = month.split('-').map(Number)
  const date = new Date(year, part - 1 + delta, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function HabitMonthView({ id, onEditJournal, refreshKey = 0 }: Props) {
  const [month, setMonth] = useState(() => dateToShanghaiDateString(new Date()).slice(0, 7))
  const [rows, setRows] = useState<HabitCheckin[]>([])
  const [loadedKey, setLoadedKey] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setRows([]); setSelected(null); setError('')
    getDatabase().then(db => { if (active) { setRows(db.getHabitMonthCheckins(id, month)); setLoadedKey(`${id}:${month}:${refreshKey}`) } })
      .catch(reason => { if (active) setError(reason?.message || '打卡记录读取失败') })
    return () => { active = false }
  }, [id, month, refreshKey])
  const cells = useMemo(() => {
    const [year, part] = month.split('-').map(Number)
    const offset = (new Date(year, part - 1, 1).getDay() + 6) % 7
    const days = new Date(year, part, 0).getDate()
    return [...Array(offset).fill(null), ...Array.from({ length: days }, (_, index) => `${month}-${String(index + 1).padStart(2, '0')}`)] as (string | null)[]
  }, [month])
  const currentRows = loadedKey === `${id}:${month}:${refreshKey}` ? rows : []
  const byDate = new Map(currentRows.map(row => [row.checkin_date, row]))
  const visible = selected ? currentRows.filter(row => row.checkin_date === selected) : currentRows
  return <section aria-label="月打卡记录" className="rounded-2xl border border-gray-200 p-3 dark:border-gray-700">
    <div className="mb-3 flex items-center justify-between"><button type="button" aria-label="上个月" onClick={() => setMonth(moveMonth(month, -1))}>‹</button><h3 className="font-semibold">{month.replace('-', '年')}月</h3><button type="button" aria-label="下个月" onClick={() => setMonth(moveMonth(month, 1))}>›</button></div>
    <div className="grid grid-cols-7 gap-1 text-center text-xs">{weekdays.map(day => <span key={day} className="text-gray-400">周{day}</span>)}
      {cells.map((date, index) => date ? <button key={date} type="button" aria-label={`${date} ${byDate.get(date)?.status === 2 ? '成功' : byDate.get(date)?.status === 1 ? '失败' : '未打卡'}`} aria-pressed={selected === date} onClick={() => setSelected(selected === date ? null : date)} className={`aspect-square min-w-0 rounded-full ${selected === date ? 'ring-2 ring-blue-500' : ''} ${byDate.get(date)?.status === 2 ? 'bg-blue-500 text-white' : byDate.get(date)?.status === 1 ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300'}`}>{Number(date.slice(-2))}</button> : <span key={`empty-${index}`} />)}
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
    <div className="mt-4 space-y-2"><h4 className="font-semibold">{month.slice(5)}月打卡日志</h4>{visible.length ? visible.map(row => <div key={row.id} className="rounded-xl bg-gray-50 p-2 text-sm dark:bg-gray-800"><div className="flex justify-between"><span>{row.checkin_date} · {row.status === 2 ? '✓ 成功' : '✕ 失败'}</span>{row.status === 2 && <button type="button" onClick={() => onEditJournal(row.checkin_date, row.note || '')} className="text-blue-600">{row.note ? '编辑日志' : '写日志'}</button>}</div>{row.note && <p className="mt-1 whitespace-pre-wrap break-words">{row.note}</p>}</div>) : <p className="text-sm text-gray-400">{selected ? '该日无打卡记录' : '本月暂无打卡记录'}</p>}</div>
  </section>
}
