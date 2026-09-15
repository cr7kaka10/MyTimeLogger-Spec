// ui/src/pages/UnifiedChecklistPage/HabitSection.tsx
// 习惯分组组件
import { memo, useMemo, useEffect, useState } from 'react'
import { statusControlClass } from '@core/StatusControl'
import { SourceRewardSummary } from '../../components/Rewards/SourceRewardSummary'
import { SourceRewardEditor } from '../../components/Rewards/SourceRewardEditor'
import { getDatabase, syncNow } from '../../db'

interface HabitSectionProps {
  habits: any[]
  todayCheckins: any[]
  selectedDate: Date
  streakMap: Record<string, number>
  categories: any[]
  timer: any
  onNavigate: (tab: any) => void
  onToggleCheckin: (habitId: string | number, date?: string, forceStatus?: number) => void
  onDateChange?: (dateStr: string) => void
  mode?: 'all' | 'incomplete' | 'completed'
}

export const HabitSection = memo(({
  habits,
  todayCheckins,
  selectedDate,
  streakMap,
  categories,
  timer,
  onNavigate,
  onToggleCheckin,
  onDateChange,
  mode = 'all',
}: HabitSectionProps) => {
  const [rewardHabit, setRewardHabit] = useState<{ id: string; title: string } | null>(null)
  const [draftHabit, setDraftHabit] = useState('')
  const habitCreator = mode !== 'completed' && (
    <form className="mb-2 flex gap-2 px-1" onSubmit={async event => {
      event.preventDefault()
      const name = draftHabit.trim()
      if (!name) return
      const db = await getDatabase()
      db.addHabit(name, '✅', 'easy')
      setDraftHabit('')
      await syncNow({ reason: 'checklist-local-habit-create' })
    }}>
      <input value={draftHabit} onChange={event => setDraftHabit(event.target.value)} className="min-w-0 flex-1 rounded border px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800" placeholder="新建原生习惯" aria-label="习惯名称" />
      <button type="submit" className="theme-accent-button rounded px-3 text-sm">＋习惯</button>
    </form>
  )


  const getLocalYYYYMMDD = (d: Date = new Date()) => {
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  // 获取日期显示文本
  const getDateLabel = () => {
    try {
      if (!selectedDate || !(selectedDate instanceof Date) || isNaN(selectedDate.getTime())) {
        return '习惯'
      }

      const selectedDateStr = selectedDate.toISOString().split('T')[0]
      const today = new Date().toISOString().split('T')[0]

      if (selectedDateStr === today) {
        return '习惯'
      }

      const month = selectedDate.getMonth() + 1
      const day = selectedDate.getDate()
      return `${month}月${day}日 习惯`
    } catch (error) {
      console.error('getDateLabel error:', error)
      return '习惯'
    }
  }

  // 当前选中日期的字符串格式（用于查询打卡记录）
  const selectedDateStr = useMemo(() => {
    try {
      return selectedDate instanceof Date ? getLocalYYYYMMDD(selectedDate) : getLocalYYYYMMDD()
    } catch {
      return getLocalYYYYMMDD()
    }
  }, [selectedDate])

  useEffect(() => {
    console.log('=== HabitSection 数据更新 ===')
    console.log('habits:', habits)
    console.log('selectedDate:', selectedDate)
    console.log('todayCheckins:', todayCheckins)
  }, [habits, selectedDate, todayCheckins])

  // 习惯排序：状态权重（未打卡 0 在上，已处理的在下），同权重按字母顺序
  const sortedHabits = useMemo(() => {
    console.log('=== HabitSection 排序习惯 ===')
    console.log('输入 habits:', habits)
    
    if (!Array.isArray(habits)) {
      console.warn('⚠️ habits 不是数组')
      return []
    }
    
    const filtered = habits.filter(habit => {
      const checkin = todayCheckins.find(c => c.habit_id === habit.id)
      const status = checkin ? checkin.status : 0
      if (mode === 'incomplete') return status === 0
      if (mode === 'completed') return status === 1 || status === 2
      return true
    })

    const sorted = [...filtered].sort((a, b) => {
      const checkinA = todayCheckins.find(c => c.habit_id === a.id)
      const checkinB = todayCheckins.find(c => c.habit_id === b.id)
      const statusA = checkinA ? checkinA.status : 0
      const statusB = checkinB ? checkinB.status : 0
      
      const weightA = statusA === 0 ? 0 : 1
      const weightB = statusB === 0 ? 0 : 1
      
      if (weightA !== weightB) {
        return weightA - weightB
      }
      return a.name.localeCompare(b.name, 'zh-CN')
    })
    console.log(`模式 [${mode}] 排序后习惯:`, sorted)
    return sorted
  }, [habits, todayCheckins, mode])

  if (sortedHabits.length === 0) {
    if (mode === 'completed') return null
    return (
      <div className="theme-surface rounded-xl border p-3 shadow-sm">
        <h3 className="mb-2 px-1 text-sm font-bold text-gray-700">{getDateLabel()}</h3>
        {habitCreator}
        <div className="flex items-center justify-center gap-2 py-2">
          <span className="text-xl text-gray-300">🌱</span>
          <p className="text-xs font-medium text-gray-400">暂无习惯</p>
        </div>
      </div>
    )
  }

  return (
    <>
    <div className="space-y-2" role="region" aria-label={mode === 'completed' ? '已完成习惯' : getDateLabel()}>
      {mode !== 'completed' && <><h3 className="text-sm font-bold text-gray-700 px-1">{getDateLabel()}</h3>{habitCreator}</>}
      {sortedHabits.map((habit) => {
        // 查询选中日期的打卡记录（不再只看今天）
        const checkin = todayCheckins.find(c => c.habit_id === habit.id)
        const todayStatus = checkin ? checkin.status : 0
        const streak = streakMap[habit.id] ?? 0

        console.log(`习惯 [${habit.name}]:`)
        console.log('  habit_id:', habit.id)
        console.log('  查找到的checkin:', checkin)
        console.log('  打卡状态:', checkin ? '已打卡 ✅' : '未打卡 ⭕')

        let borderClass = 'border-gray-100 hover:border-gray-200'
        if (todayStatus === 2) {
          borderClass = 'border-green-500 bg-green-50/10 shadow-sm shadow-green-50/20'
        } else if (todayStatus === 1) {
          borderClass = 'border-red-500 bg-red-50/10 shadow-sm shadow-red-50/20'
        }

        return (
          <div
            key={habit.id}
            className={`theme-surface grid min-h-14 w-full grid-cols-[28px_1fr_auto] items-center gap-2 rounded-xl border p-2.5 transition-all ${borderClass}`}
          >
            {/* 习惯图标 */}
            <span className="text-xl">
              {habit.icon?.length > 2 ? (
                (() => {
                  const iconMap: Record<string, string> = {
                    'habit_daily_check_in': '📅',
                    'habit_praise_others': '👍',
                    'habit_keep_diary': '📓',
                    'habit_self_reflection': '🤔',
                    'habit_push_ups': '💪',
                    'habit_exercising': '🏃',
                    'habit_yoga': '🧘',
                    'habit_housework': '🧹',
                    'habit_brush_teeth': '🪥',
                    'habit_skincare': '🧴'
                  }
                  return iconMap[habit.icon] || '🎯'
                })()
              ) : habit.icon}
            </span>

            {/* 习惯信息 */}
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold leading-5 text-gray-900">{habit.name}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-400">
                <span>连续 {streak} 天</span>
                <span>{habit.source === 'local' || String(habit.id).startsWith('local_') ? 'MyTimeLogger' : '滴答镜像'}</span>
                <SourceRewardSummary
                  sourceType="habit"
                  sourceId={String(habit.id)}
                  compact
                  onEdit={() => setRewardHabit({ id: String(habit.id), title: habit.name })}
                />
              </span>
              
              {/* 打卡历史标记（已由卡片状态颜色及右侧按钮状态呈现，为保持高度一致移除了纯文本标签） */}
            </span>

            {/* 操作按钮：习惯仅支持打卡，不在清单页启动专注。 */}
            <span className="flex gap-1.5">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onToggleCheckin(habit.id, selectedDateStr, 2)
                }}
                className={`${statusControlClass(todayStatus === 2 ? 'success' : 'idle')} hover:bg-green-50 hover:text-green-500 hover:border-green-300`}
                title="标记成功"
                aria-label={`标记习惯「${habit.name}」为成功`}
                aria-pressed={todayStatus === 2}
              >
                ✓
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onToggleCheckin(habit.id, selectedDateStr, 1)
                }}
                className={`${statusControlClass(todayStatus === 1 ? 'failure' : 'idle')} hover:bg-red-50 hover:text-red-500 hover:border-red-300`}
                title="标记失败"
                aria-label={`标记习惯「${habit.name}」为失败`}
                aria-pressed={todayStatus === 1}
              >
                ✕
              </button>
            </span>
          </div>
        )
      })}
    </div>
    {rewardHabit && (
      <SourceRewardEditor
        sourceType="habit"
        sourceId={rewardHabit.id}
        sourceTitle={rewardHabit.title}
        onClose={() => setRewardHabit(null)}
      />
    )}
    </>
  )
})

HabitSection.displayName = 'HabitSection'
