// ui/src/hooks/useHabits.ts
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Habit, HabitCheckin } from '../types'
import { getCurrentTimerClient, getDatabase, syncNow } from '../db'
import { useEventRefresh } from './useEventRefresh'
import { LOCAL_HABITS_UPDATED } from './useLocalHabitMutation'
import { isHabitScheduledForDate as scheduledForDate } from '@core/HabitSchedule'
import { dateToShanghaiDateString } from '../utils/shanghaiDate'

export interface UseHabitsReturn {
  habits: Habit[]
  todayCheckins: HabitCheckin[]
  ignoredHabits: Habit[]
  setHabitIgnored: (habitId: number | string, ignore: boolean) => Promise<boolean>
  selectedDate: string
  setSelectedDate: (date: string) => void
  streakMap: Record<number | string, number>
  weeklyMap: Record<number | string, number[]>
  toggleCheckin: (habitId: number | string, date?: string, forceStatus?: number) => Promise<{ confirmed: boolean; checkedIn: boolean; date: string }>
  habitCommandStatus: Record<string, 'syncing' | 'retryable_failed'>
  retryHabitCheckin: (habitId: number | string) => Promise<void>
  addHabit: (name: string, icon: string) => void
  deleteHabit: (id: number | string) => void
}

export function isHabitScheduledForDate(repeatRule: string | undefined | null, dateStr: string): boolean {
  return scheduledForDate(repeatRule, dateStr)
}

export function timedHabitBlock(habit: Habit, date: string, status: number, now = new Date()): string | null {
  if (habit.window_start_minute == null || habit.window_end_minute == null) return null
  if (status === 1 || status === 2) return '定时习惯结果已锁定，不能修改'
  if (date !== dateToShanghaiDateString(now)) return '定时习惯只能在当天时间段内打卡'
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(now)
  const minutes = Number(parts.find(part => part.type === 'hour')?.value) * 60 + Number(parts.find(part => part.type === 'minute')?.value)
  if (minutes < habit.window_start_minute) return '打卡时间未到'
  if (minutes >= habit.window_end_minute) return '打卡已超时，等待自动判定失败'
  return null
}

export const useHabits = (): UseHabitsReturn => {
  const [habits, setHabits] = useState<Habit[]>([])
  const [todayCheckins, setTodayCheckins] = useState<HabitCheckin[]>([])
  const [ignoredHabits, setIgnoredHabits] = useState<Habit[]>([])
  const [streakMap, setStreakMap] = useState<Record<number | string, number>>({})
  const [weeklyMap, setWeeklyMap] = useState<Record<number | string, number[]>>({})
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [habitCommandStatus, setHabitCommandStatus] = useState<Record<string, 'syncing' | 'retryable_failed'>>({})
  const commandKeys = useRef<Record<string, string>>({})
  const syncRefresh = useEventRefresh(['sync-pull-complete', LOCAL_HABITS_UPDATED])

  const getLocalYYYYMMDD = (d: Date = new Date()) => dateToShanghaiDateString(d)

  const [selectedDate, setSelectedDate] = useState<string>(() => getLocalYYYYMMDD())

  useEffect(() => {
    getDatabase().then(db => {
      // 获取所有习惯（不按日期过滤，习惯每天都显示）
      const all = db.getHabits() as any[]
      const windows = db.getHabitWindowsForDate(selectedDate)
      for (const habit of all) {
        const window = windows.get(String(habit.id))
        habit.window_start_minute = window?.start_minute ?? null
        habit.window_end_minute = window?.end_minute ?? null
      }
      
      // 获取选中日期的打卡记录
      const checkinsForSelectedDate = db.getTodayCheckins(selectedDate) as any[]
      const ignoredIds = db.getIgnoredHabitIds(selectedDate)
      setIgnoredHabits(all.filter(h => Number(h.is_active || 0) === 0 && ignoredIds.has(String(h.id))))

      // 过滤习惯：只显示今天有排期的，或者今天已经有打卡记录的（兜底展示）
      const filteredHabits = all.filter(h => {
        if (Number(h.is_active || 0) !== 0) return false
        if (h.source === 'system' && !windows.has(String(h.id))) return false
        if (ignoredIds.has(String(h.id))) return false
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

  const setHabitIgnored = useCallback(async (habitId: number | string, ignore: boolean) => {
    if (habits.concat(ignoredHabits).some(habit => String(habit.id) === String(habitId) && habit.window_start_minute != null)) return false
    const api = getCurrentTimerClient()
    if (!api) return false
    const response = await api.post('/api/habits/day-ignores', {
      habit_id: String(habitId), date: selectedDate, ignore,
      idempotency_key: globalThis.crypto?.randomUUID?.() || `ignore-${Date.now()}`,
    })
    if (!response.ok || response.data?.status !== 'confirmed') return false
    await syncNow({ reason: 'habit-day-ignore' })
    setRefreshTrigger(previous => previous + 1)
    return true
  }, [selectedDate, habits, ignoredHabits])


  const submitHabitCommand = useCallback(async (habitId: number | string, date: string, desiredStatus: number, idempotencyKey: string, retry = false) => {
    const habitKey = String(habitId)
    const api = getCurrentTimerClient()
    if (!api) {
      setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'retryable_failed' }))
      return false
    }
    commandKeys.current[habitKey] = idempotencyKey
    setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'syncing' }))
    let response
    try {
      response = retry
        ? await api.retryHabitCheckin(idempotencyKey)
        : await api.commandHabitCheckin({ habit_id: habitKey, date, desired_status: desiredStatus, idempotency_key: idempotencyKey })
    } catch {
      setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'retryable_failed' }))
      return false
    }
    if (response.data?.status === 'failed') {
      delete commandKeys.current[habitKey]
      setHabitCommandStatus(previous => { const next = { ...previous }; delete next[habitKey]; return next })
      await syncNow({ reason: 'habit-lifecycle-rejected' })
      setRefreshTrigger(previous => previous + 1)
      window.dispatchEvent(new CustomEvent('habit-lifecycle-error', { detail: response.data.error_code || 'habit_unavailable' }))
      return false
    }
    if (!response.ok || response.data?.status !== 'confirmed') {
      setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'retryable_failed' }))
      return false
    }
    const result = await syncNow({ reason: 'habit-checkin-command' }).catch(() => ({ ok: false }))
    if (!result.ok) {
      setHabitCommandStatus(previous => ({ ...previous, [habitKey]: 'retryable_failed' }))
      return true
    }
    setHabitCommandStatus(previous => {
      const next = { ...previous }
      delete next[habitKey]
      return next
    })
    setRefreshTrigger(previous => previous + 1)
    window.dispatchEvent(new CustomEvent('balance-updated'))
    return true
  }, [])

  const toggleCheckin = useCallback(async (habitId: number | string, date?: string, forceStatus?: number) => {
    navigator.vibrate?.(10)
    const targetDate = date || getLocalYYYYMMDD()
    const existing = todayCheckins.find(item => String(item.habit_id) === String(habitId))
    const habit = habits.find(item => String(item.id) === String(habitId))
    const blocked = habit && timedHabitBlock(habit, targetDate, Number(existing?.status || 0))
    if (blocked) {
      window.dispatchEvent(new CustomEvent('habit-lifecycle-error', { detail: blocked }))
      return { confirmed: false, checkedIn: false, date: targetDate }
    }
    let desiredStatus = forceStatus ?? (existing?.status === 2 ? 0 : 2)
    if (forceStatus !== undefined && existing?.status === forceStatus) desiredStatus = 0
    const cryptoApi = globalThis.crypto
    const idempotencyKey = cryptoApi?.randomUUID?.() || `habit-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const confirmed = await submitHabitCommand(habitId, targetDate, desiredStatus, idempotencyKey)
    return { confirmed: Boolean(confirmed), checkedIn: desiredStatus === 2, date: targetDate }
  }, [submitHabitCommand, todayCheckins, habits])

  const retryHabitCheckin = useCallback(async (habitId: number | string) => {
    const habitKey = String(habitId)
    const idempotencyKey = commandKeys.current[habitKey]
    if (!idempotencyKey) return
    await submitHabitCommand(habitId, selectedDate, 0, idempotencyKey, true)
  }, [selectedDate, submitHabitCommand])

  const addHabit = useCallback((name: string, icon: string) => {
    getDatabase().then(db => {
      db.addHabit(name, icon)
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
      habits, todayCheckins, ignoredHabits, setHabitIgnored, selectedDate, setSelectedDate, streakMap, weeklyMap,
      toggleCheckin, habitCommandStatus, retryHabitCheckin, addHabit, deleteHabit,
    }),
    [habits, todayCheckins, ignoredHabits, setHabitIgnored, selectedDate, setSelectedDate, streakMap, weeklyMap, toggleCheckin, habitCommandStatus, retryHabitCheckin, addHabit, deleteHabit],
  )
}
