import { useEffect, useState } from 'react'
import { type ExerciseItem as Item, type ExercisePlanDefinition, type PlanDay } from '@models/ExercisePlanSampleDataInitializer'
import type { ExerciseState } from '../../hooks/useExercise'
import { getDatabase } from '../../db'
import { ExerciseItem } from './ExerciseItem'
import { exerciseItemPoints } from '../../utils/exerciseScore'
import { isAuthoritativeExercisePlan } from '../../utils/exerciseAuthoritativeScore'

type DbItem = Item & { id: string; sort_order: number }
const REST_DAY_DIET_EXEMPTION_FROM = '2026-10-26'

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
  const isRestDay = plan ? (planVersion === 'v5' || date >= REST_DAY_DIET_EXEMPTION_FROM) && plan.gym.length === 0 && plan.rain.length === 0 : false

  useEffect(() => {
    if (!plan) { setDbItems([]); return }
    void getDatabase().then(db => {
      setDbItems(db.getExercisePlanItems(day, variant, planVersion).map((row: any) => ({
        ...JSON.parse(row.tags_json || '{}'), ...row, s: row.section,
      })))
    })
  }, [day, variant, planVersion, plan])

  if (!plan) return null
  const sections: string[] = [...new Set(dbItems.map(item => String(item.s)).filter(Boolean))]
  const authoritativePlan = isAuthoritativeExercisePlan(planVersion)
  const latestV5 = planVersion === 'v5'
  const dietRules = planDefinition.diet
  const mealPoints: Record<string, number> = { breakfast_on_time: 11, lunch_on_time: 11, dinner_on_time: 11,
    protein_at_lunch_and_dinner: 6, vegetables_at_lunch_and_dinner: 6, controlled_staple_and_no_sugary_drink: 5,
    no_sugary_drinks: 6, no_refined_staples: 6, no_snacks: 5 }
  const pointsForDietRule = (key: string) => latestV5 ? mealPoints[key] ?? 5 : 5
  const dietMaximum = dietRules.reduce((sum, rule) => sum + pointsForDietRule(rule.ruleKey || ''), 0)
  const points = authoritativePlan
    ? dbItems.map(item => Number((item as any).scorePoints || 0))
    : exerciseItemPoints(dbItems, planDefinition.exercisePoints)
  return <>{authoritativePlan && !isRestDay && <><div className="ex-section">饮食约束 · {dietMaximum}分</div><div className="ex-card">{dietRules.map(rule => {
    const key = rule.ruleKey?.trim() || '', fact = dietCheckins[key], invalid = !planDefinition.dietRulesValid || !key || (latestV5 && !fact), status = fact?.status || 'pending', completed = status === 'completed', failed = status === 'failed'
    const maximum = pointsForDietRule(key), overdue=failed&&['not_completed_before_midnight','meal_window_passed'].includes(fact?.failure_reason)
    return <button type="button" key={key || rule.content} aria-pressed={completed} disabled={locked || invalid} className={`diet-check-row ${completed ? 'done' : failed ? 'failed' : ''}`} onClick={() => { if (!invalid) void setDietState(key,completed||failed?'pending':'completed') }} onContextMenu={event => { if (locked||invalid) return;event.preventDefault();void setDietState(key,'failed') }}>
      <i className={`ex-box ${completed ? 'done' : failed ? 'skip' : ''}`}>{completed ? '✓' : failed ? '✗' : ''}</i><strong className={completed ? 'struck' : ''}>{rule.time ? `${rule.time} ${rule.content}` : rule.content}</strong><small>{latestV5 && !fact ? `0/${maximum}分 · 该日仅展示计划` : invalid ? '规则配置修复中，暂不可打卡' : `${completed ? `${maximum}/${maximum}分` : `0/${maximum}分`} · ${overdue ? '超时失败，扣20金币' : failed ? '已标记失败' : `截止 ${rule.time === '全天' ? '24:00' : rule.time || '24:00'}`}`}</small>
    </button>
  })}</div></>}<div className="ex-section">{dbItems.length ? `运动计划 · ${latestV5 ? 50 : 75}分` : '今日休息 · 不计训练分'}</div><div className="ex-plan-head">
    <strong style={{ color: plan.color, borderLeftColor: plan.color }}>{plan.label}</strong>
    {plan.rain.length > 0 && <button className={rain ? 'active' : ''} onClick={() => setRain(!rain)}>{rain ? '☔ 雨天方案' : '☀️ 健身房方案'}</button>}
  </div>{sections.filter(section => dbItems.some(item => item.s === section)).map(section => <section key={section}><div className="ex-mini">
    {section === '力量' || section === '无氧' ? '💪' : section === '有氧' ? '🫀' : section === '热身' ? '🔥' : section === '放松' ? '🧘' : '⭐'} {section}
  </div><div className="ex-card">{dbItems.filter(item => item.s === section).map(item => {
    const key = `ex-${date}-${variant === 'rain' ? 'r' : 'g'}-${item.sort_order}`
    const state = states[key], previewMax = points[dbItems.indexOf(item)] || 0, authoritative = Boolean(state?.score_rule_version)
    const maxPoints = authoritative ? state?.max_points : previewMax
    return <ExerciseItem key={item.id} item={item} color={plan.color} state={{...state, status: state?.status || 0, earned_points: authoritative ? state?.earned_points : (state?.status === 1 ? maxPoints : 0), max_points: maxPoints}}
      onState={status => { if (!locked) setState(key, status, item.id, item.name) }} />
  })}</div></section>)}{authoritativePlan && <div className="ex-card v4-guide"><strong>频率与渐进</strong>{planDefinition.progress.map(item => <p key={item.when}><b>{item.when}：</b>{item.text}</p>)}</div>}</>
}

