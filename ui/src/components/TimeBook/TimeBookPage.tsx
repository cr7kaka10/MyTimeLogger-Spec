import { memo, useCallback, useMemo, useState, useEffect } from 'react'
import type { MainTab, SessionEditData } from '../../types'
import type { FlashCard, FlashPolishCorrectionInput, UseTimeBookReturn } from '../../hooks/useTimeBook'
import { ConfirmSheet } from '../common/ConfirmSheet'
import { EmptyState } from '../common/EmptyState'
import { SessionEditSheet } from './SessionEditSheet'
import { MarkdownInput } from '../common/MarkdownInput'
import { WeekCalendar } from '../../pages/UnifiedChecklistPage/WeekCalendar'
import { formatHoursMinutes } from '@core/displayFormat'
import { DualTrackTimeline } from './DualTrackTimeline'
import { TimeBookScheduleRail } from './TimeBookScheduleRail'
import { useExercise } from '../../hooks/useExercise'
import { planDayForDate } from '../../utils/exerciseDate'
import { formatBeijingDateTime, parseBeijingDateTimeMs } from '@core/BeijingTime'

interface TimeBookPageProps extends UseTimeBookReturn {
  onNavigate: (tab: MainTab) => void
  onNavigateToSleep?: (date: string) => void
}

const toDateTimeLocal = (value: string) => String(value || '').replace(' ', 'T').slice(0, 16)

export const newSessionDefaults = (
  sessions: Array<{ end_time?: string | null }>,
  selectedDate: string,
  now = new Date(),
): SessionEditData => {
  const endTime = formatBeijingDateTime(now)
  const nowMs = now.getTime()
  const latestEnd = sessions.reduce<string | null>((latest, session) => {
    const candidate = String(session.end_time || '')
    const candidateMs = parseBeijingDateTimeMs(candidate)
    if (!candidate.startsWith(selectedDate) || !Number.isFinite(candidateMs) || candidateMs > nowMs) return latest
    return !latest || candidateMs > parseBeijingDateTimeMs(latest) ? candidate : latest
  }, null)
  return {
    start_time: latestEnd || endTime,
    end_time: endTime,
    net_duration_minutes: 0,
    net_duration_seconds: 0,
    date: selectedDate,
    category_id: null,
    session_summary: '',
  }
}

const FlashCardEditor = ({ value, onSave, onCancel }: { value: FlashCard; onSave: (data: FlashPolishCorrectionInput) => Promise<unknown>; onCancel: () => void }) => {
  const [occurredAt, setOccurredAt] = useState(toDateTimeLocal(value.occurred_at))
  const [polishedText, setPolishedText] = useState(value.polished_text || value.original_text)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const save = async () => {
    if (!polishedText.trim()) return setError('润色内容不能为空')
    setSaving(true); setError('')
    try { await onSave({ id: value.id, occurred_at: `${occurredAt.replace('T', ' ')}:00`, corrected_text: polishedText }); onCancel() } catch (cause: any) { setError(String(cause?.message || '保存失败')) } finally { setSaving(false) }
  }
  return <div className="rounded-lg border border-teal-200 bg-teal-50/40 p-3 dark:border-teal-900 dark:bg-teal-950/20">
    <input type="datetime-local" value={occurredAt} onChange={event => setOccurredAt(event.target.value)} className="mb-2 rounded border bg-white px-2 py-1.5 text-sm dark:bg-gray-900" />
    <div className="grid gap-2"><label className="grid gap-1 text-xs text-slate-500">原文（不可修改）<textarea readOnly value={value.original_text} rows={3} className="min-h-20 resize-y rounded border bg-slate-50 p-2 text-sm text-slate-600 dark:bg-slate-900 dark:text-slate-300" /></label><label className="grid gap-1 text-xs text-slate-500">润色后的内容<textarea value={polishedText} onChange={event => setPolishedText(event.target.value)} rows={3} maxLength={4000} className="min-h-20 resize-y rounded border bg-white p-2 text-sm text-slate-900 dark:bg-gray-900 dark:text-slate-100" /></label></div>
    {error && <p className="mt-2 text-xs text-red-600">{error}</p>}<div className="mt-2 flex justify-end gap-2"><button type="button" onClick={onCancel} className="rounded border px-2 py-1 text-xs">取消</button><button type="button" disabled={saving} onClick={() => void save()} className="rounded bg-teal-700 px-3 py-1 text-xs font-semibold text-white disabled:opacity-60">{saving ? '保存中…' : '保存修订稿'}</button></div>
  </div>
}

const DiaryCard = memo(({ id, title, type, content, isLocked = false, onSave, onLockedClick }: { id?: string; title: string; type: 'morning' | 'evening'; content?: string; isLocked?: boolean; onSave: (type: 'morning' | 'evening', val: string) => void; onLockedClick?: () => void }) => {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(content || '')

  useEffect(() => {
    setVal(content || '')
  }, [content])

  const handleBlur = () => {
    setEditing(false)
    if (val !== (content || '')) {
      onSave(type, val)
    }
  }

  return (
    <div
      id={id} role={isLocked ? 'button' : undefined}
      tabIndex={isLocked ? 0 : undefined}
      onClick={isLocked ? onLockedClick : undefined}
      onKeyDown={isLocked ? event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onLockedClick?.()
        }
      } : undefined}
      className={`rounded-2xl border border-gray-100 bg-white p-4 shadow-sm ${isLocked ? 'cursor-pointer active:bg-gray-50 dark:active:bg-gray-700' : ''}`}
    >
      <div className="text-xs font-bold text-gray-400 mb-1.5 flex items-center justify-between">
        <span>{title}</span>
        {isLocked ? (
          <span className="text-gray-400 font-normal">🔒 已锁定</span>
        ) : (
          !editing && (
            <button onClick={() => setEditing(true)} className="text-blue-500 hover:underline">
              编辑
            </button>
          )
        )}
      </div>
      {editing && !isLocked ? (
        <MarkdownInput
          value={val}
          onChange={setVal}
          onBlur={handleBlur}
          onSubmit={handleBlur}
          placeholder="记录些什么... (支持 Markdown，Ctrl+Enter 保存)"
          className="w-full text-[13px] text-gray-700 outline-none border-b border-blue-400 py-1 bg-gray-50/50 min-h-[60px] resize-none"
          autoFocus
        />
      ) : (
        <p className="text-[13px] text-gray-600 leading-relaxed whitespace-pre-wrap">
          {content || (
            isLocked ? (
              <span className="text-gray-300 italic">（暂无内容，已锁定不可编辑）</span>
            ) : (
              <span className="text-gray-300 italic">写点什么吧...</span>
            )
          )}
        </p>
      )}
    </div>
  )
})

DiaryCard.displayName = 'DiaryCard'

export const TimeBookPage = memo(({
  sessions, selectedDate, setSelectedDate, todaySummary, onNavigate, syncError,
  markedDates, categories, saveSession, deleteSession, diary, saveDiary, onNavigateToSleep,
  timelineEntries, flashError, taskRecommendations, taskSubmissions, createRecommendedTask, ignoreRecommendedTask, submitFlashClassificationFeedback, loadFlashProcessingLogs, correctFlashPolish, loadFlashSkillHistory, deleteFlashCard,
}: TimeBookPageProps) => {
  const [editingSession, setEditingSession] = useState<any>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [newSession, setNewSession] = useState<SessionEditData | null>(null)
  const [timelineOrder, setTimelineOrder] = useState<'asc' | 'desc'>('desc')
  const [editingFlash, setEditingFlash] = useState<FlashCard | null>(null)
  const [deletingFlash, setDeletingFlash] = useState<FlashCard | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const exercise = useExercise(selectedDate)
  const planDay = useMemo(() => planDayForDate(selectedDate), [selectedDate])
  const confirmDelete = async () => { if (!deletingFlash) return; setDeleting(true); setDeleteError(''); try { await deleteFlashCard(deletingFlash.id); setDeletingFlash(null) } catch (cause: any) { setDeleteError(String(cause?.message || '删除闪念失败')) } finally { setDeleting(false) } }

  const totalMinutes = useMemo(() => todaySummary.reduce((sum, item) => sum + item.minutes, 0), [todaySummary])
  const displayedTimelineEntries = useMemo(
    () => timelineOrder === 'asc' ? timelineEntries : [...timelineEntries].reverse(),
    [timelineEntries, timelineOrder],
  )

  const categoryGroupSummary = useMemo(() => {
    let inputMin = 0
    let outputMin = 0
    let otherMin = 0
    sessions.forEach(s => {
      const catName = s.category_name || ''
      const min = s.net_duration_minutes || 0
      if (catName === '输入') {
        inputMin += min
      } else if (catName === '输出') {
        outputMin += min
      } else {
        otherMin += min
      }
    })
    return { inputMin, outputMin, otherMin }
  }, [sessions])

  const calendarDate = useMemo(() => {
    const [year, month, day] = selectedDate.split('-').map(Number)
    return new Date(year, month - 1, day)
  }, [selectedDate])
  const handleCalendarSelect = useCallback((d: Date) => {
    setSelectedDate(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
  }, [setSelectedDate])

  const handleStart = useCallback(() => onNavigate('timer'), [onNavigate])
  const handleLockedDiaryClick = useCallback(() => {
    window.alert('请上传睡眠截图')
    onNavigateToSleep?.(selectedDate)
  }, [onNavigateToSleep, selectedDate])

  const handleSaveSession = useCallback((data: SessionEditData) => {
    saveSession(data)
    setEditingSession(null)
    setNewSession(null)
    setShowAdd(false)
  }, [saveSession])

  const handleAddSession = useCallback(() => {
    setNewSession(newSessionDefaults(sessions, selectedDate))
    setShowAdd(true)
  }, [selectedDate, sessions])

  return (
    <div className="flex min-h-full flex-col bg-[#FAFAFA] pb-[calc(4rem+env(safe-area-inset-bottom,0px))]">
      <div className="px-6 py-4 pb-2">
        <WeekCalendar selectedDate={calendarDate} onDateSelect={handleCalendarSelect} markedDates={markedDates} />
      </div>

      {/* 晨间与晚间日记卡片 */}
      <div className="px-6 py-2 grid grid-cols-2 gap-3">
        <DiaryCard
          id="timebook-morning-diary"
          title="☀️ 晨间日记"
          type="morning"
          content={diary?.morning_diary}
          isLocked={diary ? ((diary as any).report_status !== 1 && (diary as any).report_status !== 2) : true}
          onSave={saveDiary}
          onLockedClick={handleLockedDiaryClick}
        />
        <DiaryCard
          id="timebook-evening-diary"
          title="🌙 晚间日记"
          type="evening"
          content={diary?.evening_diary}
          isLocked={diary ? ((diary as any).report_status !== 2) : true}
          onSave={saveDiary}
          onLockedClick={handleLockedDiaryClick}
        />
      </div>
      <div className="mx-6 flex gap-4 text-xs font-medium">
        {(['morning', 'evening'] as const).map(type => {
          const label = type === 'morning' ? '晨间' : '晚间', completed = diary?.[`${type}_diary_reward_status`] === 'completed'
          return <p key={type} className={completed ? 'text-emerald-700' : 'text-amber-700'}>{completed ? `${label}日记奖励 +${diary?.[`${type}_diary_reward_amount`] || 0} 金币` : `${label}日记奖励待完成：${diary?.[`${type}_diary_reward_reason`] || `${label}日记尚未完成`}`}</p>
        })}
      </div>

      {editingFlash && <section className="px-6 py-2"><FlashCardEditor value={editingFlash} onSave={correctFlashPolish} onCancel={() => setEditingFlash(null)} /></section>}
      {flashError && <p className="mx-6 mt-2 text-xs text-amber-700">{flashError}</p>}
      <ConfirmSheet open={Boolean(deletingFlash)} title="删除闪念" message="删除后无法恢复这张闪念。" confirmLabel="删除" busy={deleting} error={deleteError} onClose={() => { if (!deleting) setDeletingFlash(null) }} onConfirm={() => void confirmDelete()} />

      <div className="mx-6 mb-1 flex items-center gap-2 rounded-lg border border-gray-100 px-2 py-1.5 text-[10px] text-gray-500 dark:border-gray-700">
        <button type="button" onClick={handleAddSession} className="h-7 shrink-0 rounded-md bg-gray-100 px-2 font-semibold text-gray-600 dark:bg-gray-700 dark:text-gray-200">+ 添加</button>
        <button type="button" onClick={() => setTimelineOrder(order => order === 'asc' ? 'desc' : 'asc')} className="h-7 w-7 shrink-0 rounded-md bg-gray-100 font-semibold text-gray-600 dark:bg-gray-700 dark:text-gray-200" aria-label={timelineOrder === 'asc' ? '切换为最新在前' : '切换为最早在前'} title={timelineOrder === 'asc' ? '最早在前，切换为最新在前' : '最新在前，切换为最早在前'}>↕</button>
        <span className="min-w-0 flex-1 truncate">输入 {formatHoursMinutes(categoryGroupSummary.inputMin)} · 输出 {formatHoursMinutes(categoryGroupSummary.outputMin)} · 其他 {formatHoursMinutes(categoryGroupSummary.otherMin)}</span>
        <span className="shrink-0 font-semibold">总计 {formatHoursMinutes(totalMinutes)}</span>
      </div>
      {syncError && <div className="mx-6 text-[10px] text-amber-600">本地记录已显示 · {syncError}</div>}

      <div className="mx-3 grid min-w-0 grid-cols-[42%_minmax(0,58%)] gap-0 lg:mx-6 lg:grid-cols-[minmax(250px,320px)_minmax(0,1fr)] lg:gap-4">
        <TimeBookScheduleRail day={planDay} date={selectedDate} definition={exercise.planDefinition} states={exercise.checkins} locked={exercise.locked} onSetState={exercise.setState} />
        <div className="min-w-0">{timelineEntries.length === 0 ? (
          <EmptyState icon="📭" title="这一天还没有记录" description="开始专注后，时间会自动流进这里。" actionLabel="开始专注" onAction={handleStart} />
        ) : (
          <DualTrackTimeline entries={displayedTimelineEntries} items={taskRecommendations} taskSubmissions={taskSubmissions} onEditFlash={entry => { if (entry.kind === 'flash') setEditingFlash(entry.card) }} onDeleteFlash={entry => { if (entry.kind === 'flash') setDeletingFlash(entry.card) }} onCreateTask={createRecommendedTask} onIgnoreTask={ignoreRecommendedTask} onClassify={submitFlashClassificationFeedback} onLoadLogs={loadFlashProcessingLogs} onLoadSkillHistory={loadFlashSkillHistory} onEditSession={entry => { if (entry.kind === 'session') setEditingSession(entry.session) }} />
        )}</div>
      </div>

      {/* 编辑/添加 Sheet */}
      {(editingSession || showAdd) && (
        <SessionEditSheet
          session={editingSession ? {
            id: editingSession.id,
            start_time: editingSession.start_time,
            end_time: editingSession.end_time,
            net_duration_minutes: editingSession.net_duration_minutes,
            date: selectedDate,
            category_id: editingSession.category_id,
            session_summary: editingSession.session_summary || '',
          } : newSession || undefined}
          categories={categories}
          onSave={handleSaveSession}
          onDelete={(id) => { deleteSession(id); setEditingSession(null) }}
          onClose={() => { setEditingSession(null); setNewSession(null); setShowAdd(false) }}
        />
      )}
    </div>
  )
})

TimeBookPage.displayName = 'TimeBookPage'
