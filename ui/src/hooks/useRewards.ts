// ui/src/hooks/useRewards.ts
import { useCallback, useEffect, useMemo, useState } from 'react'
import { requireActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import type { Reward } from '../types'
import { getDatabase, pullSync } from '../db'
import { playAudioCue } from '../utils/audio'
import { useEventRefresh } from './useEventRefresh'
import { notifyRewardCatalogUpdated } from './rewardCatalogRefresh'

export interface UseRewardsReturn {
  balance: number
  rewards: Reward[]
  ledger: { id: number; amount: number; description: string; created_at: string }[]
  unclaimedRewards: any[]
  buyReward: (id: string | number, amount?: number, note?: string) => Promise<void>
  addReward: (title: string, icon: string, price: number, description?: string, unlockTaskId?: string | null, unlockTaskTitle?: string | null, unlockSourceType?: string | null, unlockSourceId?: string | null, inventoryMode?: string, inventoryLimit?: number | null, unlockRequiredCount?: number, redemptionMode?: string, fulfillmentMode?: 'immediate' | 'fragment', fragmentTargetCount?: number) => Promise<any>
  updateReward: (id: string | number, title: string, icon: string, price: number, description?: string, unlockTaskId?: string | null, unlockTaskTitle?: string | null, unlockSourceType?: string | null, unlockSourceId?: string | null, inventoryMode?: string, inventoryLimit?: number | null, unlockRequiredCount?: number, redemptionMode?: string, fulfillmentMode?: 'immediate' | 'fragment', fragmentTargetCount?: number) => Promise<any>
  deleteReward: (id: string | number) => Promise<void>
  claimRewards: (ids: string[]) => void
  refresh: () => void
}

export const useRewards = (): UseRewardsReturn => {
  const [balance, setBalance] = useState(0)
  const [rewards, setRewards] = useState<Reward[]>([])
  const [ledger, setLedger] = useState<any[]>([])
  const [unclaimedRewards, setUnclaimedRewards] = useState<any[]>([])
  const eventRefresh = useEventRefresh(['balance-updated', 'sync-pull-complete'])
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  useEffect(() => {
    getDatabase().then(db => {
      setBalance(db.getBalance())
      setRewards(db.getRewards() as any[])
      setLedger(db.getLedger() as any[])
      setUnclaimedRewards(db.getUnclaimedRewards() as any[])
    })
  }, [refreshTrigger, eventRefresh])

  useEffect(() => {
    getDatabase().then(async db => {
      try {
        const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'rewards.list')
        const response = await fetch(`${runtime.serverUrl}/api/rewards`, { headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken } })
        if (response.ok) {
          await pullSync()
          setRefreshTrigger(previous => previous + 1)
        }
      } catch {
        // The last successful pull remains available for offline rendering.
      }
    })
  }, [])

  const buyReward = useCallback(async (id: string | number, amount?: number, note?: string) => {
    const db = await getDatabase()
    const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'rewards.buy')
    const resp = await fetch(`${runtime.serverUrl}/api/rewards/buy/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken },
      body: JSON.stringify(amount === undefined ? {} : { amount, note }),
    })
    if (!resp.ok) {
      const body = await resp.json().catch(() => null)
      throw new Error(body?.detail || '购买失败！')
    }
    await pullSync()
    setRefreshTrigger(prev => prev + 1)
    window.dispatchEvent(new CustomEvent('local-shortcut-trigger', { detail: 'balance-updated' }))
    window.dispatchEvent(new CustomEvent('balance-updated'))
  }, [])

  const claimRewards = useCallback((ids: string[]) => {
    getDatabase().then(async db => {
      try {
        if (ids.length === 0) return
        const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'rewards.claim')
        const serverUrl = runtime.serverUrl
        const authToken = runtime.authToken
        const resp = await fetch(`${serverUrl}/api/rewards/claim`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}`, 'X-Auth-Token': authToken },
          body: JSON.stringify({ ids }),
        })
        if (!resp.ok) {
          const body = await resp.json().catch(() => null)
          throw new Error(body?.detail || '领取奖励失败！')
        }
        const data = await resp.json().catch(() => ({ total_claimed: 0 }))
        const claimed = Number(data.total_claimed || 0)
        if (claimed > 0) {
          await pullSync()
          setRefreshTrigger(prev => prev + 1)
          window.dispatchEvent(new CustomEvent('local-shortcut-trigger', { detail: 'balance-updated' }))
          window.dispatchEvent(new CustomEvent('balance-updated'))
          window.dispatchEvent(new CustomEvent('coin-explosion', { detail: { amount: claimed } }))
          playAudioCue('coin')
        }
      } catch (err: any) {
        alert(err.message || '领取奖励失败！')
        console.error(err)
      }
    })
  }, [])

  const saveReward = useCallback(async (method: 'POST' | 'PUT' | 'DELETE', path: string, body?: Record<string, any>) => {
    const db = await getDatabase()
    const runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), `rewards.${method.toLowerCase()}`)
    const response = await fetch(`${runtime.serverUrl}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken },
      body: body ? JSON.stringify({ ...body, inventory_mode: body.inventory_mode === 'weekly' ? 'unlimited' : body.inventory_mode }) : undefined,
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail || '奖励保存失败')
    }
    const payload = await response.json().catch(() => ({}))
    await pullSync()
    setRefreshTrigger(previous => previous + 1)
    notifyRewardCatalogUpdated()
    return payload
  }, [])

  const addReward = useCallback((title: string, icon: string, price: number, description = '', _unlockTaskId: string | null = null, _unlockTaskTitle: string | null = null, _unlockSourceType: string | null = null, _unlockSourceId: string | null = null, inventoryMode = 'unlimited', inventoryLimit: number | null = null, unlockRequiredCount = 1, redemptionMode = 'coins', fulfillmentMode = 'immediate', fragmentTargetCount = 1) => saveReward('POST', '/api/rewards', { title, icon, price, description, inventory_mode: inventoryMode, inventory_limit: inventoryLimit, unlock_required_count: unlockRequiredCount, redemption_mode: redemptionMode, fulfillment_mode: fulfillmentMode, fragment_target_count: fragmentTargetCount }), [saveReward])
  const updateReward = useCallback((id: string | number, title: string, icon: string, price: number, description = '', _unlockTaskId: string | null = null, _unlockTaskTitle: string | null = null, _unlockSourceType: string | null = null, _unlockSourceId: string | null = null, inventoryMode = 'unlimited', inventoryLimit: number | null = null, unlockRequiredCount = 1, redemptionMode = 'coins', fulfillmentMode = 'immediate', fragmentTargetCount = 1) => saveReward('PUT', `/api/rewards/${id}`, { title, icon, price, description, inventory_mode: inventoryMode, inventory_limit: inventoryLimit, unlock_required_count: unlockRequiredCount, redemption_mode: redemptionMode, fulfillment_mode: fulfillmentMode, fragment_target_count: fragmentTargetCount }), [saveReward])
  const deleteReward = useCallback((id: string | number) => saveReward('DELETE', `/api/rewards/${id}`), [saveReward])

  const refresh = useCallback(() => setRefreshTrigger(prev => prev + 1), [])

  return useMemo(
    () => ({
      balance,
      rewards,
      ledger,
      unclaimedRewards,
      buyReward,
      addReward,
      updateReward,
      deleteReward,
      claimRewards,
      refresh
    }),
    [balance, rewards, ledger, unclaimedRewards, buyReward, addReward, updateReward, deleteReward, claimRewards, refresh]
  )
}
