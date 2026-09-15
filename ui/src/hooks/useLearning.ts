import { useState, useCallback, useEffect } from 'react'
import { getDatabase, pullSync } from '../db'
import { platformFetch } from '../platform/fetch'
import { parseLearningPlanJson } from '../components/Learning/learningPlanParser'
import { mapLearningTaskCategories } from './learningCategoryMapping'

export interface LearningRuntime { serverUrl: string; authToken: string }
export interface LearningCategory { id: number; name: '输入' | '输出' }
export interface LearningTask { id: string; kr_id: string; title: string; status: number; category_id?: number; category_name?: string | null; priority?: number; reward?: number; due_date?: string; created_at: string }
export interface LearningKR { id: string; objective_id: string; title: string; target_value: number; current_value: number; created_at: string; tasks?: LearningTask[] }
export interface LearningObjective { id: string; title: string; status: number; duration?: number; baseline?: string; target_description?: string; created_at: string; krs?: LearningKR[] }

export function sortLearningKrs(krs: LearningKR[]) {
  const number = (title: string) => /^\s*KR\s*(\d+)(?:\D|$)/i.exec(title)?.[1]
  return [...krs].sort((left, right) => {
    const leftNumber = number(left.title), rightNumber = number(right.title)
    if (leftNumber && rightNumber && Number(leftNumber) !== Number(rightNumber)) return Number(leftNumber) - Number(rightNumber)
    if (leftNumber !== rightNumber) return leftNumber ? -1 : 1
    return left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id)
  })
}

export function useLearning(runtime?: LearningRuntime) {
  const [objectives, setObjectives] = useState<LearningObjective[]>([])
  const [learningCategories, setLearningCategories] = useState<LearningCategory[]>([])
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const loadObjectives = useCallback(async () => {
    try {
      const db = await getDatabase()
      const obs = db.allRaw('SELECT * FROM learning_objectives ORDER BY created_at DESC') as LearningObjective[]
      const krs = db.allRaw('SELECT * FROM learning_krs ORDER BY created_at ASC') as LearningKR[]
      const tasks = db.allRaw('SELECT learning_tasks.*, categories.name AS category_name FROM learning_tasks LEFT JOIN categories ON learning_tasks.category_id = categories.id ORDER BY learning_tasks.created_at ASC') as LearningTask[]
      const categories = db.allRaw("SELECT id,name FROM categories WHERE is_active=1 AND name IN ('输入','输出') ORDER BY name") as LearningCategory[]
      setObjectives(obs.map(ob => ({ ...ob, krs: sortLearningKrs(krs.filter(kr => kr.objective_id === ob.id)).map(kr => ({ ...kr, tasks: tasks.filter(t => t.kr_id === kr.id) })) })))
      setLearningCategories(categories)
    } catch {
      setObjectives([])
      setLearningCategories([])
    }
  }, [])

  useEffect(() => { void loadObjectives() }, [loadObjectives, refreshTrigger])
  const refresh = useCallback(async () => { await loadObjectives() }, [loadObjectives])

  const command = useCallback(async (payload: Record<string, unknown>) => {
    if (!runtime?.serverUrl || !runtime.authToken) throw new Error('请先连接服务端')
    const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}/api/learning/plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken },
      body: JSON.stringify(payload),
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) throw new Error(body?.detail?.message || body?.detail || body?.message || '学习命令失败')
    await pullSync()
    setRefreshTrigger(value => value + 1)
    return body
  }, [runtime?.authToken, runtime?.serverUrl])

  const createObjective = useCallback((data: { title: string; duration?: number; baseline?: string; target_description?: string } | string) => {
    const value = typeof data === 'string' ? { title: data } : data
    return command({ action: 'create_objective', ...value })
  }, [command])
  const updateObjective = useCallback((id: string, data: { title?: string; duration?: number; baseline?: string; target_description?: string } | string) => {
    const value = typeof data === 'string' ? { title: data } : data
    return command({ action: 'update_objective', id, ...value })
  }, [command])
  const removeObjective = useCallback((id: string) => command({ action: 'delete_objective', id }), [command])
  const addKR = useCallback((objectiveId: string, title: string) => command({ action: 'create_kr', objective_id: objectiveId, title }), [command])
  const addTask = useCallback((krId: string, data: { title: string; category_id: number; priority?: number; reward?: number; due_date?: string }) => {
    return command({ action: 'create_task', kr_id: krId, ...data })
  }, [command])
  const toggleTask = useCallback((taskId: string, _currentStatus?: number, _krId?: string) => command({ action: 'toggle_task', id: taskId }), [command])
  const setTaskStatus = useCallback((taskId: string, status: 0 | 2) => command({ action: 'set_task_status', id: taskId, status }), [command])
  const removeTask = useCallback((taskId: string, _currentStatus?: number, _krId?: string) => command({ action: 'delete_task', id: taskId }), [command])
  const cancelChecklistTask = useCallback(async (taskId: string) => {
    if (!runtime?.serverUrl || !runtime.authToken) throw new Error('请先连接服务端')
    const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}/api/learning/checklist-links/${encodeURIComponent(taskId)}/cancel`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken },
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) throw new Error(body?.detail?.message || body?.detail || '取消清单任务失败')
    if (body?.status === 'not_linked') return false
    if (body?.status !== 'confirmed') throw new Error(body?.error_code || '取消清单任务失败')
    await pullSync()
    setRefreshTrigger(value => value + 1)
    return true
  }, [runtime?.authToken, runtime?.serverUrl])

  const importFullObjective = useCallback(async (jsonString: string) => {
    try {
      const data = JSON.parse(jsonString)
      if (!data?.title) throw new Error('Invalid JSON: missing title')
      parseLearningPlanJson(JSON.stringify(data))
      const db = await getDatabase()
      const categories = db.allRaw('SELECT id, name FROM categories WHERE is_active=1') as { id: number; name: string }[]
      const krs = mapLearningTaskCategories(data.krs, categories)
      await command({ action: 'import_full', title: data.title, duration: data.duration, baseline: data.baseline, target_description: data.target_description, krs })
      return true
    } catch (error) {
      console.error('Failed to import objective:', error)
      return false
    }
  }, [command])

  const importKRsToObjective = useCallback(async (objectiveId: string, jsonString: string, onDurationRecommended?: (duration: number, reasoning: string) => void) => {
    try {
      const data = JSON.parse(jsonString)
      const krs = Array.isArray(data) ? data : data?.krs
      if (!Array.isArray(krs)) throw new Error('Invalid JSON: missing krs array')
      parseLearningPlanJson(JSON.stringify({ krs }))
      if (data?.recommended_duration && data?.reasoning && onDurationRecommended) onDurationRecommended(data.recommended_duration, data.reasoning)
      const db = await getDatabase()
      const categories = db.allRaw('SELECT id, name FROM categories WHERE is_active=1') as { id: number; name: string }[]
      await command({ action: 'import_krs', objective_id: objectiveId, krs: mapLearningTaskCategories(krs, categories) })
      return true
    } catch (error) {
      console.error('Failed to import KRs:', error)
      return false
    }
  }, [command])

  const startFocusOnTask = useCallback((taskId: string): { taskId: string; title: string; categoryId: number | null } | null => {
    for (const obj of objectives) for (const kr of (obj.krs || [])) {
      const task = (kr.tasks || []).find(item => item.id === taskId)
      if (task) return { taskId: task.id, title: task.title, categoryId: task.category_id ?? null }
    }
    return null
  }, [objectives])

  return { objectives, learningCategories, createObjective, addObjective: createObjective, updateObjective, removeObjective, addKR, addTask, toggleTask, setTaskStatus, removeTask, cancelChecklistTask, refresh, importFullObjective, importKRsToObjective, startFocusOnTask }
}
