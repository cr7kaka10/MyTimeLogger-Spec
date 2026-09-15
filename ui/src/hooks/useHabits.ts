// ui/src/hooks/useHabits.ts
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Habit, HabitCheckin } from '../types'
import { getCurrentTimerClient, getDatabase, syncNow } from '../db'
import { useSyncRefresh } from './useEventRefresh'

export interface UseHabitsReturn {
  habits: Habit[]
  todayCheckins: HabitCheckin[]
  selectedDate: string
  setSelectedDate: (date: string) => void
  streakMap: Record<number | string, number>
  weeklyMap: Record<number | string, number[]>
  toggleCheckin: (habitId: number | string, date?: string, forceStatus?: number) => Promise<void>
  habitCommandStatus: Record<string, 'syncing' | 'retryable_failed'>
  retryHabitCheckin: (habitId: number | string) => Promise<void>
  addHabit: (name: string, icon: string, difficulty: string) => void
  deleteHabit: (id: number | string) => void
}

export function isHabitScheduledForDate(repeatRule: string | undefined | null, dateStr: string): boolean {
  if (!repeatRule) return true // 默认每天出现

  try {
    const parts = dateStr.split('-')
    const year = parseInt(parts[0], 10)
    const month = parseInt(parts[1], 10) - 1
    const day = parseInt(parts[2], 10)
    const date = new Date(year, month, day)
    const dayOfWeek = date.getDay() // 0 (周日) 到 6 (周六)

    const weekdayMap = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]
    const targetDay = weekdayMap[dayOfWeek]

    const rrule = repeatRule.toUpperCase()
    if (rrule.includes("FREQ=DAILY")) {
      return true
    }

    if (rrule.includes("FREQ=WEEKLY")) {
      const bydayMatch = rrule.match(/BYDAY=([^;]+)/)
      if (bydayMatch) {
        const activeDays = bydayMatch[1].split(",")
        return activeDays.includes(targetDay)
      }
    }
  } catch (e) {
    console.error("Failed to parse repeat rule:", repeatRule, e)
  }
  return true
}

export const useHabits = (): UseHabitsReturn => {
  const [habits, setHabits] = useState<Habit[]>([])
  const [todayCheckins, setTodayCheckins] = useState<HabitCheckin[]>([])
  const [streakMap, setStreakMap] = useState<Record<number | string, number>>({})
  const [weeklyMap, setWeeklyMap] = useState<Record<number | string, number[]>>({})
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [habitCommandStatus, setHabitCommandStatus] = useState<Record<string, 'syncing' | 'retryable_failed'>>({})
  const commandKeys = useRef<Record<string, string>>({})
  const syncRefresh = useSyncRefresh()

  const getLocalYYYYMMDD = (d: Date = new Date()) => {
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  const [selectedDate, setSelectedDate] = useState<string>(() => getLocalYYYYMMDD())

  useEffect(() => {
    getDatabase().then(db => {
      // 获取所有习惯（不按日期过滤，习惯每天都显示）
      const all = db.getHabits() as any[]
      
      // 获取选中日期的打卡记录
      const checkinsForSelectedDate = db.getTodayCheckins(selectedDate) as any[]

      // 过滤习惯：只显示今天有排期的，或者今天已经有打卡记录的（兜底展示）
      const filteredHabits = all.filter(h => {
        const rrule = h.repeat_rule || h.repeatRule
        const isScheduled = isHabitScheduledForDate(rrule, selectedDate)
        const hasCheckin = checkinsForSelectedDate.some(c => c.habit_id === h.id || c.habitId === h.id)
        return isScheduled || hasCheckin
      })

      console.log('=== useHabits 数据加载 ===')
      console.log('所有习惯:', all)
      console.log('过滤后习惯:', filteredHabits)
      console.log('选中日期:', selectedDate)
      console.log('打卡记录:', checkinsForSelectedDate)

      setHabits(filteredHabits)
      setTodayCheckins(checkinsForSelectedDate)

      // 真实连续天数
      const sMap: Record<number, number> = {}
      for (const h of all) sMap[h.id] = db.getRealStreak(h.id)
      setStreakMap(sMap)

      // 本周打卡状态 (本周一到周日仍然锁定在当前时间的本周，以便批量补卡)
      const nowToday = new Date()
      const ws = new Date(nowToday)
      ws.setDate(ws.getDate() - ws.getDay() + (ws.getDay() === 0 ? -6 : 1))
      const wsStr = getLocalYYYYMMDD(ws)
      const wMap: Record<number, number[]> = {}
      for (const h of all) wMap[h.id] = db.getWeeklyCheckins(h.id, wsStr)
      setWeeklyMap(wMap)
    })
  }, [refreshTrigger, syncRefresh, selectedDate])


  const submitHabitCommand = useCallback(async (habitId: number | string, date: string, desiredStatus: number, idempotencyKey: string, retry = false) => {
    const habitKey = String(habitId)
    const api = getCurrentTimerClient()
    if (!api) {
      setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'retryable_failed' }))
      return
    }
    commandKeys.current[habitKey] = idempotencyKey
    setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'syncing' }))
    const response = retry
      ? await api.retryHabitCheckin(idempotencyKey)
      : await api.commandHabitCheckin({ habit_id: habitKey, date, desired_status: desiredStatus, idempotency_key: idempotencyKey })
    if (!response.ok || response.data?.status !== 'confirmed') {
      setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'retryable_failed' }))
      return
    }
    const result = await syncNow({ reason: 'habit-checkin-command' })
    if (!result.ok) {
      setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'retryable_failed' }))
      return
    }
    setHabitCommandStatus(previous => {
      const next = { ...previous }
      delete next[habitKey]
      return next
    })
    setRefreshTrigger(previous => previous + 1)
    window.dispatchEvent(new CustomEvent('local-shortcut-trigger', { detail: 'balance-updated' }))
  }, [])

  const toggleCheckin = useCallback(async (habitId: number | string, date?: string, forceStatus?: number) => {
    navigator.vibrate?.(10)
    const targetDate = date || getLocalYYYYMMDD()
    const existing = todayCheckins.find(item => String(item.habit_id) === String(habitId))
    let desiredStatus = forceStatus ?? (existing?.status === 2 ? 0 : 2)
    if (forceStatus !== undefined && existing?.status === forceStatus) desiredStatus = 0
    const cryptoApi = globalThis.crypto
    const idempotencyKey = cryptoApi?.randomUUID?.() || `habit-${Date.now()}-${Math.random().toString(16).slice(2)}`
    await submitHabitCommand(habitId, targetDate, desiredStatus, idempotencyKey)
  }, [submitHabitCommand, todayCheckins])

  const retryHabitCheckin = useCallback(async (habitId: number | string) => {
    const habitKey = String(habitId)
    const idempotencyKey = commandKeys.current[habitKey]
    if (!idempotencyKey) return
    await submitHabitCommand(habitId, selectedDate, 0, idempotencyKey, true)
  }, [selectedDate, submitHabitCommand])

  const addHabit = useCallback((name: string, icon: string, difficulty: string) => {
    getDatabase().then(db => {
      db.addHabit(name, icon, difficulty)
      setRefreshTrigger(prev => prev + 1)
    })
  }, [])

  const deleteHabit = useCallback((id: number | string) => {
    getDatabase().then(db => {
      db.deleteHabit(id as any)
      setRefreshTrigger(prev => prev + 1)
    })
  }, [])

  return useMemo(
    () => ({
      habits, todayCheckins, selectedDate, setSelectedDate, streakMap, weeklyMap,
      toggleCheckin, habitCommandStatus, retryHabitCheckin, addHabit, deleteHabit,
    }),
    [habits, todayCheckins, selectedDate, setSelectedDate, streakMap, weeklyMap, toggleCheckin, habitCommandStatus, retryHabitCheckin, addHabit, deleteHabit],
  )
}
