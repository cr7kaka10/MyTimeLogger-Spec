import type { ExercisePlanDefinition, PlanDay } from '@models/ExercisePlanSampleDataInitializer'
import type { ExerciseState } from '../../hooks/useExercise'

export function TimeBookScheduleRail({ day, date, definition, states, locked, onSetState }: {
  day: PlanDay
  date: string
  definition: ExercisePlanDefinition | null
  states: Record<string, ExerciseState>
  locked: boolean
  onSetState: (key: string, status: number, planItemId?: string, itemName?: string) => void
}) {
  if (!definition) return <aside className="p-3 text-xs text-slate-400">全天计划加载中…</aside>
  const sourceRows = day === '六' ? definition.restSchedule : day === '日'
    ? [...definition.restSchedule, definition.sundayExtra]
    : definition.weekdaySchedule
  const rows = definition.version === 'v4'
    ? sourceRows.filter(row => !/体重|体脂/.test(row.item))
    : sourceRows
  return <aside aria-label="全天计划" className="min-w-0 self-start p-2 lg:sticky lg:top-2 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:p-3">
    <div className="mb-2 flex items-center justify-between"><h3 className="truncate text-xs font-bold text-slate-700 dark:text-slate-200">⏰ 全日计划</h3><span className="text-[10px] text-slate-400">{day}</span></div>
    <div className="space-y-1.5">{rows.map((row, index) => {
      const key = `sc-${date}-${index}`, state = states[key], done = state?.status === 1, failed = state?.status === -1
      return <button key={key} type="button" disabled={locked || Boolean(state?.locked_at)} onClick={() => onSetState(key, done ? 0 : 1, undefined, row.item)} className={`grid w-full min-w-0 grid-cols-[auto_1fr_auto] items-start gap-1 rounded-lg border px-1.5 py-2 text-left text-[11px] transition lg:px-2 ${done ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : failed ? 'border-red-200 bg-red-50 text-red-700' : 'border-slate-200 bg-white text-slate-700 hover:border-blue-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200'}`}>
        <time className="whitespace-nowrap font-semibold text-blue-600">{row.time}</time><span className={`min-w-0 break-words leading-4 ${done ? 'line-through opacity-70' : ''}`}>{row.item}<small className="mt-0.5 hidden text-[10px] text-slate-400 lg:block">{row.note}</small>{(state?.completed_time || state?.locked_at) && <small className="mt-0.5 hidden text-[10px] text-slate-500 lg:block">{state?.completed_time ? `完成 ${state.completed_time}` : ''}{state?.locked_at ? ' · 已锁定' : ''}</small>}</span><span aria-label={done ? '已完成' : failed ? '未完成' : '待完成'}>{done ? '✓' : failed ? '×' : '○'}</span>
      </button>
    })}</div>
  </aside>
}
