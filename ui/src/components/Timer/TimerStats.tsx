// ui/src/components/Timer/TimerStats.tsx
import { memo, useMemo } from 'react'

interface TimerStatsProps {
  totalTodayMinutes: number
}

const formatMinutes = (minutes: number): string => {
  const hours = Math.floor(minutes / 60)
  const rest = Math.floor(minutes % 60)
  return `${hours}h ${rest}m`
}

export const TimerStats = memo(({ totalTodayMinutes }: TimerStatsProps) => {
  const total = useMemo(() => formatMinutes(totalTodayMinutes), [totalTodayMinutes])

  const todayStr = useMemo(() => {
    const d = new Date()
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const weekday = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'][d.getDay()]
    return `${year}-${month}-${day} · ${weekday}`
  }, [])

  return (
    <header>
      <div>
        <div className="font-mono text-3xl font-bold text-gray-900">{total}</div>
        <div className="mt-2 text-sm text-gray-400">{todayStr}</div>
      </div>
    </header>
  )
})

TimerStats.displayName = 'TimerStats'
