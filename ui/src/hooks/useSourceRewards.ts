import { useCallback, useEffect, useRef, useState } from 'react'
import type { SourceRewardSummaryData, SourceRewardType } from '../types'
import { REWARD_CATALOG_UPDATED } from './rewardCatalogRefresh'
import { bindSourceItem, createLatestRequestGate, loadSourceReward, saveSourceCoins, unbindSourceItem } from './sourceRewardApi'
import { useEventRefresh } from './useEventRefresh'

export const useSourceRewards = (sourceType: SourceRewardType, sourceId: string, enabled = true) => {
  const [summary, setSummary] = useState<SourceRewardSummaryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const gate = useRef(createLatestRequestGate())
  const eventRefresh = useEventRefresh([REWARD_CATALOG_UPDATED, 'sync-pull-complete'])

  const refresh = useCallback(async () => {
    if (!enabled) return null
    const requestId = gate.current.next()
    setLoading(true); setError('')
    try {
      const next = await loadSourceReward(sourceType, sourceId)
      if (gate.current.isCurrent(requestId)) setSummary(next)
      return next
    } catch (reason: any) {
      if (gate.current.isCurrent(requestId)) setError(reason?.message || '奖励读取失败')
      throw reason
    } finally {
      if (gate.current.isCurrent(requestId)) setLoading(false)
    }
  }, [sourceType, sourceId, enabled])

  useEffect(() => { if (!enabled) { setLoading(false); return }; void refresh().catch(() => undefined) }, [refresh, eventRefresh, enabled])

  const saveCoins = useCallback(async (coins: number) => {
    if (!summary || !Number.isFinite(coins) || coins < 0) throw new Error('金币奖励必须是非负数字')
    await saveSourceCoins(summary, coins)
    return refresh()
  }, [summary, refresh])

  const unbindItem = useCallback(async (rewardId?: string | number) => {
    const id = rewardId ?? summary?.itemReward?.id
    if (!id) return summary
    await unbindSourceItem(sourceType, sourceId, id)
    return refresh()
  }, [summary, refresh, sourceType, sourceId])

  const bindItem = useCallback(async (rewardId: string | number) => {
    await bindSourceItem(sourceType, sourceId, rewardId)
    return refresh()
  }, [refresh, sourceType, sourceId])

  return { summary, loading, error, refresh, saveCoins, bindItem, unbindItem }
}
