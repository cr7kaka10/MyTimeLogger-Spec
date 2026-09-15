// ui/src/pages/UnifiedChecklistPage/WeekCalendar.tsx
// 周历组件 - 显示横向7天日期条（本周一至周日）
import { memo, useMemo, useState } from 'react'
import { dateToShanghaiDateString, tickTickDateToShanghaiDateString } from '../../utils/shanghaiDate'

interface WeekCalendarProps {
  selectedDate: Date
  onDateSelect: (date: Date) => void
  tasks?: any[]
  markedDates?: Set<string>
}

export const WeekCalendar = memo(({ selectedDate, onDateSelect, tasks = [], markedDates }: WeekCalendarProps) => {
  const [isExpanded, setIsExpanded] = useState(false)
  // 计算本周的所有日期（周一到周日）
  const weekDays = useMemo(() => {
    // 安全检查：确保 selectedDate 是有效的 Date 对象
    if (!selectedDate || !(selectedDate instanceof Date) || isNaN(selectedDate.getTime())) {
      return []
    }

    const curr = new Date(selectedDate)
    const day = curr.getDay() // 0=周日, 1=周一, ..., 6=周六
    const diff = day === 0 ? -6 : 1 - day // 计算到本周一的天数差
    
    const monday = new Date(curr)
    monday.setDate(curr.getDate() + diff)
    
    const days = []
    for (let i = 0; i < 7; i++) {
      const date = new Date(monday)
      date.setDate(monday.getDate() + i)
      days.push({
        date,
        dayOfWeek: ['一', '二', '三', '四', '五', '六', '日'][i],
        dayNum: date.getDate(),
        isToday: date.toDateString() === new Date().toDateString(),
        isSelected: date.toDateString() === selectedDate.toDateString(),
      })
    }
    
    return days
  }, [selectedDate])

  // 获取指定日期的任务状态（用于显示蓝点/红点）
  const getTaskStatus = (date: Date | null) => {
    if (!date || !tasks || !Array.isArray(tasks)) {
      return { hasTask: false, isOverdue: false, count: 0 }
    }
    
    try {
      const dateStr = dateToShanghaiDateString(date)
      const today = dateToShanghaiDateString(new Date())
      const isOverdue = dateStr < today
      
      const tasksOnDate = tasks.filter(t => {
        if (!t || t.status === 2) return false
        
        if (t.due_date) {
          try {
            return tickTickDateToShanghaiDateString(t.due_date) === dateStr
          } catch {
            return false
          }
        }
        return false
      })
      
      return {
        hasTask: tasksOnDate.length > 0,
        isOverdue: isOverdue && tasksOnDate.length > 0,
        count: tasksOnDate.length
      }
    } catch {
      return { hasTask: false, isOverdue: false, count: 0 }
    }
  }

  const shiftWeek = (offset: number) => {
    const next = new Date(selectedDate)
    next.setDate(next.getDate() + offset * 7)
    onDateSelect(next)
  }
  const today = new Date()
  const isTodaySelected = dateToShanghaiDateString(selectedDate) === dateToShanghaiDateString(today)
  const returnToToday = () => onDateSelect(new Date())
  const monthDays = useMemo(() => {
    const year = selectedDate.getFullYear(), month = selectedDate.getMonth()
    const offset = (new Date(year, month, 1).getDay() + 6) % 7
    const count = Math.ceil((offset + new Date(year, month + 1, 0).getDate()) / 7) * 7
    return Array.from({ length: count }, (_, index) =>
      index < offset ? null : new Date(year, month, index - offset + 1))
  }, [selectedDate])
  const shiftMonth = (offset: number) => {
    const next = new Date(selectedDate)
    const target = new Date(next.getFullYear(), next.getMonth() + offset + 1, 0)
    next.setDate(Math.min(next.getDate(), target.getDate()))
    next.setMonth(next.getMonth() + offset)
    onDateSelect(next)
  }
  const selectMonth = (value: string) => {
    const [year, month] = value.split('-').map(Number)
    const lastDay = new Date(year, month, 0).getDate()
    onDateSelect(new Date(year, month - 1, Math.min(selectedDate.getDate(), lastDay)))
  }
  // 安卓端后续下拉手势直接调用此入口。
  const toggleExpanded = () => setIsExpanded(value => !value)

  // 如果没有有效日期，显示空状态
  if (weekDays.length === 0) {
    return (
      <div className="theme-surface rounded-2xl border p-3 shadow-sm">
        <p className="text-center text-sm text-gray-400">加载中...</p>
      </div>
    )
  }

  return (
    <div className="theme-surface relative rounded-xl border p-2 shadow-sm" role="navigation" aria-label={isExpanded ? '月历' : '周历'}>
      {!isTodaySelected && <button
        type="button"
        onClick={returnToToday}
        aria-label="返回今天"
        title="返回今天"
        className="theme-surface absolute -top-2.5 right-3 z-10 flex h-5 items-center rounded-full border px-2 text-[10px] font-medium leading-none text-gray-400 shadow-sm transition-colors hover:text-blue-500 dark:text-gray-500 dark:hover:text-blue-300"
      >今天</button>}
      {!isExpanded ? <div className="grid grid-cols-[28px_1fr_28px] items-center gap-1">
        <button type="button" aria-label="上一周" onClick={() => shiftWeek(-1)} className="flex h-10 items-center justify-center rounded-lg text-lg font-bold text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700">‹</button>
        <div className="grid min-w-0 grid-cols-7 gap-1">
        {weekDays.map((day, idx) => {
          const taskStatus = getTaskStatus(day.date)
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onDateSelect(day.date)}
              className={`relative flex min-h-12 flex-col items-center justify-center rounded-lg px-1 py-1 transition-all ${
                day.isSelected
                  ? 'bg-blue-600 text-white font-bold shadow-md'
                  : day.isToday
                  ? 'bg-blue-50 text-blue-600 font-semibold border-2 border-blue-300'
                  : 'hover:bg-gray-50 text-gray-700'
              }`}
              title={taskStatus.hasTask ? `${taskStatus.count} 个任务` : undefined}
              aria-label={`${day.dayOfWeek} ${day.dayNum}日${day.isToday ? '（今天）' : ''}`}
              aria-pressed={day.isSelected}
            >
              <span className="text-[11px] font-medium leading-none">{day.dayOfWeek}</span>
              <span className="mt-1 text-base font-semibold leading-none">{day.dayNum}</span>
              
              {/* 小点标记：蓝点（今天及以后）或红点（过期） */}
              {(taskStatus.hasTask || markedDates?.has(dateToShanghaiDateString(day.date))) && (
                <span 
                  className={`absolute bottom-0.5 h-1 w-1 rounded-full ${
                    day.isSelected 
                      ? 'bg-white' 
                      : taskStatus.isOverdue 
                      ? 'bg-red-500' 
                      : 'bg-blue-500'
                  }`}
                  aria-label={`${taskStatus.count} 个${taskStatus.isOverdue ? '过期' : ''}任务`}
                />
              )}
            </button>
          )
        })}
        </div>
        <button type="button" aria-label="下一周" onClick={() => shiftWeek(1)} className="flex h-10 items-center justify-center rounded-lg text-lg font-bold text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700">›</button>
      </div> : <div className="relative px-7 pb-1">
        <label className="relative mx-auto mb-2 block w-fit cursor-pointer text-sm font-semibold text-gray-700 dark:text-gray-200">
          {selectedDate.getFullYear()}年{selectedDate.getMonth() + 1}月
          <input type="month" value={`${selectedDate.getFullYear()}-${String(selectedDate.getMonth() + 1).padStart(2, '0')}`} onInput={event => selectMonth(event.currentTarget.value)} className="absolute inset-0 cursor-pointer opacity-0" aria-label="选择年月" />
        </label>
        <div className="mb-1 grid grid-cols-7 gap-1 text-center text-xs text-gray-400">{['一','二','三','四','五','六','日'].map(day => <span key={day}>{day}</span>)}</div>
        <div className="grid grid-cols-7 gap-1">
          {monthDays.map((date, index) => date && date.getMonth() === selectedDate.getMonth() ? <button key={date.getTime()} type="button" onClick={() => onDateSelect(date)} className={`relative flex h-8 items-center justify-center rounded-md text-xs ${date.toDateString() === selectedDate.toDateString() ? 'bg-blue-500 font-bold text-white' : date.toDateString() === new Date().toDateString() ? 'font-bold text-blue-600' : 'text-gray-700 active:bg-gray-100 dark:text-gray-200'}`}>{date.getDate()}{(getTaskStatus(date).hasTask || markedDates?.has(dateToShanghaiDateString(date))) && <span className="absolute bottom-0.5 h-1 w-1 rounded-full bg-green-400" />}</button> : <span key={`blank-${index}`} />)}
        </div>
        <button type="button" aria-label="上一月" onClick={() => shiftMonth(-1)} className="absolute left-0 top-1/2 flex h-10 w-7 -translate-y-1/2 items-center justify-center text-lg font-bold text-gray-400">‹</button>
        <button type="button" aria-label="下一月" onClick={() => shiftMonth(1)} className="absolute right-0 top-1/2 flex h-10 w-7 -translate-y-1/2 items-center justify-center text-lg font-bold text-gray-400">›</button>
      </div>}
      <button type="button" onClick={toggleExpanded} aria-label={isExpanded ? '收起为周历' : '展开为月历'} className="mx-auto -mb-1 flex h-3 w-8 items-center justify-center text-xs leading-none text-gray-300 dark:text-gray-500">{isExpanded ? '⌃' : '⌄'}</button>
    </div>
  )
})

WeekCalendar.displayName = 'WeekCalendar'
