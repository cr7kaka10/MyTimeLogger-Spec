import { memo, useEffect, useMemo, useState } from 'react'
import {
  type ExercisePlanDefinition,
  type PlanDay,
} from '@models/ExercisePlanSampleDataInitializer'
import { useExercise } from '../hooks/useExercise'
import { beijingDateHour, dateForTab, todayTab, weekOfYear } from '../utils/exerciseDate'
import { calcScore, formatScore } from '../utils/exerciseScore'
import { projectV4Score } from '../utils/exerciseV4Score'
import { ExercisePanel } from '../components/Exercise/ExercisePanel'
import { ExerciseHistory } from '../components/Exercise/ExerciseHistory'
import { requestCapacitorInputFocus } from '../platform/keyboard'
import './ExercisePage.css'

const DAYS: PlanDay[] = ['周一','周二','周三','周四','周五','六','日']
const EMPTY_PLAN_DEFINITION: ExercisePlanDefinition = {
  version: '',
  title: '',
  sourceName: '',
  diet: [],
  weekdaySchedule: [],
  restSchedule: [],
  sundayExtra: { time: '', item: '', note: '', accent: 'default' },
  exercisePlan: {
    周一: { label: '周一', color: '#8b5cf6', gym: [], rain: [] },
    周二: { label: '周二', color: '#8b5cf6', gym: [], rain: [] },
    周三: { label: '周三', color: '#8b5cf6', gym: [], rain: [] },
    周四: { label: '周四', color: '#8b5cf6', gym: [], rain: [] },
    周五: { label: '周五', color: '#8b5cf6', gym: [], rain: [] },
    六: { label: '六', color: '#2dd4bf', gym: [], rain: [] },
    日: { label: '日', color: '#76748a', gym: [], rain: [] },
  },
  progress: [],
  weekdayScore: [],
  saturdayScore: [],
  sundayScore: [],
  categoryOrder: [],
  exercisePoints: 0,
}

interface Props {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  onStartFocus?: (title: string) => Promise<boolean>
}

export const ExercisePage = memo(({ theme, onToggleTheme, onStartFocus }: Props) => {
  const [day, setDay] = useState<PlanDay>(() => todayTab())
  const [rain, setRain] = useState(false)
  const [weight, setWeight] = useState('')
  const [bodyFatRate, setBodyFatRate] = useState('')
  const [showVersions, setShowVersions] = useState(false)
  const [beijingNow, setBeijingNow] = useState(() => beijingDateHour())
  const date = dateForTab(day)
  const x = useExercise(date)
  const def = x.planDefinition || EMPTY_PLAN_DEFINITION
  const score = useMemo(() => calcScore(day, date, rain, x.checkins, def), [day, date, rain, x.checkins, def])
  const plan = def.exercisePlan[day]
  const sched = day === '六' ? def.restSchedule : day === '日' ? [...def.restSchedule, def.sundayExtra] : def.weekdaySchedule
  const total = sched.length + (plan ? plan[rain ? 'rain' : 'gym'].length : 0)
  const done = Object.entries(x.checkins).filter(([k, v]) =>
    (k.startsWith(`sc-${date}-`) || k.startsWith(`ex-${date}-${rain ? 'r' : 'g'}-`)) && v.status === 1,
  ).length
  const log = x.log
  const dateLabel = date.split('-')
  const isPastDate = date < dateForTab(todayTab())
  const isBeijingToday = date === beijingNow.date
  useEffect(() => { setRain(x.log?.exercise_variant === 'rain') }, [date, x.log?.exercise_variant])
  const isWeightWindow = isBeijingToday && beijingNow.hour >= 6 && beijingNow.hour < 9
  const isWeightOverdue = isBeijingToday && beijingNow.hour >= 9
  const bodyDeadlineFact = x.deadlineFacts.find((fact: any) => fact.fact_type === 'body_metrics')
  const isBodyMetricLocked = bodyDeadlineFact?.status === 'failed'
  const canEditWeight = isBeijingToday && !x.locked
  const weightFact = x.deadlineFacts.find((fact: any) => fact.fact_type === 'body_weight')
  const bodyFatFact = x.deadlineFacts.find((fact: any) => fact.fact_type === 'body_fat_rate')
  const weightScore = x.planVersion === 'v4' ? Number(x.itemScores['body:weight']?.earned_points || 0) : log?.weight == null ? 0 : 5
  const bodyFatScore = x.planVersion === 'v4' ? Number(x.itemScores['body:body_fat_rate']?.earned_points || 0) : log?.body_fat_rate == null ? 0 : 5
  const metricStatus = (value: unknown, fact: any, scoreValue: number) => value == null ? '尚未保存' : fact?.status === 'failed' ? '已补录，截止后不得分' : scoreValue ? '✓ 已得分' : '已保存，等待服务端确认'
  const savedScore = useMemo(() => {
    if (!log?.score_snapshot) return null
    try {
      return typeof log.score_snapshot === 'string' ? JSON.parse(log.score_snapshot) : log.score_snapshot
    } catch {
      return null
    }
  }, [log?.score_snapshot])
  const authoritativeV4Score = useMemo(() => {
    if (x.planVersion !== 'v4' || !x.settlement?.score_snapshot) return null
    try { return typeof x.settlement.score_snapshot === 'string' ? JSON.parse(x.settlement.score_snapshot) : x.settlement.score_snapshot } catch { return null }
  }, [x.planVersion, x.settlement?.score_snapshot])
  const displayScore = x.planVersion === 'v4' ? projectV4Score(authoritativeV4Score) : (isPastDate && savedScore ? savedScore : score)
  const displayScoreCategories = useMemo(() => {
    const cats = displayScore.cats || {}
    const ordered = (def.categoryOrder || []).filter(c => cats[c])
    return [...ordered, ...Object.keys(cats).filter(c => !ordered.includes(c))]
  }, [def.categoryOrder, displayScore])

  useEffect(() => {
    setWeight(log?.weight == null ? '' : String(log.weight))
    setBodyFatRate(log?.body_fat_rate == null ? '' : String(log.body_fat_rate))
  }, [date, log?.weight, log?.body_fat_rate])

  useEffect(() => {
    const timer = window.setInterval(() => setBeijingNow(beijingDateHour()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const switchDay = (nextDay: PlanDay) => {
    setDay(nextDay)
    setRain(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const saveWeightAndDay = () => {
    const trimmedWeight = weight.trim()
    const numericWeight = trimmedWeight ? Number(trimmedWeight) : undefined
    if (numericWeight !== undefined && (!Number.isFinite(numericWeight) || numericWeight < 30 || numericWeight > 200)) {
      alert('请输入 30-200 公斤之间的有效体重。')
      return
    }
    const trimmedBodyFat = bodyFatRate.trim()
    const numericBodyFat = trimmedBodyFat ? Number(trimmedBodyFat) : undefined
    if (numericBodyFat !== undefined && (!Number.isFinite(numericBodyFat) || numericBodyFat < 3 || numericBodyFat > 75)) {
      alert('请输入 3-75% 之间的有效体脂率。')
      return
    }
    x.saveDay(numericWeight, day, done, total, x.planVersion === 'v4' ? undefined : score, rain ? 'rain' : 'gym', numericBodyFat)
  }

  return (
    <div className="exercise-page" data-theme={theme}>
      <header className="ex-header">
        <div className="ex-header-top">
          <button type="button" className="plan-title" onClick={() => setShowVersions(value => !value)}>
            每日打卡表
            <small>{x.planVersion}</small>
          </button>
          <div>{dateLabel[0]}年{Number(dateLabel[1])}月{Number(dateLabel[2])}日</div>
          <div>第{weekOfYear(date)}周<small>{dateLabel[0]}年</small></div>
        </div>
        {showVersions ? (
          <div className="plan-version-menu">
            {x.planVersions.map((version: any) => (
              <button
                key={version.version}
                type="button"
                className={version.version === x.planVersion ? 'active' : ''}
                onClick={async () => {
                  if (await x.setActivePlanVersion(version.version)) setShowVersions(false)
                }}
              >
                {version.title || '每日打卡表'}
                <small>{version.version}</small>
              </button>
            ))}
            {x.versionError && <p className="sync-warning">{x.versionError}</p>}
          </div>
        ) : null}
        <div className="ex-day-row">
          {DAYS.slice(0, 3).map(d => (
            <button
              key={d}
              className={day === d ? 'active' : ''}
              style={day === d ? {
                borderColor: d === '六' || d === '日' ? '#a3a1b0' : def.exercisePlan[d].color,
                color: d === '六' || d === '日' ? '#a3a1b0' : def.exercisePlan[d].color,
              } : {}}
              onClick={() => switchDay(d)}
            >
              {d}{d !== '六' && d !== '日' && <small>{def.exercisePlan[d].label}</small>}
            </button>
          ))}
          <button className="theme-btn" onClick={onToggleTheme}>{theme === 'dark' ? '☀️' : '🌙'}</button>
        </div>
        <div className="ex-day-row">
          {DAYS.slice(3).map(d => (
            <button key={d} className={day === d ? 'active' : ''} onClick={() => switchDay(d)}>
              {d}{d !== '六' && d !== '日' && <small>{def.exercisePlan[d].label}</small>}
            </button>
          ))}
          <button onClick={() => switchDay(todayTab())}>今</button>
        </div>
      </header>
      {!x.planDefinition ? (
        <main>
          <section className="record-card">
            <label>运动计划加载中</label>
            <p>正在从数据库读取运动计划定义。</p>
          </section>
        </main>
      ) : <main>
        <section className="record-card">
          <label>{x.locked ? '历史评分已固定' : '今日数据记录'}</label>
          <div className="body-metrics">
            <label className="body-metric"><span>体重</span><span className="body-metric-input"><input
              type="number" inputMode="decimal" min="30" max="200" step=".1" placeholder="体重" value={weight}
              disabled={!canEditWeight} title="当天全天可录入；北京时间 06:00-09:00 计为按时称重" onPointerDown={event => requestCapacitorInputFocus(event.currentTarget)} onChange={event => setWeight(event.target.value)}
            /><em>公斤</em></span><span className="body-metric-meta"><span>{weightScore}/5 分</span><span>{metricStatus(log?.weight, weightFact, weightScore)}</span></span></label>
            <label className="body-metric"><span>体脂率</span><span className="body-metric-input"><input
              type="number" inputMode="decimal" min="3" max="75" step=".1" placeholder="体脂率" value={bodyFatRate}
              disabled={!canEditWeight} title="请输入 3-75% 之间的体脂率" onPointerDown={event => requestCapacitorInputFocus(event.currentTarget)} onChange={event => setBodyFatRate(event.target.value)}
            /><em>%</em></span><span className="body-metric-meta"><span>{bodyFatScore}/5 分</span><span>{metricStatus(log?.body_fat_rate, bodyFatFact, bodyFatScore)}</span></span></label>
            <button disabled={!canEditWeight} onClick={saveWeightAndDay}>保存</button>
          </div>
          {!isWeightWindow && isBeijingToday && (isBodyMetricLocked || log?.weight == null) && (
            <p>{isBodyMetricLocked ? '已超过北京时间 09:00，可补录体重和体脂率；-50 金币处罚不变。' : isWeightOverdue ? '已超过北京时间 09:00，正在等待服务端确认截止结果。' : '当前可记录体重；北京时间 06:00-09:00 计为按时称重。'}</p>
          )}
          {x.syncError && <p className="sync-warning">打卡已保存，等待同步：{x.syncError}</p>}
          {log && <p>✓ {log.weight == null ? '体重未填' : `${log.weight}公斤`} · {log.body_fat_rate == null ? '体脂率未填' : `${log.body_fat_rate}%`} | 打卡{log.completed_items}/{log.total_items}项({Math.round(log.completed_items / (log.total_items || 1) * 100)}%) | {log.date}</p>}
        </section>
        <section className="score-card">
          <label>今日评分</label>
          <div className="score-body">
            <div className="score-ring" style={{ background: `conic-gradient(${displayScore.total >= 85 ? '#3ab85a' : displayScore.total >= 65 ? '#e8a63a' : displayScore.total >= 45 ? '#e8523a' : '#a3a1b0'} ${displayScore.total * 3.6}deg,var(--border) 0)` }}>
              <span><b>{formatScore(displayScore.total)}</b><small>/ 100分</small></span>
            </div>
            <div className="score-cats">
              {displayScoreCategories.map(c => {
                const v = displayScore.cats[c]
                return <div key={c}><span>{c}</span><i><b style={{ width: `${Math.round(v.s / v.m * 100)}%` }} /></i><em>{formatScore(v.s)}/{formatScore(v.m)}</em></div>
              })}
            </div>
          </div>
        </section>
        <ExercisePanel day={day} date={date} rain={rain} setRain={next => { setRain(next); void x.setVariant(next ? 'rain' : 'gym') }} states={x.checkins} setState={x.setState} dietCheckins={x.dietCheckins} setDietState={x.setDietState} planVersion={x.planVersion} planDefinition={def} locked={x.locked} />
        <ExerciseHistory rows={x.history} />
      </main>}
    </div>
  )
})
