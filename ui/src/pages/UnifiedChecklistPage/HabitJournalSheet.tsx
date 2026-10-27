import { useEffect, useState } from 'react'
import { BottomSheet } from '../../components/common/BottomSheet'
import { getCurrentTimerClient, syncNow } from '../../db'

interface Props { habitId: string; name: string; date: string; initialNote?: string; onClose: () => void; onSaved?: () => void }
const moods = ['😭', '☹️', '😐', '🙂', '🥰']

export function HabitJournalSheet({ habitId, name, date, initialNote = '', onClose, onSaved }: Props) {
  const [note, setNote] = useState(initialNote)
  const [mood, setMood] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const previousMood = moods.find(item => initialNote.startsWith(item)) || ''
    setMood(previousMood); setNote(previousMood ? initialNote.slice(previousMood.length).trimStart() : initialNote); setError('')
  }, [habitId, date, initialNote])
  const save = async () => {
    if (busy) return
    const api = getCurrentTimerClient()
    if (!api) { setError('尚未连接服务器，请稍后重试'); return }
    setBusy(true); setError('')
    try {
      const content = `${mood}${mood && note.trim() ? ' ' : ''}${note.trim()}`
      const response = await api.saveHabitJournal(habitId, date, content)
      if (!response.ok) throw new Error(response.error || '日志保存失败')
      const result = await syncNow({ reason: 'habit-journal' })
      if (!result.ok) throw new Error('日志已保存到服务器，本机同步失败，请重试')
      onSaved?.(); onClose()
    } catch (reason) { setError(reason instanceof Error ? reason.message : '日志保存失败') }
    finally { setBusy(false) }
  }
  return <BottomSheet open ariaLabel={`习惯日志 ${name}`} onClose={() => { if (!busy) onClose() }} panelClass="p-5 sm:mb-6 sm:max-w-xl sm:rounded-3xl">
    <div className="space-y-4 text-gray-900 dark:text-gray-100">
      <header className="flex items-start justify-between"><div><h2 className="text-lg font-bold">{name}</h2><p className="text-sm text-gray-500">{date} · 打卡日志</p></div><button type="button" disabled={busy} aria-label="关闭日志" onClick={onClose}>×</button></header>
      <div className="flex justify-between gap-1" aria-label="选择心情">{moods.map(item => <button key={item} type="button" aria-label={`心情 ${item}`} aria-pressed={mood === item} onClick={() => setMood(mood === item ? '' : item)} className={`rounded-xl px-2 py-1 text-2xl ${mood === item ? 'bg-blue-100 dark:bg-blue-900' : 'hover:bg-gray-100 dark:hover:bg-gray-800'}`}>{item}</button>)}</div>
      <textarea value={note} maxLength={1990} onChange={event => setNote(event.target.value)} placeholder="打卡成功！记录一下心得吧" aria-label="打卡日志内容" className="min-h-28 w-full rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm dark:border-gray-700 dark:bg-gray-800" />
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <div className="flex justify-end gap-2"><button type="button" disabled={busy} onClick={onClose} className="rounded-xl border px-4 py-2 text-sm dark:border-gray-700">跳过</button><button type="button" disabled={busy} onClick={() => void save()} className="theme-accent-button rounded-xl px-5 py-2 text-sm disabled:opacity-50">{busy ? '保存中…' : '保存'}</button></div>
    </div>
  </BottomSheet>
}
