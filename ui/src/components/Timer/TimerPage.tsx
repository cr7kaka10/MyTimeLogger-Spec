// ui/src/components/Timer/TimerPage.tsx
import { memo, useEffect, useRef, useState } from 'react'
import type { MainTab } from '../../types'
import type { UseTimerReturn } from '../../hooks/useTimer'
import type { ManagementPlanRuntime } from '../../hooks/useManagementPlan'
import { CategoryGrid } from './CategoryGrid'
import { CurrentTimerHeader } from './CurrentTimerHeader'
import { MicroBreakBanner } from './MicroBreakBanner'
import { PauseReasonSheet } from './PauseReasonSheet'
import { SessionSummarySheet } from './SessionSummarySheet'
import { StatusSwitchNoteSheet } from './StatusSwitchNoteSheet'
import { TimerStats } from './TimerStats'
import { TimerAiPrompt } from './TimerAiPrompt'
import { scheduleTimerInputFocus } from './summaryInputFocus'
import { createTimerInputTrace, observeEventLoopLag, type TimerInputTrace } from './timerInputTelemetry'
import { TIMER_NOTE_PRESETS } from './notePresets'

interface TimerPageProps extends UseTimerReturn {
  onNavigate: (tab: MainTab) => void
  onOpenLedger: () => void
  theme?: 'light' | 'dark'
  onToggleTheme?: () => void
  onOpenSettings?: () => void
  runtime: ManagementPlanRuntime
  onRecordFlashCard: (text: string) => Promise<string | undefined>
  focusAiRequest?: number
  onFocusAiHandled?: () => void
}

export const TimerPage = memo((props: TimerPageProps) => {
  const {
    state,
    isPaused,
    totalTodayMinutes,
    elapsedMs,
    remainingMs,
    microBreakRemainingSeconds,
    showPauseReason,
    showSummary,
    showStatusSwitchNote,
    isEarlyEnd,
    currentCategory,
    currentNote,
    categories,
    balance,
    timerSyncStatus,
    lastTimerSyncAt,
    start,
    setCurrentNote,
    togglePause,
    endSession,
    switchCategory,
    submitStatusSwitchNote,
    cancelStatusSwitchNote,
    submitSummary,
    cancelSummary,
    submitPauseReason,
    skipPauseReason,
    closeSummary,
    onNavigate,
    onOpenLedger,
    theme,
    onToggleTheme,
    runtime,
    onRecordFlashCard,
    focusAiRequest,
    onFocusAiHandled,
  } = props
  const [editingNote, setEditingNote] = useState(false)
  const [noteDraft, setNoteDraft] = useState('')
  const [selectedNotePreset, setSelectedNotePreset] = useState('')
  const noteInputRef = useRef<HTMLInputElement>(null)
  const noteTraceRef = useRef<TimerInputTrace | null>(null)
  const summaryTraceRef = useRef<TimerInputTrace | null>(null)

  useEffect(() => {
    if (!editingNote) return
    const input = noteInputRef.current
    if (!input) return
    const trace = noteTraceRef.current || createTimerInputTrace('note')
    trace.mark('sheet.mount.completed')
    const stopLag = observeEventLoopLag(trace)
    const stopFocus = scheduleTimerInputFocus(input, input.value.length, undefined, { report: (event, details) => trace.mark(event, details) })
    return () => { stopLag(); stopFocus() }
  }, [editingNote])

  const openNoteEditor = () => {
    noteTraceRef.current = createTimerInputTrace('note')
    noteTraceRef.current.mark('sheet.mount.requested')
    setNoteDraft(currentNote)
    setSelectedNotePreset(TIMER_NOTE_PRESETS.includes(currentNote as typeof TIMER_NOTE_PRESETS[number]) ? currentNote : '')
    setEditingNote(true)
  }

  const requestEndSession = () => {
    if (state === 'studying') {
      summaryTraceRef.current = createTimerInputTrace('summary')
      summaryTraceRef.current.mark('sheet.mount.requested')
    }
    endSession()
  }

  const saveNote = () => {
    setCurrentNote(selectedNotePreset || noteDraft)
    setEditingNote(false)
  }

  const commandsEnabled = timerSyncStatus === 'ready'
  const compactSyncText = commandsEnabled && lastTimerSyncAt
    ? `刚刚同步 · ${lastTimerSyncAt}`
    : ''

  return (
    <div className="flex min-h-full flex-col gap-4 bg-[#FAFAFA] p-5 pb-[calc(5rem+env(safe-area-inset-bottom,0px))]">
      <TimerStats totalTodayMinutes={totalTodayMinutes} />
      {!commandsEnabled ? (
        <div id="timer-readiness-status" className="rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-700" aria-live="polite">
          {timerSyncStatus === 'switching' ? '正在切换…' :
            timerSyncStatus === 'stopping' ? '正在停止…' :
            timerSyncStatus === 'syncing' ? '正在同步当前计时…' :
            timerSyncStatus === 'initializing' ? '正在准备计时…' :
            timerSyncStatus === 'network_failed' ? '网络不可用，恢复连接后会自动重试' :
            timerSyncStatus === 'auth_failed' ? '登录已失效，请重新登录后继续计时' :
            timerSyncStatus === 'upgrade_required' ? '客户端需要升级后才能同步当前计时' :
            '计时服务暂不可用，请检查账号和服务端配置'}
        </div>
      ) : null}
      {compactSyncText ? (
        <div data-testid="compact-sync-status" className="px-1 text-xs leading-5 text-slate-500 [overflow-wrap:anywhere]" aria-live="polite">
          {compactSyncText}
        </div>
      ) : null}
      <div className="flex min-w-0 flex-col gap-4">
        {/* 计时状态显示顶部状态栏 - 只有在有活跃分类时才显示 */}
        {state !== 'stopped' && currentCategory && (
          <>
            <CurrentTimerHeader
              state={state}
              elapsedMs={elapsedMs}
              remainingMs={remainingMs}
              currentCategory={currentCategory}
              currentNote={currentNote}
              isPaused={isPaused}
              onEditNote={openNoteEditor}
              onTogglePause={togglePause}
              onStop={requestEndSession}
              commandsEnabled={commandsEnabled}
            />
            <MicroBreakBanner remainingSeconds={microBreakRemainingSeconds} />
          </>
        )}

        {/* 分类网格始终显示 */}
        <CategoryGrid
          categories={categories}
          currentCategory={currentCategory}
          timerState={state}
          commandsEnabled={commandsEnabled}
          onStart={start}
          onSwitch={switchCategory}
        />
      </div>
      <div className="shrink-0 pt-2">
        <TimerAiPrompt
          available={Boolean(runtime.serverUrl && runtime.authToken)}
          focusRequest={focusAiRequest}
          onFocusHandled={onFocusAiHandled}
          onSubmit={onRecordFlashCard}
        />
      </div>
      {showPauseReason ? (
        <PauseReasonSheet onConfirm={submitPauseReason} onSkip={skipPauseReason} />
      ) : null}
      {showStatusSwitchNote ? (
        <StatusSwitchNoteSheet onConfirm={submitStatusSwitchNote} onClose={cancelStatusSwitchNote} />
      ) : null}
      {editingNote ? (
        <div className="fixed inset-0 z-50 flex items-end bg-black/20" onClick={() => setEditingNote(false)}>
          <div className="w-full rounded-t-2xl bg-white p-4 shadow-xl" onClick={event => event.stopPropagation()}>
            <h3 className="mb-3 text-base font-bold text-gray-900">计时备注</h3>
            <div className="mb-3 flex flex-wrap gap-2">{TIMER_NOTE_PRESETS.map(preset => (
              <button key={preset} type="button" onClick={() => { setSelectedNotePreset(preset); setNoteDraft('') }} className={`rounded-full px-4 py-1.5 text-sm ${selectedNotePreset === preset ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 active:bg-gray-200'}`}>{preset}</button>
            ))}</div>
            <input
              ref={noteInputRef}
              value={noteDraft}
              onChange={event => { setNoteDraft(event.target.value); setSelectedNotePreset('') }}
              onKeyDown={event => {
                if (event.key === 'Enter' && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                  event.preventDefault()
                  saveNote()
                }
              }}
              placeholder="备注"
              className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-sm outline-none focus:border-blue-400"
            />
            <div className="mt-3 flex gap-2">
              <button type="button" onClick={() => setEditingNote(false)} className="h-11 flex-1 rounded-xl bg-gray-100 text-sm font-semibold text-gray-500">取消</button>
              <button type="button" onClick={saveNote} className="h-11 flex-1 rounded-xl bg-blue-600 text-sm font-semibold text-white">保存</button>
            </div>
          </div>
        </div>
      ) : null}
      {showSummary ? (
        <SessionSummarySheet trace={summaryTraceRef.current || undefined} isEarlyEnd={isEarlyEnd} onSave={submitSummary} onClose={isEarlyEnd ? cancelSummary : closeSummary} />
      ) : null}
    </div>
  )
})

TimerPage.displayName = 'TimerPage'
