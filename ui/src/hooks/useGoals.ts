// ui/src/hooks/useGoals.ts
import { useCallback, useEffect, useMemo, useState } from 'react'
import { requireActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import type { Goal } from '../types'
import { getDatabase, pullSync } from '../db'
import { useEventRefresh } from './useEventRefresh'

export interface UseGoalsReturn {
  goals: Goal[]
  progressMap: Record<number | string, { current: number; target: number; percent: number }>
  historyMap: Record<number | string, Record<string, number>>
  addGoal: (g: Omit<Goal, 'id'>) => Promise<void>
  updateGoal: (id: number | string, g: Omit<Goal, 'id'>) => Promise<void>
  deleteGoal: (id: number | string) => Promise<void>
}

export const useGoals = (): UseGoalsReturn => {
  const [goals, setGoals] = useState<Goal[]>([])
  const [progressMap, setProgressMap] = useState<Record<number | string, { current: number; target: number; percent: number }>>({})
  const [historyMap, setHistoryMap] = useState<Record<number | string, Record<string, number>>>({})
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const eventRefresh = useEventRefresh(['balance-updated', 'sync-pull-complete'])

  useEffect(() => {
    getDatabase().then(db => {
      const allGoals = db.getGoals() as Goal[]
      setGoals(allGoals)

      const pMap: Record<number | string, { current: number; target: number; percent: number }> = {}
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
        const response = await fetch(`${runtime.serverUrl}/api/goals/auto_settle`, {
          method: 'POST', headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken },
        })
        if (response.ok) await pullSync()
      } catch {
        // Offline viewing continues to use the last synchronized cache.
      }
    })
  }, [])

  const command = useCallback(async (method: 'POST' | 'PUT' | 'DELETE', path: string, body?: Record<string, any>) => {
    const db = await getDatabase()
    const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), `goals.${method.toLowerCase()}`)
    const response = await fetch(`${runtime.serverUrl}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail || '目标保存失败')
    }
    await pullSync()
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
