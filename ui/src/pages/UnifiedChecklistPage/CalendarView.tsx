// ui/src/pages/UnifiedChecklistPage/CalendarView.tsx
// 可展开的月历视图组件（月历网格）
import { memo, useMemo } from 'react'
import type { TaskItem } from '../../types'

interface CalendarViewProps {
  isExpanded: boolean
  selectedDate: Date
  onDateSelect: (date: Date) => void
  tasks: TaskItem[]
  habits: any[]
  todayCheckins: any[]
}

export const CalendarView = memo(({
  isExpanded,
  selectedDate,
  onDateSelect,
  tasks,
}: CalendarViewProps) => {
  // 生成当前月份的日历网格
  const calendarDays = useMemo(() => {
    const year = selectedDate.getFullYear()
    const month = selectedDate.getMonth()
    
    // 获取当月第一天和最后一天
    const firstDay = new Date(year, month, 1)
    const lastDay = new Date(year, month + 1, 0)
    
    // 获取第一天是星期几 (0=周日, 1=周一, ..., 6=周六)
    const firstDayOfWeek = firstDay.getDay()
    const startDay = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1 // 转换为周一开始
    
    // 计算需要显示的天数
    const daysInMonth = lastDay.getDate()
    const totalCells = Math.ceil((daysInMonth + startDay) / 7) * 7
    
    const days = []
    for (let i = 0; i < totalCells; i++) {
      const dayNum = i - startDay + 1
      if (dayNum > 0 && dayNum <= daysInMonth) {
        const date = new Date(year, month, dayNum)
        days.push({
          date,
          dayNum,
          isCurrentMonth: true,
          isToday: date.toDateString() === new Date().toDateString(),
          isSelected: date.toDateString() === selectedDate.toDateString(),
        })
      } else {
        days.push({
          date: null,
          dayNum: 0,
          isCurrentMonth: false,
          isToday: false,
          isSelected: false,
        })
      }
    }
    
    return days
  }, [selectedDate])

  // 获取指定日期的任务状态（用于显示蓝点/红点）
  const getTaskStatus = (date: Date | null) => {
    if (!date || !tasks || !Array.isArray(tasks)) {
      return { hasTask: false, isOverdue: false, count: 0 }
    }
    
    try {
      // 使用北京时间格式化
      const year = date.getFullYear()
      const month = String(date.getMonth() + 1).padStart(2, '0')
      const day = String(date.getDate()).padStart(2, '0')
      const dateStr = `${year}-${month}-${day}`
      console.log(`=== 检查日期 ${dateStr} 的任务状态 ===`)
      
      const now = new Date()
      const beijingNow = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (8 * 3600000))
      const todayYear = beijingNow.getFullYear()
      const todayMonth = String(beijingNow.getMonth() + 1).padStart(2, '0')
      const todayDay = String(beijingNow.getDate()).padStart(2, '0')
      const today = `${todayYear}-${todayMonth}-${todayDay}`
      const isOverdue = dateStr < today
      
      const tasksOnDate = tasks.filter(t => {
        if (!t || t.status === 2) return false
        
        if (t.due_date) {
          try {
            const cleanDate = t.due_date.replace("+0000", "Z")
            const dueDt = new Date(cleanDate)
            const taskDate = new Date(dueDt.getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10)
            const match = taskDate === dateStr
            
            if (match) {
              console.log(`  ✅ 任务 [${t.title}] 匹配日期 ${dateStr}`)
            }
            
            return match
          } catch {
            return false
          }
        }
        return false
      })
      
      console.log(`  日期 ${dateStr} 共有 ${tasksOnDate.length} 个任务`)
      return {
        hasTask: tasksOnDate.length > 0,
        isOverdue: isOverdue && tasksOnDate.length > 0,
        count: tasksOnDate.length
      }
    } catch {
      return { hasTask: false, isOverdue: false, count: 0 }
    }
  }

  if (!isExpanded) {
    return null
  }

  return (
    <div
      className="bg-white rounded-2xl border border-gray-100/80 shadow-sm p-4 overflow-hidden transition-all duration-300 ease-in-out"
      style={{
        maxHeight: isExpanded ? '500px' : '0',
        opacity: isExpanded ? 1 : 0,
      }}
    >
      {/* 星期标题行 */}
      <div className="grid grid-cols-7 gap-2 mb-3">
        {['一', '二', '三', '四', '五', '六', '日'].map((day) => (
          <div key={day} className="text-center text-xs font-bold text-gray-500">
            {day}
          </div>
        ))}
      </div>

      {/* 日历网格 */}
      <div className="grid grid-cols-7 gap-2">
        {calendarDays.map((day, idx) => {
          if (!day.isCurrentMonth) {
            return <div key={idx} className="aspect-square" />
          }

          const taskStatus = getTaskStatus(day.date)

          return (
            <button
              key={idx}
              type="button"
              onClick={() => day.date && onDateSelect(day.date)}
              className={`aspect-square rounded-xl flex flex-col items-center justify-center text-sm font-medium transition-all relative ${
                day.isSelected
                  ? 'bg-blue-600 text-white font-bold shadow-md scale-105'
                  : day.isToday
                  ? 'bg-blue-50 text-blue-600 font-semibold border-2 border-blue-300'
                  : 'hover:bg-gray-50 text-gray-700'
              }`}
              title={taskStatus.hasTask ? `${taskStatus.count} 个任务` : undefined}
            >
              <span className="text-base">{day.dayNum}</span>
              
              {/* 小点标记：蓝点（今天及以后）或红点（过期） */}
              {taskStatus.hasTask && (
                <span 
                  className={`absolute bottom-1 w-1.5 h-1.5 rounded-full ${
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
    </div>
  )
})

CalendarView.displayName = 'CalendarView'
