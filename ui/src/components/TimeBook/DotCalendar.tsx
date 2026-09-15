// ui/src/components/TimeBook/DotCalendar.tsx
import { memo, useMemo } from 'react'
import { dateToShanghaiDateString } from '../../utils/shanghaiDate'

interface DotCalendarProps {
  selectedDate: string       // YYYY-MM-DD
  markedDates: Set<string>   // 有记录的日期集合
  sleepStatusMap?: Record<string, number>
  onSelectDate: (date: string) => void
  onNavigateToSleep?: (date: string) => void
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

export const DotCalendar = memo(({ selectedDate, markedDates, sleepStatusMap, onSelectDate, onNavigateToSleep }: DotCalendarProps) => {
  const { year, month, days, today } = useMemo(() => {
    const [y, selectedMonth] = selectedDate.split('-').map(Number)
    const m = selectedMonth - 1
    const firstDay = new Date(y, m, 1)
    const lastDay = new Date(y, m + 1, 0)
    const startOffset = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1 // 周一为0

    const cells: Array<{ date: string; day: number; isCurrentMonth: boolean }> = []
    // 上月填充
    for (let i = 0; i < startOffset; i++) {
      const prev = new Date(y, m, -startOffset + i + 1)
      const date = `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, '0')}-${String(prev.getDate()).padStart(2, '0')}`
      cells.push({ date, day: prev.getDate(), isCurrentMonth: false })
    }
    // 当月
    for (let i = 1; i <= lastDay.getDate(); i++) {
      const date = `${y}-${String(m + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`
      cells.push({ date, day: i, isCurrentMonth: true })
    }

    return { year: y, month: m, days: cells, today: dateToShanghaiDateString(new Date()) }
  }, [selectedDate])

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-3">
      <div className="text-center text-sm font-semibold text-gray-700 mb-2">
        {year}年{month + 1}月
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-xs text-gray-400 mb-1">
        {WEEKDAYS.map(w => <div key={w}>{w}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {days.map(cell => {
          const isSelected = cell.date === selectedDate
          const isToday = cell.date === today
          const hasRecord = markedDates.has(cell.date)
          const sleepStatus = sleepStatusMap?.[cell.date] ?? 0

          let bgStyle: React.CSSProperties = {}
          if (cell.isCurrentMonth) {
            if (sleepStatus === 1) {
              bgStyle = { background: 'linear-gradient(to right, rgba(168, 85, 247, 0.15) 50%, transparent 50%)' }
            } else if (sleepStatus === 2) {
              bgStyle = { background: 'linear-gradient(to right, rgba(168, 85, 247, 0.15) 50%, rgba(234, 179, 8, 0.15) 50%)' }
            }
          }

          return (
            <button
              key={cell.date}
              type="button"
              onClick={() => {
                if (cell.isCurrentMonth) {
                  onSelectDate(cell.date)
                  if ((sleepStatus === 1 || sleepStatus === 2) && onNavigateToSleep) {
                    onNavigateToSleep(cell.date)
                  }
                }
              }}
              style={bgStyle}
              disabled={!cell.isCurrentMonth}
              className={`relative flex flex-col items-center justify-center h-8 rounded-md text-xs
                ${!cell.isCurrentMonth ? 'text-gray-200' : ''}
                ${isSelected && !sleepStatus ? 'bg-blue-500 text-white font-bold' : ''}
                ${isSelected && sleepStatus ? 'ring-2 ring-blue-500 font-bold text-gray-900 bg-white/50' : ''}
                ${isToday && !isSelected ? 'font-bold text-blue-600' : ''}
                ${cell.isCurrentMonth && !isSelected ? 'active:bg-gray-100' : ''}
              `}
            >
              {cell.day}
              {hasRecord && !isSelected && (
                <span className="absolute bottom-0.5 h-1 w-1 rounded-full bg-green-400" />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
})

DotCalendar.displayName = 'DotCalendar'
