// ui/src/pages/MainLayout.tsx
import { memo, type ReactNode, useEffect } from 'react'
import type { MainTab } from '../types'
import { TabBar } from '../components/common/TabBar'
import { PageQuickActions } from '../components/common/PageQuickActions'
import { getElectronApi, isElectron } from '../platform'
import { getElectronCapabilities } from '../platform/electron'

const TIMER_FLOW_PREFIX = '[timer-flow]'
export const mobileQuickActionsTopPadding = 'calc(env(safe-area-inset-top, 0px) + 0.5rem)'

interface MainLayoutProps {
  activeTab: MainTab
  onTabChange: (tab: MainTab) => void
  children: ReactNode
  balance: number
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  onOpenLedger: () => void
  onOpenManagementPlanHistory?: () => void
}

export const MainLayout = memo(({ activeTab, onTabChange, children, balance, theme, onToggleTheme, onOpenLedger, onOpenManagementPlanHistory }: MainLayoutProps) => {
  const desktopCapabilities = getElectronCapabilities()
  const noDrag = { WebkitAppRegion: 'no-drag' } as any
  const handleMinimize = () => {
    getElectronApi()?.minimizeWindow?.()
  }
  const handleClose = () => {
    getElectronApi()?.closeWindow?.()
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && (e.key === 'c' || e.key === 'C')) {
        e.preventDefault()
        const traceId = `renderer-local-${Date.now()}`
        console.info(TIMER_FLOW_PREFIX, {
          layer: 'MainLayout',
          event: 'shortcut:local-keydown',
          source: 'renderer-local',
          traceId,
          isElectron: isElectron(),
        })
        window.dispatchEvent(new CustomEvent('local-shortcut-trigger', {
          detail: { type: 'status-switch', source: 'renderer-local', traceId },
        }))
      }
      if (e.altKey && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault()
        handleClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className="theme-page relative mx-auto flex h-screen h-[100dvh] w-full max-w-[920px] flex-col overflow-hidden border-x border-gray-100/30 shadow-2xl dark:border-gray-700">
      {desktopCapabilities.windowControls && (
        <div
          className="theme-surface z-50 flex h-9 w-full shrink-0 items-center justify-between border-b px-3 select-none"
          style={{ WebkitAppRegion: 'drag' } as any}
        >
          <span className="min-w-0 flex-1 truncate text-xs font-bold text-gray-400 tracking-wider">MyTimeLogger</span>
          <div className="flex items-center gap-1" style={noDrag}>
            {activeTab !== 'settings' && (
              <>
                <PageQuickActions compact activeTab={activeTab} balance={balance} theme={theme} onToggleTheme={onToggleTheme} onNavigate={onTabChange} onOpenLedger={onOpenLedger} onOpenManagementPlanHistory={onOpenManagementPlanHistory} />
                <span className="mx-1 h-4 w-px bg-gray-200 dark:bg-gray-700" aria-hidden="true" />
              </>
            )}
            <button
              onClick={handleMinimize}
              style={noDrag}
              className="flex h-6 w-6 items-center justify-center rounded-md text-gray-400 active:bg-gray-200 md:hover:bg-gray-100 transition-colors"
              title="最小化"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 12h-15" />
              </svg>
            </button>
            <button
              onClick={handleClose}
              style={noDrag}
              className="flex h-6 w-6 items-center justify-center rounded-md text-gray-400 active:bg-red-500 active:text-white md:hover:bg-red-50 md:hover:text-red-500 transition-colors"
              title="关闭"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {!isElectron() && activeTab !== 'settings' && (
        <div className="z-50 flex shrink-0 justify-end px-5" style={{ paddingTop: mobileQuickActionsTopPadding }}>
          <PageQuickActions compact activeTab={activeTab} balance={balance} theme={theme} onToggleTheme={onToggleTheme} onNavigate={onTabChange} onOpenLedger={onOpenLedger} onOpenManagementPlanHistory={onOpenManagementPlanHistory} />
        </div>
      )}

      <main className="min-h-0 min-w-0 flex-1 overflow-y-auto pb-[calc(4rem+env(safe-area-inset-bottom,0px))]">
        {children}
      </main>
      <TabBar activeTab={activeTab} onChange={onTabChange} />
    </div>
  )
})

MainLayout.displayName = 'MainLayout'
