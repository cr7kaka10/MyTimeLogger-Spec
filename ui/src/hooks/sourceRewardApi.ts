import { requireActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import { getDatabase, pullSync } from '../db'
import { platformFetch } from '../platform/fetch'
import type { SourceRewardSummaryData, SourceRewardType } from '../types'
import { notifyRewardCatalogUpdated } from './rewardCatalogRefresh'

export const SOURCE_COIN_TYPE: Record<SourceRewardType, 'task' | 'habit' | 'learning' | 'learning_objective'> = {
  checklist_task: 'task', habit: 'habit', learning_task: 'learning', learning_objective: 'learning_objective',
}

const request = async (path: string, init?: RequestInit) => {
  const db = await getDatabase()
  const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'source-reward')
  const response = await platformFetch(`${runtime.serverUrl}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken, ...(init?.headers || {}) },
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(payload?.detail || '奖励读取或保存失败')
  return payload
}

export const loadSourceReward = (sourceType: SourceRewardType, sourceId: string) =>
  request(`/api/rewards/source/${sourceType}/${encodeURIComponent(sourceId)}`) as Promise<SourceRewardSummaryData>

export const saveSourceCoins = async (summary: SourceRewardSummaryData, coins: number) => {
  await request('/api/rewards/config', { method: 'POST', body: JSON.stringify({
    item_type: SOURCE_COIN_TYPE[summary.sourceType], item_id: summary.sourceId, coins, penalty: summary.penalty,
  }) })
  notifyRewardCatalogUpdated()
}

export const bindSourceItem = async (sourceType: SourceRewardType, sourceId: string, rewardId: string | number) => {
  await request(`/api/rewards/source/${sourceType}/${encodeURIComponent(sourceId)}/bindings/${rewardId}`, { method: 'POST' })
  await pullSync()
  notifyRewardCatalogUpdated()
}

export const unbindSourceItem = async (sourceType: SourceRewardType, sourceId: string, rewardId: string | number) => {
  await request(`/api/rewards/source/${sourceType}/${encodeURIComponent(sourceId)}/bindings/${rewardId}`, { method: 'DELETE' })
  await pullSync()
  notifyRewardCatalogUpdated()
}

export const createLatestRequestGate = () => {
  let generation = 0
  return { next: () => ++generation, isCurrent: (candidate: number) => candidate === generation }
}
