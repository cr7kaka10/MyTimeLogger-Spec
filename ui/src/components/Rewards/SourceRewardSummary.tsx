import { memo } from 'react'
import type { SourceRewardType } from '../../types'
import { useSourceRewards } from '../../hooks/useSourceRewards'

interface Props { sourceType: SourceRewardType; sourceId: string; onEdit?: () => void; compact?: boolean; hideError?: boolean }

export const SourceRewardSummary = memo(({ sourceType, sourceId, onEdit, compact = false, hideError = false }: Props) => {
  const { summary, loading, error, refresh } = useSourceRewards(sourceType, sourceId)
  if (loading && !summary) return <span className="text-xs text-gray-400">奖励加载中…</span>
  if (error && !summary) return hideError ? null : <button type="button" onClick={() => void refresh().catch(() => undefined)} className="text-xs text-red-500">奖励读取失败，重试</button>
  return <button type="button" onClick={onEdit} disabled={!onEdit} className={`flex flex-wrap items-center gap-1.5 text-left text-xs text-gray-500 dark:text-gray-400 ${onEdit ? 'hover:text-blue-600' : ''}`}>
    <span aria-label="金币奖励">🪙 {summary?.coins ?? 0}</span>
    {(summary?.itemRewards || []).length ? (summary?.itemRewards || []).map(item => {
      const progress = summary?.fragmentProgress?.[String(item.id)]
      const percent = progress?.percent ?? progress?.activeUnits ?? progress?.active ?? 0
      return <span key={item.id} aria-label="物品奖励">{item.icon || '🎁'} {item.title} · {percent}%{progress?.inventoryLimit ? ` · 完整卡片本月 ${progress.inventoryUsed || 0}/${progress.inventoryLimit}` : ''}{progress?.inventoryLimitReached ? ' · 本月已满' : ''}{progress?.earliestExpiresAt ? ` · ${String(progress.earliestExpiresAt).slice(5, 10)} 到期` : ''}</span>
    }) : <span aria-label="物品奖励">🎁 未设置</span>}
    {onEdit && !compact && <span className="text-blue-500">设置</span>}
  </button>
})

SourceRewardSummary.displayName = 'SourceRewardSummary'
