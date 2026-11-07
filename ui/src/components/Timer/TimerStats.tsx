// ui/src/components/Timer/TimerStats.tsx
import { memo, useMemo } from 'react'

interface TimerStatsProps {
  totalTodayMinutes: number
  compactSyncText?: string
  homeSlogan: string
}

const formatMinutes = (minutes: number): string => {
  const hours = Math.floor(minutes / 60)
  const rest = Math.floor(minutes % 60)
  return `${hours}h ${rest}m`
}

export const TimerStats = memo(({ totalTodayMinutes, compactSyncText, homeSlogan }: TimerStatsProps) => {
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
      <div className="flex min-w-0 flex-col gap-2 md:flex-row md:items-start md:gap-4">
        <div className="flex min-w-0 items-start gap-3 md:contents">
          <div className="shrink-0 font-mono text-3xl font-bold text-gray-900 dark:text-gray-100">{total}</div>
          <div className="min-w-0 flex-1 text-right md:contents">
            <div className="text-sm text-gray-400 dark:text-gray-300 md:order-2 md:shrink-0 md:whitespace-nowrap">{todayStr}</div>
            {compactSyncText ? <div data-testid="compact-sync-status" className="min-w-0 break-words text-xs text-slate-500 dark:text-slate-400 md:order-4 md:ml-auto md:shrink-0 md:whitespace-nowrap" aria-live="polite">{compactSyncText}</div> : null}
          </div>
        </div>
        {homeSlogan ? <div data-testid="home-slogan" className="min-w-0 whitespace-pre-wrap break-words text-sm text-gray-700 [overflow-wrap:anywhere] dark:text-gray-200 md:order-3 md:flex-1 md:text-center">{homeSlogan}</div> : null}
      </div>
    </header>
  )
})

TimerStats.displayName = 'TimerStats'
