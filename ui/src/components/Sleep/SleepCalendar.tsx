// ui/src/components/Sleep/SleepCalendar.tsx
import { memo, useMemo } from 'react'

interface SleepDay {
  date: string
  sleep_score?: number
}

interface Props {
  data: SleepDay[]
  selectedDate: string
  onSelectDate: (date: string) => void
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

export const SleepCalendar = memo(({ data, selectedDate, onSelectDate }: Props) => {
  const scoreMap = useMemo(() => {
    const m: Record<string, number> = {}
    for (const d of data) {
      if (d.sleep_score != null) m[d.date] = d.sleep_score
    }
    return m
  }, [data])

  const { year, month, days } = useMemo(() => {
    const d = new Date(selectedDate)
    const y = d.getFullYear(); const m = d.getMonth()
    const firstDay = new Date(y, m, 1)
    const lastDay = new Date(y, m + 1, 0)
    const offset = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1
    const cells: Array<{ date: string; day: number; isCurrentMonth: boolean }> = []
    for (let i = 0; i < offset; i++) {
      const prev = new Date(y, m, -offset + i + 1)
      cells.push({ date: prev.toISOString().slice(0, 10), day: prev.getDate(), isCurrentMonth: false })
    }
    for (let i = 1; i <= lastDay.getDate(); i++) {
      cells.push({ date: new Date(y, m, i).toISOString().slice(0, 10), day: i, isCurrentMonth: true })
    }
    return { year: y, month: m, days: cells }
  }, [selectedDate])

  const dotColor = (score: number) => {
    if (score >= 80) return 'bg-green-400'
    if (score >= 60) return 'bg-yellow-400'
    return 'bg-red-400'
  }

  return (
    <div className="theme-surface rounded-xl border p-3">
      <div className="text-center text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">{year}年{month + 1}月 睡眠质量</div>
      <div className="grid grid-cols-7 gap-1 text-center text-xs text-gray-400 mb-1">
        {WEEKDAYS.map(w => <div key={w}>{w}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {days.map(cell => {
          const score = scoreMap[cell.date]
          const isSel = cell.date === selectedDate
          return (
            <button key={cell.date} type="button" onClick={() => cell.isCurrentMonth && onSelectDate(cell.date)}
              disabled={!cell.isCurrentMonth}
              className={`relative flex flex-col items-center justify-center h-8 rounded-md text-xs
                ${!cell.isCurrentMonth ? 'text-gray-200 dark:text-gray-600' : ''}
                ${isSel ? 'bg-blue-500 text-white font-bold' : 'active:bg-gray-100 dark:active:bg-gray-700'}`}>
              {cell.day}
              {score != null && (
                <span className={`absolute bottom-0.5 h-1.5 w-1.5 rounded-full ${dotColor(score)}`} />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
})

SleepCalendar.displayName = 'SleepCalendar'
