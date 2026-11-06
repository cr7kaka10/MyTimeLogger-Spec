// ui/src/hooks/useGoals.ts
import { useCallback, useEffect, useMemo, useState } from 'react'
import { requireActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import type { Goal } from '../types'
import { getDatabase, pullSync } from '../db'
import { useEventRefresh } from './useEventRefresh'
import { formatPlatformNetworkError } from '../platform/fetch'
import { protectedPlatformFetch } from '../platform/protectedRequest'

export interface UseGoalsReturn {
  goals: Goal[]
  progressMap: Record<number | string, { current: number; target: number; percent: number; isRestDay?: boolean }>
  historyMap: Record<number | string, Record<string, number>>
  addGoal: (g: Omit<Goal, 'id'>) => Promise<void>
  updateGoal: (id: number | string, g: Omit<Goal, 'id'>) => Promise<void>
  deleteGoal: (id: number | string) => Promise<void>
}

export const useGoals = (): UseGoalsReturn => {
  const [goals, setGoals] = useState<Goal[]>([])
  const [progressMap, setProgressMap] = useState<Record<number | string, { current: number; target: number; percent: number; isRestDay?: boolean }>>({})
  const [historyMap, setHistoryMap] = useState<Record<number | string, Record<string, number>>>({})
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const eventRefresh = useEventRefresh(['balance-updated', 'sync-pull-complete'])

  useEffect(() => {
    getDatabase().then(db => {
      const allGoals = db.getGoals() as Goal[]
      setGoals(allGoals)

      const pMap: Record<number | string, { current: number; target: number; percent: number; isRestDay?: boolean }> = {}
      const hMap: Record<number | string, Record<string, number>> = {}

      allGoals.forEach(g => {
        pMap[g.id] = db.getGoalProgress(g)
        const categoryIds = g.category_ids?.length
          ? g.category_ids
          : (g.category_id == null ? [] : [g.category_id])
        if (categoryIds.length > 0 && typeof db.getCategoriesHistory === 'function') {
          hMap[g.id] = db.getCategoriesHistory(categoryIds, g.metric as any, 30)
        }
      })
      setProgressMap(pMap)
      setHistoryMap(hMap)
    })
  }, [refreshTrigger, eventRefresh])

  useEffect(() => {
    getDatabase().then(async db => {
      try {
        const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'goals.auto_settle')
        const response = await protectedPlatformFetch(runtime, '/api/goals/auto_settle', { method: 'POST' })
        if (response.ok) await pullSync()
      } catch {
        // Offline viewing continues to use the last synchronized cache.
      }
    })
  }, [])

  const command = useCallback(async (method: 'POST' | 'PUT' | 'DELETE', path: string, body?: Record<string, any>) => {
    const db = await getDatabase()
    const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), `goals.${method.toLowerCase()}`)
    let response
    try {
      response = await protectedPlatformFetch(runtime, path, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      })
    } catch (error) {
      throw new Error(formatPlatformNetworkError(error))
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(response.status === 401 ? '认证失败，请重新登录当前环境' : payload?.detail || `目标操作失败（HTTP ${response.status}）`)
    }
    await pullSync().catch(error => console.warn('[useGoals] 保存已成功，后续同步失败:', error))
    setRefreshTrigger(previous => previous + 1)
  }, [])

  const addGoal = useCallback((goal: Omit<Goal, 'id'>) => command('POST', '/api/goals', goal), [command])
  const updateGoal = useCallback((id: number | string, goal: Omit<Goal, 'id'>) => command('PUT', `/api/goals/${id}`, goal), [command])
  const deleteGoal = useCallback((id: number | string) => command('DELETE', `/api/goals/${id}`), [command])

  return useMemo(
    () => ({
      goals,
      progressMap,
      historyMap,
      addGoal,
      updateGoal,
      deleteGoal,
    }),
    [goals, progressMap, historyMap, addGoal, updateGoal, deleteGoal],
  )
}
