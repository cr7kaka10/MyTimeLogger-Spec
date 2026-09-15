// ui/src/App.tsx
import './index.css'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'

import { TimerPage } from './components/Timer/TimerPage'
import { TimeBookPage } from './components/TimeBook/TimeBookPage'
import { HabitsPage } from './components/Habits/HabitsPage'
import { GoalsPage } from './components/Goals/GoalsPage'
import { RewardsPage } from './components/Rewards/RewardsPage'
import { SettingsPage } from './components/Settings/SettingsPage'
import { SleepPage } from './components/Sleep/SleepPage'
import { ChecklistPage } from './components/Checklist/ChecklistPage'
import { UnifiedChecklistPage } from './pages/UnifiedChecklistPage'
import { BackpackPage } from './components/Backpack/BackpackPage'
import { ExercisePage } from './pages/ExercisePage'
import { LearningPage } from './components/Learning/LearningPage'
import { LoginPage } from './components/Auth/LoginPage'
import { getRawDb, setCoreActionSyncRequester, syncNow } from './db'

import { useGoals } from './hooks/useGoals'
import { useHabits } from './hooks/useHabits'
import { useRewards } from './hooks/useRewards'
import { useSettings } from './hooks/useSettings'
import { useSleep } from './hooks/useSleep'
import { useTimeBook } from './hooks/useTimeBook'
import { useTimer } from './hooks/useTimer'
import { formatTaskFocusBlockedMessage, type TaskFocusResult } from './hooks/taskFocusRouting'
import { useBackpack } from './hooks/useBackpack'
import { useChecklist } from './hooks/useChecklist'
import { useLedger } from './hooks/useLedger'
import { MainLayout } from './pages/MainLayout'
import { LedgerSheet } from './components/Rewards/LedgerSheet'
import { CategoryManager } from './components/Categories/CategoryManager'
import { ManagementPlanSheet } from './components/ManagementPlan/ManagementPlanSheet'
import type { MindmapNavigation, MindmapRewardReturnContext } from './components/ManagementPlan/ManagementPlanMindmap'
import { CoinExplosion } from './components/common/CoinExplosion'
import { detectPlatformRuntime, getElectronApi } from './platform'
import { resolveSavedSession, type SavedSessionVerification } from './auth/sessionState'
import { BootstrapGate } from './bootstrap'
import { emitTimerFlow } from './utils/timerFlow'
import { createBackNavigationService, runBackNavigation } from './platform/backNavigation'
import { createNotificationNavigator } from './platform/notificationNavigation'
import { getNotificationRuntime } from './platform/notificationRuntime'
import { platformFetch } from './platform/fetch'
import type { HabitSection, MainTab } from './types'
import type { ManagementPlanDraft } from './hooks/useManagementPlan'
import { mindmapRewardFingerprint, type ManagementPlanMindmap } from './hooks/useManagementPlanMindmap'
import { configureBehaviorAudit, flushBehaviorEvents, recordBehavior } from './utils/behaviorAudit'
import { createUserActionSyncScheduler } from './utils/userActionSync'

const STATUS_SWITCH_DEDUPE_MS = 300

const AppSession = ({ initialAuthenticated, onAccountActivated }: { initialAuthenticated: boolean; onAccountActivated: () => void }) => {
  const [activeTab, setActiveTab] = useState<MainTab>('timer')
  const [showLedger, setShowLedger] = useState(false)
  const [showCategoryManager, setShowCategoryManager] = useState(false)
  const [showManagementPlan, setShowManagementPlan] = useState(false)
  const [managementPlanMode, setManagementPlanMode] = useState<'draft' | 'history'>('draft')
  const [managementPlanRequest, setManagementPlanRequest] = useState('')
  const [managementPlanDraft, setManagementPlanDraft] = useState<ManagementPlanDraft | null>(null)
  const [mindmapReturnContext, setMindmapReturnContext] = useState<MindmapRewardReturnContext | null>(null)
  const [timerAiFocusRequest, setTimerAiFocusRequest] = useState(0)
  const handleTimerAiFocusHandled = useCallback(() => setTimerAiFocusRequest(0), [])
  const [explosionPos, setExplosionPos] = useState<{ x: number; y: number } | null>(null)
  const [authenticated, setAuthenticated] = useState(initialAuthenticated)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const lastStatusSwitchShortcutRef = useRef<{ at: number, traceId: string, source: string } | null>(null)
  const previousTabRef = useRef<MainTab | null>(null)
  const userActionSyncRef = useRef<ReturnType<typeof createUserActionSyncScheduler> | null>(null)
  const authenticatedRef = useRef(false)
  const auditAuthInitializedRef = useRef(false)
  const notificationNavigatorRef = useRef(createNotificationNavigator(
    () => authenticatedRef.current,
    route => setActiveTab(route),
  ))

  const timer = useTimer()
  const settings = useSettings()
  const timeBook = useTimeBook(activeTab === 'timebook', { serverUrl: settings.selectedEnvironmentProfile.serverUrl, authToken: settings.selectedEnvironmentProfile.authToken })
  const habits = useHabits()
  const goals = useGoals()
  const rewards = useRewards()
  const sleep = useSleep()
  const backpack = useBackpack()
  const ledgerHook = useLedger()

  const handleNavigate = useCallback((tab: MainTab) => {
    if (tab === 'timebook') timeBook.resetToToday()
    userActionSyncRef.current?.request()
    setActiveTab(current => { if (current !== tab) { previousTabRef.current = current; recordBehavior('navigation.tab_opened', { tab }) }; return tab })
  }, [timeBook.resetToToday])

  const handleMindmapNavigate = useCallback((intent: MindmapNavigation) => {
    if (intent.returnContext) setMindmapReturnContext(intent.returnContext)
    handleNavigate(intent.tab)
  }, [handleNavigate])

  useEffect(() => {
    configureBehaviorAudit(authenticated ? settings.selectedEnvironmentProfile : null)
    if (auditAuthInitializedRef.current) recordBehavior(authenticated ? 'auth.signed_in' : 'auth.signed_out')
    auditAuthInitializedRef.current = true
    if (authenticated) void flushBehaviorEvents()
  }, [authenticated, settings.selectedEnvironmentProfile])

  useEffect(() => {
    if (!authenticated) return
    const actionSync = createUserActionSyncScheduler(() => syncNow({ reason: 'user-action' }))
    userActionSyncRef.current = actionSync
    const requestActionSync = () => actionSync.request()
    setCoreActionSyncRequester(requestActionSync)
    window.addEventListener('click', requestActionSync)
    window.addEventListener('change', requestActionSync)
    window.addEventListener('submit', requestActionSync)
    return () => {
      window.removeEventListener('click', requestActionSync)
      window.removeEventListener('change', requestActionSync)
      window.removeEventListener('submit', requestActionSync)
      actionSync.dispose()
      setCoreActionSyncRequester(null)
      if (userActionSyncRef.current === actionSync) userActionSyncRef.current = null
    }
  }, [authenticated])

  useEffect(() => {
    if (!authenticated) return
    const onClick = (event: MouseEvent) => {
      const target = (event.target as Element | null)?.closest('button,[role="button"],input[type="submit"]') as HTMLElement | null
      if (!target) return
      const dialog = target.closest('[role="dialog"]') as HTMLElement | null
      const surface = dialog?.getAttribute('aria-label')?.includes('管理方案') ? 'management_plan' : activeTab
      recordBehavior('control.activated', { surface, control: target.getAttribute('aria-label') || target.textContent?.trim().slice(0, 80) || target.tagName.toLowerCase() })
    }
    const onInput = (event: Event) => {
      const target = event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null
      if (!target || target.type === 'password' || target.type === 'hidden') return
      const dialog = target.closest('[role="dialog"]') as HTMLElement | null
      const surface = dialog?.getAttribute('aria-label')?.includes('管理方案') ? 'management_plan' : activeTab
      recordBehavior('input.changed', { surface, control: target.getAttribute('aria-label') || target.name || target.id || target.tagName.toLowerCase() })
    }
    window.addEventListener('click', onClick, true)
    window.addEventListener('change', onInput, true)
    return () => { window.removeEventListener('click', onClick, true); window.removeEventListener('change', onInput, true) }
  }, [activeTab, authenticated])

  useEffect(() => {
    const navigate = (event: Event) => {
      const page = window as typeof window & { __mtlPendingNavigation?: { route: string, focusAi: boolean } }
      const detail = page.__mtlPendingNavigation ?? (event as CustomEvent).detail
      delete page.__mtlPendingNavigation
      if (detail === 'timer' || detail?.route === 'timer') {
        handleNavigate('timer')
        if (detail?.focusAi) setTimerAiFocusRequest(current => current + 1)
      }
    }
    window.addEventListener('mtl:navigate', navigate)
    const pending = (window as typeof window & { __mtlPendingNavigation?: { route: string, focusAi: boolean } }).__mtlPendingNavigation
    if (pending) navigate(new CustomEvent('mtl:navigate', { detail: pending }))
    return () => window.removeEventListener('mtl:navigate', navigate)
  }, [handleNavigate])

  useEffect(() => {
    authenticatedRef.current = authenticated
    if (authenticated) notificationNavigatorRef.current.consumePending()
  }, [authenticated])

  useEffect(() => {
    let remove = () => {}; let closed = false
    void getNotificationRuntime()?.notifications.subscribe(route => notificationNavigatorRef.current.open(route)).then(unsubscribe => { if (closed) unsubscribe(); else remove = unsubscribe }).catch(() => {})
    const expire = () => {
      if (detectPlatformRuntime() !== 'capacitor-android') { setAuthenticated(false); return }
      void settings.clearActiveSession().then(() => setAuthenticated(false)).catch(() => {})
    }
    const challenge = () => {
      if (detectPlatformRuntime() !== 'capacitor-android') { setAuthenticated(false); return }
      void settings.verifyActiveSession().then(result => {
        if (result !== 'invalid') return
        return settings.clearActiveSession().then(() => setAuthenticated(false))
      }).catch(() => {})
    }
    window.addEventListener('mtl:auth-expired', expire)
    window.addEventListener('mtl:auth-challenge', challenge)
    return () => { closed = true; remove(); window.removeEventListener('mtl:auth-expired', expire); window.removeEventListener('mtl:auth-challenge', challenge) }
  }, [settings.clearActiveSession, settings.verifyActiveSession])

  useEffect(() => createBackNavigationService().subscribe(() => runBackNavigation(() => {
    if (showOnboarding) { setShowOnboarding(false); return true }
    if (showLedger) { setShowLedger(false); return true }
    if (showCategoryManager) { setShowCategoryManager(false); return true }
    if (showManagementPlan) { recordBehavior('navigation.back', { surface: 'management_plan' }); setShowManagementPlan(false); return true }
    return false
  }, () => {
    const previous = previousTabRef.current
    if (!previous) return false
    previousTabRef.current = null; recordBehavior('navigation.back', { tab: previous }); setActiveTab(previous)
    return true
  })), [showCategoryManager, showLedger, showManagementPlan, showOnboarding])

  const handleStartLearningFocus = useCallback(async (categoryId: number | null, taskTitle: string): Promise<TaskFocusResult> => {
    const requestedCategory = timer.categories.find(category => category.id === categoryId)
    const resolvedCategoryId = requestedCategory?.id ?? timer.categories.find(category => category.name === '输入')?.id
    if (!resolvedCategoryId) return { status: 'unavailable', reason: 'missing-category' }
    const result = await timer.requestTaskFocus(resolvedCategoryId, taskTitle)
    if (result.status === 'started' || result.status === 'retargeted' || result.status === 'switched') setActiveTab('timer')
    return result
  }, [timer.categories, timer.requestTaskFocus])

  const handleStartExerciseFocus = useCallback(async (title: string) => {
    const exerciseCategory = timer.categories.find(category => category.name === '运动')
    if (!exerciseCategory) return false
    const result = await timer.requestTaskFocus(exerciseCategory.id, title)
    if (result.status === 'blocked') alert(formatTaskFocusBlockedMessage(result.sourceCategoryName))
    if (result.status === 'unavailable' || result.status === 'blocked') return false
    setActiveTab('timer')
    return true
  }, [timer.categories, timer.requestTaskFocus])

  const handleHabitSectionChange = useCallback((_section: HabitSection) => {}, [])

  const openManagementPlan = useCallback((requestText = '') => {
    setManagementPlanMode('draft')
    setManagementPlanRequest(requestText.trim())
    setManagementPlanDraft(null)
    setShowManagementPlan(true)
  }, [])

  const openManagementPlanDraft = useCallback((draft: ManagementPlanDraft) => {
    setManagementPlanMode('draft')
    setManagementPlanRequest('')
    setManagementPlanDraft(draft)
    setShowManagementPlan(true)
  }, [])

  const openManagementPlanHistory = useCallback(() => {
    setManagementPlanMode('history')
    setShowManagementPlan(true)
  }, [])

  useEffect(() => {
    if (!mindmapReturnContext) return
    const { serverUrl, authToken } = settings.selectedEnvironmentProfile
    if (!serverUrl || !authToken) return
    let cancelled = false
    let checking = false
    const checkForSavedReward = async () => {
      if (checking) return
      checking = true
      try {
        const response = await platformFetch(`${serverUrl.replace(/\/$/, '')}/api/management-plans/mindmap`, { headers: { Authorization: `Bearer ${authToken}`, 'X-Auth-Token': authToken } })
        const snapshot = await response.json().catch(() => null) as ManagementPlanMindmap | null
        if (!response.ok || !snapshot || cancelled) return
        const fingerprint = mindmapRewardFingerprint(snapshot, mindmapReturnContext)
        if (fingerprint === mindmapReturnContext.fingerprint) return
        setMindmapReturnContext(null)
        setManagementPlanMode('history')
        setManagementPlanRequest('')
        setManagementPlanDraft(null)
        setShowManagementPlan(true)
      } catch {
        // A failed polling request must not be treated as a successful save.
      } finally {
        checking = false
      }
    }
    void checkForSavedReward()
    const timerId = window.setInterval(() => { void checkForSavedReward() }, 1000)
    return () => { cancelled = true; window.clearInterval(timerId) }
  }, [mindmapReturnContext, settings.selectedEnvironmentProfile])

  const handleNavigateToSleep = useCallback((date: string) => {
    sleep.setSelectedDate(date)
    setActiveTab('sleep')
  }, [sleep])

  const handleOpenSleepFromSettings = useCallback(() => handleNavigate('sleep'), [handleNavigate])
  const handleOpenCategoryManager = useCallback(() => setShowCategoryManager(true), [])
  const handleCloseCategoryManager = useCallback(() => setShowCategoryManager(false), [])

  useEffect(() => {
    const handleShortcut = (_event: any, raw: any) => {
      const payload = typeof raw === 'string'
        ? { type: raw, source: 'unknown', traceId: `shortcut-${Date.now()}` }
        : {
            type: raw?.type,
            source: raw?.source || 'unknown',
            traceId: raw?.traceId || `shortcut-${Date.now()}`,
            traceStep: raw?.traceStep || 0,
          }
      const type = payload.type
      if (type !== 'status-switch') return
      emitTimerFlow('App', 'shortcut.received', {
        traceId: payload.traceId,
        traceStep: payload.traceStep,
        source: payload.source,
        result: 'received',
      })
      const now = Date.now()
      const last = lastStatusSwitchShortcutRef.current
      if (last && now - last.at < STATUS_SWITCH_DEDUPE_MS) {
        emitTimerFlow('App', 'shortcut.deduped', {
          source: payload.source,
          traceId: payload.traceId,
          keptSource: last.source,
          keptTraceId: last.traceId,
          result: 'deduped',
        })
        emitTimerFlow('App', 'flow.completed', { traceId: payload.traceId, result: 'deduped' })
        return
      }
      lastStatusSwitchShortcutRef.current = { at: now, traceId: payload.traceId, source: payload.source }
      emitTimerFlow('App', 'shortcut.dispatched', {
        source: payload.source,
        traceId: payload.traceId,
        result: 'dispatched',
      })
      setActiveTab('timer')
      timer.requestStatusSwitch(payload.traceId)
    }

    const handleLocalShortcut = (event: Event) => {
      const detail = (event as CustomEvent).detail
      handleShortcut(null, typeof detail === 'string' ? { type: detail, source: 'renderer-local' } : detail)
    }

    window.addEventListener('local-shortcut-trigger', handleLocalShortcut)
    const unsubscribe = getElectronApi()?.onShortcutTrigger?.(handleShortcut)
    return () => {
      window.removeEventListener('local-shortcut-trigger', handleLocalShortcut)
      if (typeof unsubscribe === 'function') unsubscribe()
    }
  }, [timer.requestStatusSwitch])

  useEffect(() => {
    const handleExplosion = (e: any) => {
      const x = e.detail?.x ?? (typeof window !== 'undefined' ? window.innerWidth / 2 : 200)
      const y = e.detail?.y ?? (typeof window !== 'undefined' ? window.innerHeight / 2 : 400)
      setExplosionPos({ x, y })
    }
    window.addEventListener('coin-explosion' as any, handleExplosion)
    return () => window.removeEventListener('coin-explosion' as any, handleExplosion)
  }, [])

  const page = useMemo(() => {
    if (activeTab === 'backpack') return <BackpackPage {...backpack} />
    if (activeTab === 'exercise') return <ExercisePage theme={settings.theme} onToggleTheme={settings.toggleTheme} onStartFocus={handleStartExerciseFocus} />
    if (activeTab === 'learning') return <LearningPage onNavigate={handleNavigate} onStartFocus={handleStartLearningFocus} runtime={{ serverUrl: settings.selectedEnvironmentProfile.serverUrl, authToken: settings.selectedEnvironmentProfile.authToken }} />
    if (activeTab === 'timer') return <TimerPage {...timer} theme={settings.theme} onToggleTheme={settings.toggleTheme} onNavigate={handleNavigate} onOpenLedger={() => setShowLedger(true)} onOpenSettings={() => handleNavigate('settings')} runtime={{ serverUrl: settings.selectedEnvironmentProfile.serverUrl, authToken: settings.selectedEnvironmentProfile.authToken }} onRecordFlashCard={timeBook.recordFlashCard} focusAiRequest={timerAiFocusRequest} onFocusAiHandled={handleTimerAiFocusHandled} />
    if (activeTab === 'timebook') return <TimeBookPage {...timeBook} onNavigate={handleNavigate} onNavigateToSleep={handleNavigateToSleep} />
      if (activeTab === 'sleep') return (
        <SleepPage {...sleep}
          onPickImage={sleep.pickImage}
          onSleepAnalysis={sleep.runAnalysis}
          onFullAnalysis={sleep.runFullAnalysis}
          onForceRefresh={sleep.forceRefresh}
        />
      )
    if (activeTab === 'settings') return (
      showCategoryManager
        ? <CategoryManager onClose={handleCloseCategoryManager} />
        : <SettingsPage {...settings} onOpenSleep={handleOpenSleepFromSettings} onOpenCategoryManager={handleOpenCategoryManager} onSignedOut={() => setAuthenticated(false)} />
    )
    if (activeTab === 'goals') return <GoalsPage {...goals} balance={timer.balance} activeSection="goals" onSectionChange={handleHabitSectionChange} categories={timeBook.categories} />
    if (activeTab === 'rewards') return <RewardsPage {...rewards} activeSection="rewards" onSectionChange={handleHabitSectionChange} ledgerHook={ledgerHook} />
    if (activeTab === 'checklist') return (
      <UnifiedChecklistPage
        habits={habits}
        timeBook={timeBook}
        timer={timer}
        onNavigate={handleNavigate}
      />
    )

    // 'habits' tab 已移除，如果有任何遗留引用会 fallback 到 checklist
    return (
      <UnifiedChecklistPage
        habits={habits}
        timeBook={timeBook}
        timer={timer}
        onNavigate={handleNavigate}
      />
    )
    }, [activeTab, goals, habits, backpack, ledgerHook, showCategoryManager, handleHabitSectionChange, handleNavigate, handleNavigateToSleep, handleStartExerciseFocus, handleStartLearningFocus, rewards, settings, sleep, timeBook, timer, handleOpenSleepFromSettings, handleOpenCategoryManager, handleCloseCategoryManager, openManagementPlan, openManagementPlanDraft, timerAiFocusRequest])

  const hasSavedToken = Boolean(settings.selectedEnvironmentProfile.authToken)
  const waitingForSavedToken = hasSavedToken && settings.connectionStatus === 'checking'
  const savedLoginReady = hasSavedToken && settings.connectionStatus === 'connected'
  useEffect(() => {
    if (detectPlatformRuntime() !== 'capacitor-android') return
    const verification: SavedSessionVerification = settings.connectionStatus === 'connected' ? 'connected'
      : settings.connectionStatus === 'unauthorized' ? 'unauthorized'
        : settings.connectionStatus === 'checking' ? 'checking' : 'network_failed'
    const session = resolveSavedSession(settings.selectedEnvironmentProfile.authToken, verification)
    if (session.authenticated) setAuthenticated(true)
    else if (session.clearToken) void settings.clearActiveSession().then(() => setAuthenticated(false)).catch(() => {})
  }, [settings.clearActiveSession, settings.connectionStatus, settings.selectedEnvironmentProfile.authToken])
  const needsLogin = !authenticated
  const restoringAndroidProfile = detectPlatformRuntime() === 'capacitor-android' && !settings.profileReady
  const onboardingKey = `mtl.familyOnboardingSeen.${settings.activeEnvironment}.${settings.selectedEnvironmentProfile.username || 'user'}`
  const completeOnboarding = useCallback(() => {
    window.localStorage.setItem(onboardingKey, '1')
    setShowOnboarding(false)
  }, [onboardingKey])

  const body = restoringAndroidProfile ? <main className="theme-page min-h-screen" /> : needsLogin ? (
    <LoginPage
      environment={settings.activeEnvironment}
      serverUrl={settings.selectedEnvironmentProfile.serverUrl || (settings.activeEnvironment === 'development' ? settings.settings.server_url : '')}
      defaultUsername={settings.selectedEnvironmentProfile.username}
      savedLoginReady={savedLoginReady}
      checkingSavedLogin={waitingForSavedToken}
      onLogin={settings.loginEnvironment}
      onServerUrlChange={value => settings.updateEnvironmentSetting('server_url', value, settings.activeEnvironment)}
      onAuthenticated={(accountActivated) => {
        setAuthenticated(true)
        if (window.localStorage.getItem(onboardingKey) !== '1') setShowOnboarding(true)
        if (accountActivated) onAccountActivated()
      }}
    />
  ) : (
    <MainLayout activeTab={activeTab} onTabChange={handleNavigate} balance={timer.balance} theme={settings.theme} onToggleTheme={settings.toggleTheme} onOpenLedger={() => setShowLedger(true)} onOpenManagementPlanHistory={openManagementPlanHistory}>
      {page}

      {/* 全局待领取奖励横幅 */}
      {rewards.unclaimedRewards.length > 0 && activeTab !== 'rewards' && activeTab !== 'exercise' && (
        <div className="fixed bottom-[72px] left-1/2 -translate-x-1/2 w-[calc(100%-32px)] max-w-[448px] flex items-center justify-between p-3.5 bg-blue-50/95 backdrop-blur border border-blue-200 rounded-2xl shadow-lg z-40 transition-all">
          <div className="text-sm text-blue-800 font-semibold flex items-center gap-2">
            <span className="text-xl">🎁</span>
            <div className="flex flex-col">
              <span>待领取奖励 ({rewards.unclaimedRewards.length} 项)</span>
              <span className="text-xs text-blue-600/80">共 {rewards.unclaimedRewards.reduce((s: any, x: any) => s + x.coins, 0).toFixed(2)} 🪙</span>
            </div>
          </div>
          <button
            onClick={() => rewards.claimRewards(rewards.unclaimedRewards.map((r: any) => r.id))}
            className="px-5 py-2.5 text-sm font-bold text-white bg-blue-600 rounded-xl active:scale-95 hover:bg-blue-700 transition-all shadow-md"
          >
            一键领取
          </button>
        </div>
      )}

      {showLedger && <LedgerSheet {...ledgerHook} onClose={() => setShowLedger(false)} />}
      <ManagementPlanSheet open={showManagementPlan} mode={managementPlanMode} runtime={{ serverUrl: settings.selectedEnvironmentProfile.serverUrl, authToken: settings.selectedEnvironmentProfile.authToken }} initialRequest={managementPlanRequest} initialDraft={managementPlanDraft} onNavigate={handleMindmapNavigate} onClose={() => setShowManagementPlan(false)} />
      {explosionPos && <CoinExplosion x={explosionPos.x} y={explosionPos.y} onComplete={() => setExplosionPos(null)} />}
      {showOnboarding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 backdrop-blur-sm">
          <div className="w-full max-w-[520px] rounded-3xl bg-white p-6 shadow-2xl">
            <div className="mb-5">
              <div className="mb-3 inline-flex rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">首次使用</div>
              <h2 className="text-xl font-bold text-gray-950">先完成我的服务配置</h2>
              <p className="mt-2 text-sm leading-6 text-gray-500">TickTick、大模型和 aTimeLogger 按当前登录用户单独配置；S3 全库容灾由服务管理者统一管理，未配置时不会读取别人的数据。</p>
            </div>
            <div className="space-y-3 text-sm text-gray-600">
              <div className="rounded-2xl bg-gray-50 p-4">
                <div className="font-semibold text-gray-900">个人绑定</div>
                <div className="mt-1 text-gray-500">进入设置页后打开“我的服务配置”，可以在线填写或导入标准 JSON 配置文件。</div>
              </div>
            </div>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <button type="button" onClick={completeOnboarding} className="h-11 rounded-2xl bg-gray-100 text-sm font-semibold text-gray-600">跳过</button>
              <button type="button" onClick={() => { setActiveTab('settings'); completeOnboarding() }} className="h-11 rounded-2xl bg-blue-600 text-sm font-bold text-white shadow-[0_12px_30px_rgba(37,99,235,0.25)]">去设置查看</button>
            </div>
          </div>
        </div>
      )}
    </MainLayout>
  )

  return body
}

const App = () => {
  const [accountEpoch, setAccountEpoch] = useState(0)
  const [initialAuthenticated, setInitialAuthenticated] = useState(false)
  return <AppSession key={accountEpoch} initialAuthenticated={initialAuthenticated} onAccountActivated={() => {
    setInitialAuthenticated(true)
    setAccountEpoch(value => value + 1)
  }} />
}

const root = createRoot(document.getElementById('root') as HTMLElement)
root.render(<BootstrapGate><App /></BootstrapGate>)
