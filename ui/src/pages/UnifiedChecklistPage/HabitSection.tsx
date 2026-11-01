// ui/src/pages/UnifiedChecklistPage/HabitSection.tsx
// 习惯分组组件
import { memo, useMemo, useEffect, useState } from 'react'
import { statusControlClass } from '@core/StatusControl'
import { SourceRewardSummary } from '../../components/Rewards/SourceRewardSummary'
import { SourceRewardEditor } from '../../components/Rewards/SourceRewardEditor'
import { getDatabase, syncNow } from '../../db'
import { HabitActions } from './HabitActions'
import { useLocalHabitMutation } from '../../hooks/useLocalHabitMutation'
import { requireActiveHabitRewardSource } from '../../hooks/sourceRewardApi'
import { dateToShanghaiDateString } from '../../utils/shanghaiDate'
import { timedHabitBlock } from '../../hooks/useHabits'

interface HabitSectionProps {
  habits: any[]
  ignoredHabits: any[]
  onSetIgnored: (habitId: string | number, ignore: boolean) => Promise<boolean>
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
  ignoredHabits,
  onSetIgnored,
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
  const [managedHabit, setManagedHabit] = useState<any>(null)
  const [rewardError, setRewardError] = useState('')
  const [clockNow, setClockNow] = useState(() => new Date())
  const dietPoints: Record<string, number> = { no_sugary_drinks: 6, no_refined_staples: 6, no_snacks: 5, breakfast_on_time: 11, lunch_on_time: 11, dinner_on_time: 11 }
  const dietHabits = habits.filter(habit => habit.source === 'system' && String(habit.id).startsWith('diet-v5:'))
  const dietMaximum = dietHabits.reduce((sum, habit) => sum + (dietPoints[String(habit.id).split(':')[1]] || 0), 0)
  const dietEarned = dietHabits.reduce((sum, habit) => sum + (Number(todayCheckins.find(row => String(row.habit_id) === String(habit.id))?.status) === 2 ? dietPoints[String(habit.id).split(':')[1]] || 0 : 0), 0)
  useEffect(() => {
    const timer = window.setInterval(() => setClockNow(new Date()), 30_000)
    return () => window.clearInterval(timer)
  }, [])
  const changeIgnore = async (habitId: string | number, ignore: boolean) => {
    try {
      if (!await onSetIgnored(habitId, ignore)) setRewardError('忽略状态未保存，请检查网络后重试')
      else setRewardError('')
    } catch { setRewardError('忽略状态未保存，请检查网络后重试') }
  }
  useEffect(() => {
    const listener = (event: Event) => setRewardError((event as CustomEvent<string>).detail || '习惯状态已变化，请同步清单')
    window.addEventListener('habit-lifecycle-error', listener)
    return () => window.removeEventListener('habit-lifecycle-error', listener)
  }, [])
  const openReward = async (habit: any) => {
    setRewardError('')
    try {
      await requireActiveHabitRewardSource(String(habit.id))
      setRewardHabit({ id: String(habit.id), title: habit.name })
    } catch (error) { setRewardError(error instanceof Error ? error.message : '请联网同步习惯后再配置奖励') }
  }
  const localMutation = useLocalHabitMutation()
  const habitCreator = mode !== 'completed' && (
    <form className="mb-2 flex gap-2 px-1" onSubmit={async event => {
      event.preventDefault()
      const name = draftHabit.trim()
      if (!name) return
      if (await localMutation.run(db => db.addHabit(name, '✅'), 'create')) setDraftHabit('')
    }}>
      <input value={draftHabit} disabled={localMutation.busy} onChange={event => setDraftHabit(event.target.value)} className="min-w-0 flex-1 rounded border px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800" placeholder="新建原生习惯" aria-label="习惯名称" />
      <button type="submit" disabled={localMutation.busy} className="theme-accent-button rounded px-3 text-sm disabled:opacity-50">＋习惯</button>
      {localMutation.message && <span role="status" className="text-xs">{localMutation.message}</span>}
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
      if (Number(habit.is_active || 0) !== 0) return false
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

  const ignoredControls = mode === 'incomplete' && ignoredHabits.length > 0 && (
    <div className="text-xs text-gray-500">今日已忽略：{ignoredHabits.map(habit => (
      <button key={habit.id} type="button" className="mx-1 underline" onClick={() => void changeIgnore(habit.id, false)}>
        {habit.name} · 撤销
      </button>
    ))}</div>
  )

  if (sortedHabits.length === 0) {
    if (mode === 'completed') return null
    return (
      <div className="theme-surface rounded-xl border p-3 shadow-sm">
        <h3 className="mb-2 px-1 text-sm font-bold text-gray-700">{getDateLabel()}</h3>
        {rewardError && <p role="alert" className="text-xs text-red-600">{rewardError}</p>}
        {habitCreator}
        {ignoredControls}
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
      {rewardError && <p role="alert" className="text-sm text-red-600">{rewardError}</p>}
      {mode !== 'completed' && <><h3 className="text-sm font-bold text-gray-700 px-1">{getDateLabel()}</h3>{habitCreator}</>}
      {mode !== 'completed' && dietMaximum > 0 && <p className="px-1 text-xs text-amber-700">饮食约束 {dietEarned}/{dietMaximum} 分 · 六项各结算一次</p>}
      {ignoredControls}
      {sortedHabits.map((habit) => {
        // 查询选中日期的打卡记录（不再只看今天）
        const checkin = todayCheckins.find(c => c.habit_id === habit.id)
        const todayStatus = checkin ? checkin.status : 0
        const timed = habit.window_start_minute != null && habit.window_end_minute != null
        const blocked = timedHabitBlock(habit, selectedDateStr, Number(todayStatus), clockNow)
        const clockLabel = (minute: number) => minute === 1440 ? '24:00' : `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`
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
              <button type="button" onClick={() => { if (habit.source !== 'system') setManagedHabit(habit) }} className="block max-w-full truncate text-left text-sm font-semibold leading-5 text-gray-900 dark:text-gray-100" aria-label={`查看习惯「${habit.name}」月打卡记录`}>{habit.name}</button>
              <span className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-400">
                <span>连续 {streak} 天</span>
                <span>{habit.source === 'system' ? '运动饮食规则' : habit.source === 'local' || String(habit.id).startsWith('local_') ? 'MyTimeLogger' : '滴答镜像'}</span>
                {timed && <span className="text-amber-700">{clockLabel(habit.window_start_minute)}–{clockLabel(habit.window_end_minute)} · {blocked || '时间内可打卡，结果不可更改'}</span>}
                {habit.source !== 'system' && <SourceRewardSummary
                  sourceType="habit"
                  sourceId={String(habit.id)}
                  compact
                  onEdit={() => { void openReward(habit) }}
                />}
              </span>

              {/* 打卡历史标记（已由卡片状态颜色及右侧按钮状态呈现，为保持高度一致移除了纯文本标签） */}
            </span>

            {/* 操作按钮：习惯仅支持打卡，不在清单页启动专注。 */}
            <span className="flex gap-1.5">
              {habit.source !== 'system' && <button type="button" title="习惯详情与管理" aria-label={`管理习惯「${habit.name}」`} onClick={() => setManagedHabit(habit)} className="px-2 text-gray-500">⋯</button>}
              {mode !== 'completed' && !timed && selectedDateStr === dateToShanghaiDateString(new Date()) && <button type="button" title="忽略今天" aria-label={`忽略今天的习惯「${habit.name}」`}
                onClick={() => void changeIgnore(habit.id, true)} className="rounded px-2 text-xs text-gray-500 hover:bg-gray-100">忽略今天</button>}
              <button
                type="button"
                disabled={Boolean(blocked)}
                onClick={(e) => {
                  e.stopPropagation()
                  if (todayStatus === 2 && checkin?.note && !window.confirm('撤销打卡会删除这一天的日志，确定继续吗？')) return
                  onToggleCheckin(habit.id, selectedDateStr, 2)
                }}
                className={`${statusControlClass(todayStatus === 2 ? 'success' : 'idle')} hover:bg-green-50 hover:text-green-500 hover:border-green-300`}
                title={blocked || (todayStatus === 2 ? '取消成功，恢复未完成' : '标记成功')}
                aria-label={todayStatus === 2 ? `取消习惯「${habit.name}」的成功状态` : `标记习惯「${habit.name}」为成功`}
                aria-pressed={todayStatus === 2}
              >
                ✓
              </button>
              {habit.source !== 'system' && <button
                type="button"
                disabled={Boolean(blocked)}
                onClick={(e) => {
                  e.stopPropagation()
                  if (todayStatus === 2 && checkin?.note && !window.confirm('改为失败会清除成功打卡日志，确定继续吗？')) return
                  onToggleCheckin(habit.id, selectedDateStr, 1)
                }}
                className={`${statusControlClass(todayStatus === 1 ? 'failure' : 'idle')} hover:bg-red-50 hover:text-red-500 hover:border-red-300`}
                title={blocked || (todayStatus === 1 ? '取消失败，恢复未完成' : '标记失败')}
                aria-label={todayStatus === 1 ? `取消习惯「${habit.name}」的失败状态` : `标记习惯「${habit.name}」为失败`}
                aria-pressed={todayStatus === 1}
              >
                ✕
              </button>}
            </span>
          </div>
        )
      })}
    </div>
    {managedHabit && (
      <HabitActions
        key={String(managedHabit.id)}
        habit={managedHabit}
        categories={categories}
        onClose={() => setManagedHabit(null)}
        onEditReward={habit => { setManagedHabit(null); void openReward(habit) }}
      />
    )}
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
