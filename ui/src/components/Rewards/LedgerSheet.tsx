// ui/src/components/Rewards/LedgerSheet.tsx
import { memo, useState } from 'react'
import type { LedgerEntry, LedgerFilter } from '../../types'
import type { UseLedgerReturn } from '../../hooks/useLedger'
import { BottomSheet } from '../common/BottomSheet'
import { getDatabase } from '../../db'
import { shareTextFile } from '../../platform/fileShare'
import { buildLedgerCsv, ledgerCsvFilename } from '../../utils/ledgerCsv'
import { ledgerSourceName, parseLedgerDisplay } from '../../utils/ledgerDisplay'

interface LedgerSheetProps extends UseLedgerReturn {
  onClose: () => void
}

const FILTERS: { key: LedgerFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'income', label: '收入' },
  { key: 'expense', label: '支出' },
  { key: 'reward', label: '兑换' },
]

export const formatCoinAmount = (amount: number): string => {
  if (!Number.isFinite(amount)) return '0'
  return Number(amount.toFixed(2)).toString()
}

export const getLedgerOccurredTime = (item: Pick<LedgerEntry, 'occurred_at'>): string => (item.occurred_at || '').slice(11, 16)

const formatSignedCoinAmount = (amount: number): string => {
  const value = formatCoinAmount(Math.abs(amount))
  return `${amount >= 0 ? '+' : '-'}${value}`
}

const BADGE_STYLES: Record<string, string> = {
  习惯: 'border-emerald-200 bg-emerald-50 text-emerald-600',
  清单: 'border-blue-200 bg-blue-50 text-blue-600',
  目标: 'border-purple-200 bg-purple-50 text-purple-600',
  学习: 'border-amber-200 bg-amber-50 text-amber-600',
  运动: 'border-orange-200 bg-orange-50 text-orange-600',
  饮食: 'border-lime-200 bg-lime-50 text-lime-600',
  兑换: 'border-pink-200 bg-pink-50 text-pink-600',
}

export { parseLedgerDisplay } from '../../utils/ledgerDisplay'

const TypeBadge = ({ label }: { label: string }) => (
  <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-bold leading-none ${BADGE_STYLES[label] || 'border-gray-200 bg-gray-50 text-gray-500'}`}>
    {label}
  </span>
)

const getLedgerIcon = (item: LedgerEntry) => {
  const display = parseLedgerDisplay(item)
  const isFail = display.isFail

  if (isFail) {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded bg-red-500 text-white">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </span>
    )
  }
  // 所有成功打卡、任务完成统一为绿色对号
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded bg-emerald-500 text-white">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
    </span>
  )
}

export const exportLedgerCsv = async (filter: LedgerFilter, load: UseLedgerReturn['exportEntries'], deliver = shareTextFile) => {
  const rows = await load(filter)
  await deliver(ledgerCsvFilename(filter), buildLedgerCsv(rows), { mimeType: 'text/csv;charset=utf-8', dialogTitle: '分享金币流水' })
  return rows.length
}

export const LedgerSheet = memo(({ groupedEntries, filter, setFilter, summary, hasMore, isLoadingMore, loadMore, exportEntries, onClose, refresh }: LedgerSheetProps) => {
  const [detail, setDetail] = useState<LedgerEntry | null>(null)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; item: LedgerEntry } | null>(null)
  const [isExporting, setIsExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  const handleExport = async () => {
    if (isExporting) return
    setIsExporting(true); setExportError('')
    try { await exportLedgerCsv(filter, exportEntries) }
    catch { setExportError('导出失败，请重试') }
    finally { setIsExporting(false) }
  }

  const handleContextMenu = (e: React.MouseEvent, item: LedgerEntry) => {
    e.preventDefault()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      item,
    })
  }

  const handleDelete = async (item: LedgerEntry) => {
    const descText = item.description || ledgerSourceName(item.source_type)
    const amountText = `${formatSignedCoinAmount(Number(item.amount))}`
    const ok = window.confirm(
      `确定要直接从数据库删除该条金币流水记录吗？\n\n「${descText}」\n金额: ${amountText} 🪙\n\n⚠️ 此操作为物理删除，会自动更新金币总额，且删除后不可恢复。`
    )
    if (!ok) return
    try {
      const db = await getDatabase()
      db.deleteLedgerEntry(item.id)
      await refresh()
      if (detail && detail.id === item.id) {
        setDetail(null)
      }
    } catch (err) {
      console.error('删除流水失败:', err)
      alert('删除失败，请查看控制台日志')
    }
  }

  return (
    <BottomSheet open onClose={onClose}>
      <div className="flex max-h-[70vh] flex-col">
        <div className="sticky top-0 border-b border-gray-100 bg-white p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-gray-900">💰 金币流水</h2>
            </div>
            <button onClick={onClose} className="text-gray-400 active:text-gray-600">✕</button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {FILTERS.map(f => {
              const label = f.key === 'income'
                ? `收入${formatCoinAmount(summary.income)}🪙`
                : f.key === 'expense'
                  ? `支出${formatCoinAmount(summary.expense)}🪙`
                  : f.label
              return (
                <button
                  key={f.key} type="button" onClick={() => setFilter(f.key)}
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${filter === f.key ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-500'}`}
                >{label}</button>
              )
            })}
            <button type="button" onClick={() => void handleExport()} disabled={isExporting}
              className="rounded-full border border-blue-200 bg-white px-3 py-1 text-xs font-semibold text-blue-600 disabled:text-gray-400">
              {isExporting ? '导出中…' : '导出'}
            </button>
          </div>
          {exportError && <p className="mt-2 text-xs text-red-500">{exportError}</p>}
        </div>

        <div className="flex-1 overflow-y-auto">
          {groupedEntries.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <span className="text-4xl">💰</span>
              <p className="mt-3 text-sm text-gray-400">暂无流水记录</p>
            </div>
          ) : (
            <div className="px-4 py-3">
              {groupedEntries.map(group => {
                const parts = group.date.split('-')
                const d = parts.length === 3
                  ? new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
                  : new Date(group.date)
                const dayNames = ['日', '一', '二', '三', '四', '五', '六']
                const dateLabel = `${group.date} 周${dayNames[d.getDay()]}`
                return (
                  <div key={group.date} className="mb-4">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-blue-400" />
                      <span className="text-xs font-semibold text-gray-500">{dateLabel}</span>
                      {group.income > 0 && <span className="text-xs font-semibold text-red-500">收入{formatCoinAmount(group.income)}🪙</span>}
                      {group.expense > 0 && <span className="text-xs font-semibold text-green-500">支出{formatCoinAmount(group.expense)}🪙</span>}
                    </div>
                    <div className="ml-1 space-y-2 border-l-2 border-gray-100 pl-4">
                      {group.items.map(item => {
                        const icon = getLedgerIcon(item)
                        const display = parseLedgerDisplay(item)
                        const isPositive = item.amount >= 0
                        const time = getLedgerOccurredTime(item)
                        return (
                          <button
                            key={item.id} type="button" onClick={() => setDetail(item)}
                            onContextMenu={(e) => handleContextMenu(e, item)}
                            className="flex w-full items-center gap-3 rounded-lg bg-white py-1 text-left active:bg-gray-50"
                          >
                            <span className="flex h-5 w-5 items-center justify-center text-lg">{icon}</span>
                            <span className="flex-1 truncate text-sm text-gray-700 flex items-center gap-1.5">
                              <TypeBadge label={display.label} />
                              <span className="truncate">{display.title}</span>
                            </span>
                            <span className={`text-sm font-bold ${isPositive ? 'text-red-500' : 'text-green-500'}`}>
                              {formatSignedCoinAmount(Number(item.amount))} 🪙
                            </span>
                            <span className="w-10 text-right text-xs text-gray-400">{time}</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
              {hasMore && (
                <div className="pt-1 pb-2">
                  <button
                    type="button"
                    onClick={loadMore}
                    disabled={isLoadingMore}
                    className="h-10 w-full rounded-lg bg-gray-100 text-sm font-semibold text-gray-600 active:bg-gray-200 disabled:text-gray-400"
                  >
                    {isLoadingMore ? '加载中...' : '加载更多'}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 右键菜单 */}
      {contextMenu && (
        <>
          <div
            className="fixed inset-0 z-40 bg-transparent"
            onClick={() => setContextMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault()
              setContextMenu(null)
            }}
          />
          <div
            className="fixed z-50 w-32 rounded-lg border border-gray-100 bg-white py-1 shadow-lg"
            style={{
              top: `${contextMenu.y}px`,
              left: `${contextMenu.x}px`,
            }}
          >
            <button
              type="button"
              onClick={() => {
                handleDelete(contextMenu.item)
                setContextMenu(null)
              }}
              className="flex w-full items-center px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 active:bg-red-100 font-medium"
            >
              🗑️ 删除记录
            </button>
          </div>
        </>
      )}

      {/* 详情弹窗 */}
      {detail && (
        <BottomSheet open onClose={() => setDetail(null)}>
          <div className="space-y-4 p-4">
            <h3 className="text-lg font-bold text-gray-900">流水详情</h3>
            <div className="space-y-3 rounded-xl bg-gray-50 p-4 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">类型</span>
                <span className="font-semibold text-gray-900">{ledgerSourceName(detail.source_type)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">金额</span>
                <span className={`font-bold ${detail.amount >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {formatSignedCoinAmount(Number(detail.amount))} 🪙
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">描述</span>
                <span className="text-right text-gray-900">{detail.description || '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">时间</span>
                <span className="text-gray-900">{detail.created_at || '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">流水 ID</span>
                <span className="font-mono text-xs text-gray-400">#{detail.id}</span>
              </div>
            </div>
          </div>
        </BottomSheet>
      )}

    </BottomSheet>
  )
})

LedgerSheet.displayName = 'LedgerSheet'
