// ui/src/components/Timer/TimerStats.tsx
import { memo, useMemo } from 'react'

interface TimerStatsProps {
  totalTodayMinutes: number
  compactSyncText?: string
}

const formatMinutes = (minutes: number): string => {
  const hours = Math.floor(minutes / 60)
  const rest = Math.floor(minutes % 60)
  return `${hours}h ${rest}m`
}

export const TimerStats = memo(({ totalTodayMinutes, compactSyncText }: TimerStatsProps) => {
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
    <header className="shrink-0">
      <div className="flex min-w-0 flex-col gap-2 md:flex-row md:items-baseline md:gap-4 md:whitespace-nowrap">
        <div className="font-mono text-3xl font-bold text-gray-900">{total}</div>
        <div className="text-sm text-gray-400">{todayStr}</div>
        {compactSyncText ? <div data-testid="compact-sync-status" className="text-xs text-slate-500 md:ml-auto md:whitespace-nowrap" aria-live="polite">{compactSyncText}</div> : null}
      </div>
    </header>
  )
})

TimerStats.displayName = 'TimerStats'
