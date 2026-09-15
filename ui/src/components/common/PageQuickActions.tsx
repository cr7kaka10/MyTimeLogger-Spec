import { memo } from 'react'
import type { MainTab } from '../../types'
import { SyncStatusBar } from './SyncStatusBar'

interface PageQuickActionsProps {
  activeTab: MainTab
  balance: number
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  onNavigate: (tab: MainTab) => void
  onOpenLedger: () => void
  onOpenManagementPlanHistory?: () => void
  compact?: boolean
}

export const PageQuickActions = memo(({ activeTab, balance, theme, onToggleTheme, onNavigate, onOpenLedger, onOpenManagementPlanHistory, compact = false }: PageQuickActionsProps) => {
  const bal = Number.isFinite(balance) ? parseFloat(balance.toFixed(2)) : balance
  const noDrag = { WebkitAppRegion: 'no-drag' } as any
  const base = `flex items-center justify-center border border-transparent leading-none transition-all active:scale-95 hover:bg-gray-100 dark:hover:bg-gray-700 ${compact ? 'h-6 w-7 rounded-md text-sm' : 'h-9 w-9 rounded-xl text-lg'}`
  const tone = (tab: MainTab) => activeTab === tab
    ? 'border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-900/30'
    : 'bg-transparent'

  return (
    <nav aria-label="页面快捷操作" style={noDrag} className={`flex items-center justify-end ${compact ? 'gap-0.5' : 'gap-1 rounded-2xl border border-gray-100/80 bg-white/75 p-1 shadow-sm backdrop-blur dark:border-gray-700 dark:bg-gray-800/75'}`}>
      <SyncStatusBar />
      <button type="button" aria-label="明暗切换" title="明暗切换" style={noDrag} onClick={onToggleTheme} className={base}>{theme === 'dark' ? '☀️' : '🌙'}</button>
      <button type="button" aria-label="时间目标" title="时间目标" style={noDrag} onClick={() => onNavigate('goals')} className={`${base} ${tone('goals')}`}>🎯</button>
      <button type="button" aria-label="我的背包" title="我的背包" style={noDrag} onClick={() => onNavigate('backpack')} className={`${base} ${tone('backpack')}`}>🎒</button>
      <button type="button" aria-label="奖励商店" title="奖励商店" style={noDrag} onClick={() => onNavigate('rewards')} className={`${base} ${tone('rewards')}`}>🎁</button>
      {onOpenManagementPlanHistory && <button type="button" aria-label="管理方案" title="管理方案" style={noDrag} onClick={() => onOpenManagementPlanHistory()} className={base}>🧭</button>}
      <button type="button" aria-label="我的金币" title="我的金币" style={noDrag} onClick={onOpenLedger} className={`flex items-center justify-center gap-1 font-semibold text-gray-900 transition-all active:scale-95 hover:bg-gray-100 dark:text-gray-50 dark:hover:bg-gray-700 ${compact ? 'h-6 min-w-12 rounded-md px-1.5 text-xs' : 'h-9 min-w-14 rounded-xl px-2 text-sm'}`}>
        <span className={compact ? 'text-sm leading-none' : 'text-base leading-none'}>💰</span><span>{bal}</span>
      </button>
    </nav>
  )
})

PageQuickActions.displayName = 'PageQuickActions'
