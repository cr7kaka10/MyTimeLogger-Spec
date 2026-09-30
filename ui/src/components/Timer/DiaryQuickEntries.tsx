import { memo, useState } from 'react'
import { BottomSheet } from '../common/BottomSheet'
import { continueDiaryNumbering, diaryInitialValue } from '../Sleep/SleepPage'

export type DiaryType = 'morning' | 'evening'
export type HomeDiary = { morning_diary?: string; evening_diary?: string; report_status?: number; morning_diary_reward_status?: string; morning_diary_reward_amount?: number; evening_diary_reward_status?: string; evening_diary_reward_amount?: number }
type Props = { diary: HomeDiary | null; onSave: (type: DiaryType, value: string) => void; onLockedClick: () => void }

const ITEMS = [
  { type: 'morning', icon: '☀️', title: '晨间日记' },
  { type: 'evening', icon: '🌙', title: '晚间日记' },
] as const

export const DiaryQuickEntries = memo(({ diary, onSave, onLockedClick }: Props) => {
  const reportStatus = Number(diary?.report_status || 0)
  const [editing, setEditing] = useState<DiaryType | null>(null)
  const [draft, setDraft] = useState('')
  const open = (type: DiaryType, locked: boolean, content: string) => {
    if (locked) { onLockedClick(); return }
    setDraft(diaryInitialValue(type === 'morning' ? '晨间日记' : '晚间日记', content)); setEditing(type)
  }
  const save = () => {
    if (!editing) return
    if (draft !== (diary?.[`${editing}_diary`] || '')) onSave(editing, draft)
    setEditing(null)
  }
  return (
    <><section data-testid="timer-diary-entries" aria-label="今日日记" className="mx-auto grid w-full max-w-2xl grid-cols-2 gap-2 sm:gap-3">
      {(['morning', 'evening'] as const).map(type => {
        const item = ITEMS.find(candidate => candidate.type === type)!
        const content = diary?.[`${type}_diary`]?.trim() || ''
        const locked = type === 'morning' ? reportStatus < 1 : reportStatus < 2
        const completed = diary?.[`${type}_diary_reward_status`] === 'completed'
        const amount = diary?.[`${type}_diary_reward_amount`] || 0
        return <button key={type} type="button" onClick={() => open(type, locked, content)}
          aria-label={`${item.title}${locked ? '，已锁定' : '，打开编辑'}`}
          className="min-h-11 min-w-0 rounded-2xl border border-slate-200/90 bg-white p-3 text-left shadow-[0_4px_14px_rgba(15,23,42,0.06)] transition active:scale-[0.99] dark:border-slate-700 dark:bg-slate-900 dark:shadow-none">
          <span className="flex items-center justify-between gap-1 text-sm font-semibold text-slate-800 dark:text-slate-100"><span>{item.icon} {item.title}</span><span className={`shrink-0 text-[10px] ${locked ? 'text-slate-400' : completed ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>{locked ? '🔒 已锁定' : completed ? `+${amount} 金币` : '待填写'}</span></span>
          <span className="mt-1 block min-w-0 overflow-hidden text-xs leading-5 text-slate-500 [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2] [overflow-wrap:anywhere] dark:text-slate-400">{content || (locked ? '完成睡眠分析后解锁' : '点击写下此刻的记录')}</span>
        </button>
      })}
    </section><BottomSheet open={Boolean(editing)} onClose={() => setEditing(null)} ariaLabel={editing === 'morning' ? '编辑晨间日记' : '编辑晚间日记'} panelClass="space-y-3 p-4">
      <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{editing === 'morning' ? '☀️ 晨间日记' : '🌙 晚间日记'}</h3>
      <textarea value={draft} onChange={event => setDraft(event.target.value)} autoFocus rows={10} className="w-full resize-none rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm leading-6 text-slate-800 outline-none focus:border-blue-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" onKeyDown={event => {
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); save(); return }
        if (event.key !== 'Enter' || event.shiftKey || event.altKey) return
        const target = event.currentTarget; const next = continueDiaryNumbering(draft, target.selectionStart, target.selectionEnd)
        if (!next) return; event.preventDefault(); setDraft(next.value); window.setTimeout(() => target.setSelectionRange(next.cursor, next.cursor), 0)
      }} />
      <div className="flex gap-2"><button type="button" onClick={() => setEditing(null)} className="h-11 flex-1 rounded-xl bg-slate-100 text-sm font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">取消</button><button type="button" onClick={save} className="h-11 flex-1 rounded-xl bg-blue-600 text-sm font-semibold text-white">保存</button></div>
    </BottomSheet></>
  )
})

DiaryQuickEntries.displayName = 'DiaryQuickEntries'
