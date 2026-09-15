// ui/src/components/Timer/TimerCircle.tsx
import { memo, useMemo } from 'react'
import type { TimerState } from '../../types'
import { elapsedWholeSeconds } from '@core/displayFormat'

interface TimerCircleProps {
  state: TimerState
  elapsedMs: number
  remainingMs: number
  totalMs: number
  color?: string
}

const formatMs = (ms: number): string => {
  const seconds = elapsedWholeSeconds(ms)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  if (hours > 0) return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

export const TimerCircle = memo(({ state, elapsedMs, remainingMs, totalMs, color = '#2563EB' }: TimerCircleProps) => {
  const isCountup = state === 'countup_studying'
  const isStopped = state === 'stopped'
  const isFinished = state === 'long_break_finished'
  const value = useMemo(() => (isCountup ? formatMs(elapsedMs) : formatMs(remainingMs)), [elapsedMs, isCountup, remainingMs])
  const circumference = useMemo(() => 2 * Math.PI * 120, [])
  const percent = useMemo(() => {
    if (!totalMs) return 0
    return Math.min(1, Math.max(0, 1 - remainingMs / totalMs))
  }, [remainingMs, totalMs])
  const offset = useMemo(() => circumference * (1 - percent), [circumference, percent])

  if (isFinished) {
    return (
      <div className="flex min-h-64 flex-col items-center justify-center text-center">
        <div className="text-5xl font-bold text-blue-600">✓</div>
        <div className="mt-4 text-xl font-semibold text-gray-900">休息完成</div>
      </div>
    )
  }

  if (isCountup || isStopped) {
    return (
      <div className="flex min-h-64 items-center justify-center">
        <div className={`font-mono text-5xl font-bold ${isStopped ? 'text-gray-300' : 'text-gray-900'}`}>{isStopped ? '00:00' : value}</div>
      </div>
    )
  }

  return (
    <div className="flex min-h-64 items-center justify-center">
      <div className="relative h-64 w-64">
        <svg viewBox="0 0 280 280" className="h-64 w-64 -rotate-90">
          <circle cx="140" cy="140" r="120" stroke="currentColor" strokeWidth="8" fill="none" className="text-gray-100" />
          <circle
            cx="140"
            cy="140"
            r="120"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            fill="none"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center font-mono text-5xl font-bold text-gray-900">{value}</div>
      </div>
    </div>
  )
})

TimerCircle.displayName = 'TimerCircle'
