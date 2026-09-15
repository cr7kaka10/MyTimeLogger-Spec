import { weekOfYear } from '../../utils/exerciseDate'

const readablePlan = (dayName: unknown) => {
  const value = String(dayName || '').trim()
  if (!value || /^sc-\d{4}-\d{2}-\d{2}(?:-\d+)?$/i.test(value)) return '未记录训练安排'
  return /^[一二三四五六日天]$/.test(value) ? `周${value}训练` : value
}

export function ExerciseHistory({rows}:{rows:any[]}){return <><div className="ex-section">历史记录</div><div className="ex-card">{!rows.length?<div className="empty">先保存今日数据</div>:<><div className="history-row history-row-head"><span>日期</span><b>周数</b><span>训练安排</span><strong>身体指标</strong><em>完成率</em><i>评分/金币</i></div>{rows.map(x=><div className="history-row" key={x.id}><span>{x.date}</span><b>第{weekOfYear(x.date)}周</b><span>{readablePlan(x.day_name)}</span><strong>{x.weight==null?'—':`${x.weight}kg`}{x.body_fat_rate==null?'':` · ${x.body_fat_rate}%`}</strong><em>{Math.round(x.completed_items/(x.total_items||1)*100)}%</em><i>{x.settlement_score_total==null?'未结算':`${Math.round(x.settlement_score_total)}分 · ${Number(x.settlement_coin_amount||0)>0?'+':''}${Number(x.settlement_coin_amount||0)}金币`}</i></div>)}</>}</div></>}
