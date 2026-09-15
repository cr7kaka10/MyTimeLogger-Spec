// ui/src/components/Habits/HabitsPage.tsx
import { memo, useMemo, useState } from 'react'
import type { HabitSection } from '../../types'
import type { UseHabitsReturn } from '../../hooks/useHabits'
import { EmptyState } from '../common/EmptyState'
import { HabitMonthCalendarDialog } from './HabitMonthCalendarDialog'
import { SourceRewardSummary } from '../Rewards/SourceRewardSummary'

interface HabitsPageProps extends UseHabitsReturn {
  balance?: number
  activeSection: HabitSection
  onSectionChange: (section: HabitSection) => void
  onSync?: () => Promise<void>
  syncStatus?: string
  onOpenLedger?: () => void
  categories?: any[]
  timer?: any
  onNavigate?: (tab: any) => void
}

export const HabitsPage = memo(({
  habits, todayCheckins, selectedDate, setSelectedDate, streakMap, weeklyMap,
  toggleCheckin, habitCommandStatus, retryHabitCheckin, addHabit, deleteHabit, activeSection, onSectionChange, balance = 0, onSync, syncStatus, onOpenLedger, categories, timer, onNavigate
}: HabitsPageProps) => {
  const checkedCount = useMemo(() => todayCheckins.filter((item) => item.status === 2).length, [todayCheckins])
  const [selectedHabit, setSelectedHabit] = useState<any | null>(null)

  const getLocalYYYYMMDD = (d: Date = new Date()) => {
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  const weekDays = useMemo(() => {
    const nowToday = new Date()
    const currentDay = nowToday.getDay()
    const distanceToMonday = currentDay === 0 ? -6 : 1 - currentDay
    const monday = new Date(nowToday)
    monday.setDate(nowToday.getDate() + distanceToMonday)

    const days = []
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday)
      d.setDate(monday.getDate() + i)
      const year = d.getFullYear()
      const month = String(d.getMonth() + 1).padStart(2, '0')
      const day = String(d.getDate()).padStart(2, '0')
      const dateStr = `${year}-${month}-${day}`
      days.push({
        dateStr,
        dayNum: d.getDate(),
        label: ['日', '一', '二', '三', '四', '五', '六'][d.getDay()],
        isToday: dateStr === getLocalYYYYMMDD(),
      })
    }
    return days
  }, [])

  if (habits.length === 0) {
    return (
      <div className="flex min-h-full flex-col items-center justify-center bg-[#FAFAFA] p-6 w-full">
        <EmptyState icon="🎯" title="还没有习惯" description="同步滴答清单的习惯后即可开始打卡。" />
        {onSync && (
          <button
            type="button"
            onClick={onSync}
            className="mt-4 rounded-xl bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white shadow-md active:bg-blue-600 transition-all flex items-center gap-2"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={(syncStatus?.includes('同步中') || syncStatus?.includes('正在')) ? 'animate-spin' : ''}>
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M16 3h5v5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M8 21H3v-5" />
            </svg>
            拉取最新习惯
          </button>
        )}
      </div>
    )
  }

  // Group habits by category_id
  const groupedHabits = useMemo(() => {
    const groups: Record<string, typeof habits> = {}
    habits.forEach(h => {
      const catId = h.category_id !== null && h.category_id !== undefined ? String(h.category_id) : 'uncategorized'
      if (!groups[catId]) {
        groups[catId] = []
      }
      groups[catId].push(h)
    })
    return groups
  }, [habits])

  const categoryMap = useMemo(() => {
    const map: Record<string, any> = {}
    categories?.forEach(c => {
      map[String(c.id)] = c
    })
    return map
  }, [categories])

  const groupKeys = useMemo(() => {
    return Object.keys(groupedHabits).sort((a, b) => {
      if (a === 'uncategorized') return 1
      if (b === 'uncategorized') return -1
      const catA = categoryMap[a]
      const catB = categoryMap[b]
      return (catA?.sort_order ?? 0) - (catB?.sort_order ?? 0)
    })
  }, [groupedHabits, categoryMap])

  return (
    <div className="flex min-h-full flex-col gap-4 bg-[#FAFAFA] p-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">习惯</h1>
          <div className="mt-2 text-sm text-gray-400">
            {selectedDate === getLocalYYYYMMDD() ? '今天' : `${selectedDate.slice(5)}`}已完成 {checkedCount} / {habits.length}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onSync && (
            <button
              type="button"
              onClick={onSync}
              className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold text-blue-600 active:bg-blue-50 hover:bg-blue-50/50 transition-all"
              title="同步待办与习惯"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={(syncStatus?.includes('同步中') || syncStatus?.includes('正在')) ? 'animate-spin' : ''}>
                <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
                <path d="M16 3h5v5" />
                <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
                <path d="M8 21H3v-5" />
              </svg>
            </button>
          )}
          {onOpenLedger ? (
            <button
              type="button"
              onClick={onOpenLedger}
              className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold hover:bg-amber-50 active:bg-amber-100 transition-all"
              title="金币流水"
            >
              💰 {typeof balance === 'number' ? parseFloat(balance.toFixed(2)) : balance}
            </button>
          ) : (
            <div className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold">💰 {typeof balance === 'number' ? parseFloat(balance.toFixed(2)) : balance}</div>
          )}
        </div>
      </header>

      {/* 周日历 */}
      <div className="grid grid-cols-7 gap-2 bg-white border border-gray-100/80 p-2.5 rounded-2xl shadow-sm">
        {weekDays.map((day) => {
          const isSelected = day.dateStr === selectedDate
          const isToday = day.isToday

          return (
            <button
              key={day.dateStr}
              type="button"
              onClick={() => setSelectedDate(day.dateStr)}
              className={`flex flex-col items-center justify-center py-2 rounded-xl transition-all duration-200 active:scale-95 ${
                isSelected
                  ? 'bg-blue-600 text-white font-bold shadow-md shadow-blue-500/10'
                  : 'hover:bg-gray-50 text-gray-700'
              }`}
            >
              <span className={`text-[11px] font-medium leading-none ${isSelected ? 'text-blue-100' : 'text-gray-400'}`}>
                {day.label}
              </span>
              <span className={`mt-1.5 text-base font-bold leading-none ${isToday && !isSelected ? 'text-blue-600' : ''}`}>
                {day.dayNum}
              </span>
              {isToday && !isSelected && (
                <span className="mt-1 h-1 w-1 rounded-full bg-blue-600 animate-pulse" />
              )}
              {(!isToday || isSelected) && (
                <span className="mt-1 h-1 w-1" />
              )}
            </button>
          )
        })}
      </div>

      <div className="flex-1 space-y-6">
        {groupKeys.map(key => {
          const group = groupedHabits[key]
          const cat = categoryMap[key]
          const catName = key === 'uncategorized' ? '未分类' : (cat?.name || '未知分类')
          const catIcon = key === 'uncategorized' ? '🎯' : (cat?.icon || '📖')
          const catColor = key === 'uncategorized' ? '#9E9E9E' : (cat?.color || '#5E81AC')

          return (
            <div key={key} className="space-y-2.5">
              {/* 分组头部 */}
              <div className="flex items-center justify-between px-1">
                <div className="flex items-center gap-2">
                  <span
                    className="flex h-6 w-6 items-center justify-center rounded-lg text-sm"
                    style={{ backgroundColor: `${catColor}15`, color: catColor }}
                  >
                    {catIcon}
                  </span>
                  <span className="text-sm font-bold text-gray-700">{catName}</span>
                  <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-bold text-gray-400">
                    {group.length}
                  </span>
                </div>
              </div>

              {/* 习惯列表 */}
              <div className="space-y-3">
                {group.map((habit) => {
                  const todayCheckin = todayCheckins.find(c => c.habit_id === habit.id)
                  const todayStatus = todayCheckin ? todayCheckin.status : 0
                  const streak = (streakMap as any)[habit.id] ?? 0
                  const commandStatus = habitCommandStatus[String(habit.id)]

                  let borderClass = 'border-gray-100 hover:border-gray-200'
                  if (todayStatus === 2) {
                    borderClass = 'border-green-500 bg-green-50/10 shadow-sm shadow-green-50/20'
                  } else if (todayStatus === 1) {
                    borderClass = 'border-red-500 bg-red-50/10 shadow-sm shadow-red-50/20'
                  }

                  return (
                    <div
                      key={habit.id}
                      onClick={() => setSelectedHabit(habit)}
                      className={`grid min-h-20 w-full grid-cols-[36px_1fr_auto] items-center gap-3 rounded-2xl border bg-white p-4 text-left active:bg-gray-50/80 cursor-pointer transition-all ${borderClass}`}
                    >
                      <span className="text-2xl">{habit.icon?.length > 2 ? (
                        { 'habit_daily_check_in': '📅', 'habit_praise_others': '👍', 'habit_keep_diary': '📓', 'habit_self_reflection': '🤔', 'habit_push_ups': '💪', 'habit_exercising': '🏃', 'habit_yoga': '🧘', 'habit_housework': '🧹', 'habit_brush_teeth': '🪥', 'habit_skincare': '🧴' }[habit.icon] || '🎯'
                      ) : habit.icon}</span>
                      <div>
                        <span className="font-semibold text-gray-900">{habit.name}</span>
                        <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold text-gray-400">{habit.difficulty}</span>
                        <span className="block mt-1 text-sm text-gray-400">连续 {streak} 天</span>
                        <SourceRewardSummary sourceType="habit" sourceId={String(habit.id)} compact hideError />
                        {commandStatus === 'syncing' && <span className="mt-1 block text-xs font-medium text-blue-600">同步中</span>}
                        {commandStatus === 'retryable_failed' && (
                          <button type="button" onClick={(event) => { event.stopPropagation(); retryHabitCheckin(habit.id) }} className="mt-1 text-xs font-medium text-red-500 hover:text-red-700">
                            同步失败，重试
                          </button>
                        )}
                      </div>
                      <span className="flex gap-2">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleCheckin(habit.id, selectedDate, 2)
                          }}
                          disabled={commandStatus === 'syncing'}
                          className={`h-8 w-8 rounded-full text-xs flex items-center justify-center transition-all ${
                            todayStatus === 2
                              ? 'bg-green-500 border border-green-600 text-white font-bold'
                              : 'bg-gray-100 text-gray-400 hover:bg-green-50 hover:text-green-500 hover:border-green-300'
                          }`}
                          title="标记成功"
                        >
                          ✓
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleCheckin(habit.id, selectedDate, 1)
                          }}
                          disabled={commandStatus === 'syncing'}
                          className={`h-8 w-8 rounded-full text-xs flex items-center justify-center transition-all ${
                            todayStatus === 1
                              ? 'bg-red-500 border border-red-600 text-white font-bold'
                              : 'bg-gray-100 text-gray-400 hover:bg-red-50 hover:text-red-500 hover:border-red-300'
                          }`}
                          title="标记失败"
                        >
                          ✕
                        </button>
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {selectedHabit && (
        <HabitMonthCalendarDialog
          habit={selectedHabit}
          onClose={() => setSelectedHabit(null)}
          onToggleCheckin={toggleCheckin}
        />
      )}
    </div>
  )
})

HabitsPage.displayName = 'HabitsPage'
