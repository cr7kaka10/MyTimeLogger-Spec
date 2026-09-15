import { useEffect, useState } from 'react'
import { type ExerciseItem as Item, type ExercisePlanDefinition, type PlanDay, type Section } from '@models/ExercisePlanSampleDataInitializer'
import type { ExerciseState } from '../../hooks/useExercise'
import { getDatabase } from '../../db'
import { ExerciseItem } from './ExerciseItem'
import { exerciseItemPoints } from '../../utils/exerciseScore'

type DbItem = Item & { id: string; sort_order: number }

export function ExercisePanel({ day, date, rain, setRain, states, setState, dietCheckins, setDietState, planVersion, planDefinition, locked }: {
  day: PlanDay; date: string; rain: boolean; setRain: (x: boolean) => void
  states: Record<string, ExerciseState>
  setState: (key: string, status: number, id?: string, name?: string) => void
  dietCheckins: Record<string, any>
  setDietState: (ruleKey: string, status: 'pending' | 'completed' | 'failed') => void
  planVersion: string
  planDefinition: ExercisePlanDefinition
  locked?: boolean
}) {
  const [dbItems, setDbItems] = useState<DbItem[]>([])
  const plan = planDefinition.exercisePlan[day]
  const variant = rain ? 'rain' : 'gym'

  useEffect(() => {
    if (!plan) { setDbItems([]); return }
    void getDatabase().then(db => {
      setDbItems(db.getExercisePlanItems(day, variant, planVersion).map((row: any) => ({
        ...JSON.parse(row.tags_json || '{}'), ...row, s: row.section,
      })))
    })
  }, [day, variant, planVersion, plan])

  if (!plan) return null
  const sections: Section[] = ['无氧', '有氧', '回家后']
  const points = planVersion === 'v4'
    ? dbItems.map(item => Number((item as any).scorePoints || 0))
    : exerciseItemPoints(dbItems, planDefinition.exercisePoints)
  return <>{planVersion === 'v4' && <><div className="ex-section">饮食约束 · 15分</div><div className="ex-card">{planDefinition.diet.map(rule => {
    const key = rule.ruleKey?.trim() || '', invalid = !planDefinition.dietRulesValid || !key, fact = dietCheckins[key], status = fact?.status || 'pending', completed = status === 'completed', failed = status === 'failed'
    const overdue=failed&&fact?.failure_reason==='not_completed_before_midnight'
    return <button type="button" key={key || rule.content} aria-pressed={completed} disabled={locked || invalid} className={`diet-check-row ${completed ? 'done' : failed ? 'failed' : ''}`} onClick={() => { if (!invalid) void setDietState(key,completed||failed?'pending':'completed') }} onContextMenu={event => { if (locked||invalid) return;event.preventDefault();void setDietState(key,'failed') }}>
      <i className={`ex-box ${completed ? 'done' : failed ? 'skip' : ''}`}>{completed ? '✓' : failed ? '✗' : ''}</i><strong className={completed ? 'struck' : ''}>{rule.content}</strong><small>{invalid ? '规则配置修复中，暂不可打卡' : `${completed ? '5/5分' : '0/5分'} · ${overdue ? '已过24:00，扣20金币' : failed ? '已标记失败' : '当天24:00前必打卡'}`}</small>
    </button>
  })}</div></>}<div className="ex-section">运动计划 · 75分</div><div className="ex-plan-head">
    <strong style={{ color: plan.color, borderLeftColor: plan.color }}>{plan.label}</strong>
    {plan.rain.length > 0 && <button className={rain ? 'active' : ''} onClick={() => setRain(!rain)}>{rain ? '☔ 雨天方案' : '☀️ 健身房方案'}</button>}
  </div>{sections.filter(section => dbItems.some(item => item.s === section)).map(section => <section key={section}><div className="ex-mini">
    {section === '无氧' ? '💪' : section === '有氧' ? '🫀' : '🏠'} {section}
  </div><div className="ex-card">{dbItems.filter(item => item.s === section).map(item => {
    const key = `ex-${date}-${variant === 'rain' ? 'r' : 'g'}-${item.sort_order}`
    const state = states[key], previewMax = points[dbItems.indexOf(item)] || 0, authoritative = Boolean(state?.score_rule_version)
    const maxPoints = authoritative ? state?.max_points : previewMax
    return <ExerciseItem key={item.id} item={item} color={plan.color} state={{...state, status: state?.status || 0, earned_points: authoritative ? state?.earned_points : (state?.status === 1 ? maxPoints : 0), max_points: maxPoints}}
      onState={status => { if (!locked) setState(key, status, item.id, item.name) }} />
  })}</div></section>)}{planVersion === 'v4' && <div className="ex-card v4-guide"><strong>频率与渐进</strong>{planDefinition.progress.map(item => <p key={item.when}><b>{item.when}：</b>{item.text}</p>)}</div>}</>
}

