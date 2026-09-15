// ui/src/pages/UnifiedChecklistPage/index.tsx
// 统一清单页面主容器 - 整合任务和习惯
import { memo, useState, useCallback, useRef, useEffect } from 'react'
import { WeekCalendar } from './WeekCalendar'
import { CalendarView } from './CalendarView'
import { TaskSection } from './TaskSection'
import { HabitSection } from './HabitSection'
import { useChecklist } from '../../hooks/useChecklist'
import type { UseHabitsReturn } from '../../hooks/useHabits'
import type { UseTimeBookReturn } from '../../hooks/useTimeBook'
import { dateToShanghaiDateString } from '../../utils/shanghaiDate'
import { syncAfterDateSwitch } from '../../db'

interface UnifiedChecklistPageProps {
  habits: UseHabitsReturn
  timeBook: UseTimeBookReturn
  timer: any
  onNavigate: (tab: any) => void
}

export const UnifiedChecklistPage = memo(({
  habits,
  timeBook,
  timer,
  onNavigate,
}: UnifiedChecklistPageProps) => {
  // 状态管理：月历展开状态（false=周历，true=月历）
  const [isCalendarExpanded, setIsCalendarExpanded] = useState(false)
  // 使用北京时间初始化 selectedDate
  const [selectedDate, setSelectedDate] = useState(() => {
    const now = new Date()
    const beijingTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (8 * 3600000))
    console.log('=== 初始化 selectedDate (北京时间) ===')
    console.log('系统时间:', now)
    console.log('北京时间:', beijingTime)
    return beijingTime
  })
  
  // 使用 useChecklist hook（返回所有任务）
  const checklist = useChecklist()
  const monthName = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'][selectedDate.getMonth()]
  const selectDateWithSync = useCallback((nextDate: Date) => {
    const dateStr = dateToShanghaiDateString(nextDate)
    setSelectedDate(nextDate)
    syncAfterDateSwitch('checklist', dateStr)
      .catch(error => console.warn('[UnifiedChecklistPage] date switch sync failed:', error))
  }, [])
  const returnToToday = useCallback(() => {
    const [year, month, day] = dateToShanghaiDateString(new Date()).split('-').map(Number)
    selectDateWithSync(new Date(year, month - 1, day))
    setIsCalendarExpanded(false)
  }, [selectDateWithSync])
  const syncTone = checklist.syncStatus?.includes('失败')
    ? 'border-red-100 bg-red-50 text-red-600'
    : checklist.syncStatus?.includes('同步中')
    ? 'border-blue-100 bg-blue-50 text-blue-600'
    : 'border-gray-100 bg-white text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'
  
  const containerRef = useRef<HTMLDivElement>(null)
  const startY = useRef(0)
  const isDragging = useRef(false)

  // 页面加载时自动同步滴答清单
  useEffect(() => {
    console.log('=== UnifiedChecklistPage 初始化 ===')
    console.log('selectedDate:', selectedDate)
    console.log('selectedDateStr:', selectedDate.toISOString().split('T')[0])
    console.log('tasks 数据:', checklist.tasks)
    console.log('habits 数据:', habits.habits)
    console.log('todayCheckins 数据:', habits.todayCheckins)
    
    if (typeof checklist.refreshFromTickTick === 'function') {
      console.log('触发 TickTick 自动同步...')
      checklist.refreshFromTickTick(true)
    } else {
      console.warn('⚠️ refreshFromTickTick 方法不存在')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 同步选中日期到 habits hook（使用北京时间格式化）
  useEffect(() => {
    console.log('=== selectedDate 变化 ===')
    console.log('新选中日期:', selectedDate)
    
    // 使用北京时间格式化日期字符串
    const year = selectedDate.getFullYear()
    const month = String(selectedDate.getMonth() + 1).padStart(2, '0')
    const day = String(selectedDate.getDate()).padStart(2, '0')
    const dateStr = `${year}-${month}-${day}`
    
    console.log('新选中日期字符串 (北京时间):', dateStr)
    habits.setSelectedDate(dateStr)
    console.log('已同步 selectedDate 到 habits hook:', dateStr)
  }, [selectedDate, habits])

  // 手势识别：下滑展开，上滑收起
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    startY.current = e.touches[0].clientY
    isDragging.current = true
  }, [])

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isDragging.current) return

    const currentY = e.touches[0].clientY
    const deltaY = currentY - startY.current

    // 下滑超过 80px 展开周历→月历
    if (deltaY > 80 && !isCalendarExpanded && containerRef.current?.scrollTop === 0) {
      setIsCalendarExpanded(true)
      isDragging.current = false
    }

    // 上滑收起月历→周历
    if (deltaY < -40 && isCalendarExpanded) {
      setIsCalendarExpanded(false)
      isDragging.current = false
    }
  }, [isCalendarExpanded])

  const handleTouchEnd = useCallback(() => {
    isDragging.current = false
  }, [])

  return (
    <div
      ref={containerRef}
      className="theme-page min-h-full space-y-3 overflow-y-auto px-6 py-4"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* 顶部工具栏 */}
      <header className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={returnToToday}
          className="shrink-0 rounded-lg px-1 py-1 text-2xl font-bold tracking-tight text-gray-900 transition-opacity hover:opacity-75 dark:text-gray-100"
          title="返回今天"
          aria-label={`${monthName}，点击返回今天`}
        >
          {monthName}
        </button>
        <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5">
          <div
            className={`flex h-9 min-w-0 flex-1 items-center truncate rounded-lg border px-2 text-[11px] font-semibold ${syncTone}`}
            title={checklist.syncStatus}
          >
            {checklist.syncStatus} · {checklist.tasks.length}任务
          </div>
          {checklist.unknownTaskRequestId && (
            <button
              type="button"
              onClick={checklist.reconcileUnknownTask}
              className="theme-surface h-9 shrink-0 rounded-lg border px-2 text-xs font-semibold text-amber-700 dark:text-amber-300"
              title="核对滴答清单中的未知创建结果"
            >
              核对
            </button>
          )}
          {/* Push 按钮已隐藏 - 统一通过同步按钮触发 */}
          <button
            type="button"
            onClick={() => checklist.refreshFromTickTick(true)}
            className="theme-surface flex h-9 w-10 shrink-0 items-center justify-center rounded-lg border text-xs font-semibold text-blue-600 transition-all hover:bg-blue-50/50 active:bg-blue-50 dark:text-blue-400 dark:hover:bg-gray-700 dark:active:bg-gray-700"
            title="同步待办与习惯"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={
                checklist.syncStatus?.includes('同步中') ||
                checklist.syncStatus?.includes('正在')
                  ? 'animate-spin'
                  : ''
              }
            >
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M16 3h5v5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M8 21H3v-5" />
            </svg>
          </button>
        </div>
      </header>

      {/* 周历（默认）或月历（展开） */}
      {!isCalendarExpanded ? (
        <WeekCalendar
          selectedDate={selectedDate}
          onDateSelect={selectDateWithSync}
          tasks={checklist.tasks}
        />
      ) : (
        <div role="region" aria-label="月历视图">
          <CalendarView
            isExpanded={isCalendarExpanded}
            selectedDate={selectedDate}
            onDateSelect={selectDateWithSync}
            tasks={checklist.tasks}
            habits={habits.habits}
            todayCheckins={habits.todayCheckins}
          />
        </div>
      )}

      {/* 今日任务分组（未完成） */}
      <TaskSection
        tasks={checklist.tasks}
        selectedDate={selectedDate}
        categories={timeBook.categories}
        timer={timer}
        onNavigate={onNavigate}
        onComplete={checklist.completeTask}
        onAdd={checklist.addTask}
        onDelete={checklist.deleteTask}
        onUpdateTask={checklist.updateTask}
        onUpdatePriority={checklist.updateTaskPriority}
        mode="incomplete"
      />

      {/* 习惯分组（未完成） */}
      <HabitSection
        habits={habits.habits}
        todayCheckins={habits.todayCheckins}
        selectedDate={selectedDate}
        streakMap={habits.streakMap}
        categories={timeBook.categories}
        timer={timer}
        onNavigate={onNavigate}
        onToggleCheckin={habits.toggleCheckin}
        onDateChange={habits.setSelectedDate}
        mode="incomplete"
      />

      {/* 已完成区块 */}
      <div className="mt-3 border-t border-gray-100 pt-2 dark:border-gray-700">
        <h2 className="mb-2 px-1 text-xs font-bold text-gray-500">已完成</h2>
        <div className="space-y-2 opacity-75">
          {/* 选中日期任务分组（已完成） */}
          <TaskSection
            tasks={checklist.tasks}
            selectedDate={selectedDate}
            categories={timeBook.categories}
            timer={timer}
            onNavigate={onNavigate}
            onComplete={checklist.completeTask}
            onAdd={checklist.addTask}
            onDelete={checklist.deleteTask}
            onUpdateTask={checklist.updateTask}
            onUpdatePriority={checklist.updateTaskPriority}
            mode="completed"
          />

          {/* 习惯分组（已完成） */}
          <HabitSection
            habits={habits.habits}
            todayCheckins={habits.todayCheckins}
            selectedDate={selectedDate}
            streakMap={habits.streakMap}
            categories={timeBook.categories}
            timer={timer}
            onNavigate={onNavigate}
            onToggleCheckin={habits.toggleCheckin}
            onDateChange={habits.setSelectedDate}
            mode="completed"
          />
        </div>
      </div>

      {/* 状态栏保留数量概览，具体同步状态已放到顶部按钮旁。 */}
      <div className="text-center text-xs text-gray-400 mt-2 font-medium">
        {checklist.tasks.length} 条任务 · {habits.habits.length} 个习惯
      </div>
    </div>
  )
})

UnifiedChecklistPage.displayName = 'UnifiedChecklistPage'
