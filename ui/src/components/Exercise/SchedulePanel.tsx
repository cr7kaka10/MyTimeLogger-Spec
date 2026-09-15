import { type ExercisePlanDefinition, type PlanDay } from '@models/ExercisePlanSampleDataInitializer'
import { exerciseStatusPresentation } from '@core/ExerciseStatus'
import { statusControlClass } from '@core/StatusControl'
import type { ExerciseState } from '../../hooks/useExercise'
import { PressableCheckRow } from './PressableCheckRow'
import { formatScore, scheduleItemScore } from '../../utils/exerciseScore'

const colors: any = { diet: '#e8a63a', study: '#3ab85a', sleep: '#3a7ee8', stretch: '#2dd4bf', default: '#76748a' }

export function SchedulePanel({ day, date, states, setState, planDefinition, locked }: {
  day: PlanDay
  date: string
  states: Record<string, ExerciseState>
  setState: (key: string, status: number, planItemId?: string, itemName?: string) => void
  planDefinition: ExercisePlanDefinition
  locked?: boolean
}) {
  const rows = day === '六' ? planDefinition.restSchedule : day === '日' ? [...planDefinition.restSchedule, planDefinition.sundayExtra] : planDefinition.weekdaySchedule
  return <><div className="ex-card ex-schedule">{rows.map((r, i) => {
    const k = `sc-${date}-${i}`, st = states[k], done = st?.status === 1, skip = st?.status === -1, deadlineLocked = Boolean(st?.locked_at), c = colors[r.accent], p = exerciseStatusPresentation(st?.status), control = done ? 'success' : skip ? 'failure' : 'idle'
    const preview = scheduleItemScore(day, date, i, st, planDefinition), authoritative = locked ? Boolean(st?.score_rule_version) : st?.score_rule_version === 'v2'
    const earned = authoritative ? Number(st?.earned_points || 0) : locked ? 0 : preview.earned, max = authoritative ? Number(st?.max_points || 0) : locked ? 0 : preview.max
    return <PressableCheckRow key={k} disabled={deadlineLocked} className={`${done ? 'done' : ''} ${skip ? 'skip' : ''} ${deadlineLocked ? 'deadline-locked' : ''}`} onTap={() => setState(k, done ? 0 : 1, undefined, r.item)} onLong={() => setState(k, skip ? 0 : -1, undefined, r.item)}>
      <div className="ex-time" style={{ color: c }}>{r.time}</div>
      <div className="ex-row-main"><div className={done ? 'struck' : ''}>{r.item}</div>{r.note && <small>{r.note}</small>}{max > 0 && <span className="ex-score-meta"><em>{formatScore(done ? earned : 0)}/{formatScore(max)} 分</em>{done && st.completed_time && <em>✓ 打卡 {st.completed_time}</em>}</span>}{deadlineLocked ? <b>✗ 已超时锁定</b> : skip && <b>✗ 已标记跳过（右键或长按可取消）</b>}</div>
      <i aria-label={p.label} className={`ex-box ${statusControlClass(control)}`}>{p.mark}</i>
    </PressableCheckRow>
  })}</div><div className="ex-hint">💡 轻点完成；电脑版右键、手机端长按标记跳过（✗）</div></>
}
