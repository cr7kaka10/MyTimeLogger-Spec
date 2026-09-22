import { useEffect, useState } from 'react'
import type { Database } from '@models/Database'
import { getDatabase } from '../../db'
import { SourceRewardSummary } from '../../components/Rewards/SourceRewardSummary'

export function HabitDetails({ id }: { id: string | number }) {
  const [details, setDetails] = useState<ReturnType<Database['getLocalHabitDetails']>>()
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    getDatabase().then(db => {
      const next = db.getLocalHabitDetails(id)
      if (active) { setDetails(next); if (!next) setError('本地习惯不存在') }
    }).catch(reason => { if (active) setError(reason?.message || '详情读取失败') })
    return () => { active = false }
  }, [id])
  if (error) return <p role="alert">{error}</p>
  if (!details) return <p>正在读取详情…</p>
  return <div className="space-y-2 text-sm">
    <p>分类：{details.category || '未分类'} · 排期：{details.habit.repeat_rule || '每天'}</p>
    <SourceRewardSummary sourceType="habit" sourceId={String(id)} />
    <h4 className="font-semibold">最近30次打卡（只读）</h4>
    {details.checkins.length ? <ul>{details.checkins.map(row => <li key={row.id}>{row.date} · {row.status === 2 ? '成功' : row.status === 1 ? '失败' : '未完成'}</li>)}</ul> : <p>暂无打卡记录</p>}
  </div>
}
