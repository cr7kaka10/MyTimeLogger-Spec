// ui/src/components/Habits/HabitMonthCalendarDialog.tsx
import { memo, useMemo, useState, useEffect } from 'react'
import { BottomSheet } from '../common/BottomSheet'
import { getDatabase } from '../../db'

interface HabitMonthCalendarDialogProps {
  habit: { id: number | string; name: string; icon: string }
  onClose: () => void
  onToggleCheckin: (habitId: number | string, dateStr: string) => void
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

export const HabitMonthCalendarDialog = memo(({ habit, onClose, onToggleCheckin }: HabitMonthCalendarDialogProps) => {
  const [currentMonth, setCurrentMonth] = useState(() => {
    const today = new Date()
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  })
  const [checkinsMap, setCheckinsMap] = useState<Record<string, number>>({})
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  useEffect(() => {
    getDatabase().then(db => {
      if (typeof (db as any).getMonthlyCheckins === 'function') {
        setCheckinsMap((db as any).getMonthlyCheckins(habit.id, currentMonth))
      }
    })
  }, [habit.id, currentMonth, refreshTrigger])

  const { year, month, days, todayStr } = useMemo(() => {
    const [yStr, mStr] = currentMonth.split('-')
    const y = parseInt(yStr)
    const m = parseInt(mStr) - 1 // 0-indexed month
    const firstDay = new Date(y, m, 1)
    const lastDay = new Date(y, m + 1, 0)
    const startOffset = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1 // 周一为0

    const formatLocalDate = (d: Date) => {
      const year = d.getFullYear()
      const month = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      return `${year}-${month}-${day}`
    }

    const cells: Array<{ date: string; day: number; isCurrentMonth: boolean }> = []
    // 上月填充
    for (let i = 0; i < startOffset; i++) {
      const prev = new Date(y, m, -startOffset + i + 1)
      cells.push({ date: formatLocalDate(prev), day: prev.getDate(), isCurrentMonth: false })
    }
    // 当月
    for (let i = 1; i <= lastDay.getDate(); i++) {
      const cur = new Date(y, m, i)
      cells.push({ date: formatLocalDate(cur), day: i, isCurrentMonth: true })
    }

    return {
      year: y,
      month: m,
      days: cells,
      todayStr: formatLocalDate(new Date())
    }
  }, [currentMonth])

  const handlePrevMonth = () => {
    const [yStr, mStr] = currentMonth.split('-')
    let y = parseInt(yStr)
    let m = parseInt(mStr) - 1
    if (m === 0) {
      m = 12
      y -= 1
    }
    setCurrentMonth(`${y}-${String(m).padStart(2, '0')}`)
  }

  const handleNextMonth = () => {
    const [yStr, mStr] = currentMonth.split('-')
    let y = parseInt(yStr)
    let m = parseInt(mStr) + 1
    if (m === 13) {
      m = 1
      y += 1
    }
    setCurrentMonth(`${y}-${String(m).padStart(2, '0')}`)
  }

  const handleCellClick = (date: string) => {
    if (date > todayStr) return
    onToggleCheckin(habit.id, date)
    setRefreshTrigger(prev => prev + 1)
  }

  return (
    <BottomSheet open onClose={onClose}>
      <div className="flex flex-col gap-4">
        <header className="flex items-center justify-between border-b border-gray-100 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-2xl">{habit.icon}</span>
            <div>
              <h2 className="text-sm font-bold text-gray-900">{habit.name}</h2>
              <p className="text-[10px] text-gray-400">历史月历打卡记录</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-gray-50 px-3 py-1 text-xs font-semibold text-gray-500 active:bg-gray-100"
          >
            确定
          </button>
        </header>

        <div className="flex items-center justify-between px-2">
          <button
            type="button"
            onClick={handlePrevMonth}
            className="text-gray-500 hover:text-gray-950 text-xs font-semibold p-1"
          >
            ‹ 上月
          </button>
          <span className="text-xs font-bold text-gray-700">{year}年{month + 1}月</span>
          <button
            type="button"
            onClick={handleNextMonth}
            className="text-gray-500 hover:text-gray-950 text-xs font-semibold p-1"
          >
            下月 ›
          </button>
        </div>

        <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-gray-400 font-semibold">
          {WEEKDAYS.map(w => <div key={w} className="py-1">{w}</div>)}
        </div>

        <div className="grid grid-cols-7 gap-1.5">
          {days.map(cell => {
            const status = checkinsMap[cell.date] ?? 0
            const isToday = cell.date === todayStr
            const isFuture = cell.date > todayStr

            let bgClass = 'bg-gray-50 text-gray-700'
            let text: string | number = cell.day
            if (!cell.isCurrentMonth) {
              bgClass = 'text-gray-150 cursor-not-allowed opacity-30'
            } else if (status === 2) {
              bgClass = 'bg-green-500 text-white font-bold'
              text = '✓'
            } else if (status === 1) {
              bgClass = 'bg-red-500 text-white font-bold'
              text = '✕'
            } else if (isToday) {
              bgClass = 'bg-blue-50 text-blue-600 font-bold border border-blue-200'
            } else if (isFuture) {
              bgClass = 'bg-transparent text-gray-300 cursor-not-allowed'
            }

            return (
              <button
                key={cell.date}
                type="button"
                disabled={!cell.isCurrentMonth || isFuture}
                onClick={() => handleCellClick(cell.date)}
                className={`flex h-8 items-center justify-center rounded-lg text-xs transition-all active:scale-95 ${bgClass}`}
                title={cell.isCurrentMonth && !isFuture ? `${cell.date}: 点击打卡状态转换` : ''}
              >
                {text}
              </button>
            )
          })}
        </div>
      </div>
    </BottomSheet>
  )
})

HabitMonthCalendarDialog.displayName = 'HabitMonthCalendarDialog'
