// ui/src/components/Timer/CurrentTimerHeader.tsx
import { memo, useMemo } from 'react'
import type { TimerState, Category } from '../../types'
import { CategoryIcon } from '../common/CategoryIcon'

interface CurrentTimerHeaderProps {
  state: TimerState
  elapsedMs: number
  remainingMs: number
  currentCategory: Category | null
  currentNote: string
  isPaused: boolean
  onEditNote: () => void
  onTogglePause: () => void
  onStop: () => void
  commandsEnabled?: boolean
}

// 格式化计时时长为 MM:SS 或 HH:MM:SS
const formatTimerDuration = (milliseconds: number, forceMinutes = false): string => {
  const totalSeconds = Math.floor(milliseconds / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = forceMinutes ? Math.floor(totalSeconds / 60) : Math.floor((totalSeconds % 3600) / 60)
  const seconds = Math.floor(totalSeconds % 60)

  if (!forceMinutes && hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

// 获取状态标签文本
const getStateLabel = (state: TimerState, isPaused: boolean): string => {
  if (isPaused) return '暂停中'
  switch (state) {
    case 'studying':
      return '专注中'
    case 'countup_studying':
      return '正计时中'
    case 'short_breaking':
      return '短休息中'
    case 'long_breaking':
      return '休息中'
    case 'long_break_finished':
      return '专注完成'
    default:
      return ''
  }
}

export const CurrentTimerHeader = memo(({
  state,
  elapsedMs,
  remainingMs,
  currentCategory,
  currentNote,
  isPaused,
  onEditNote,
  onTogglePause,
  onStop,
  commandsEnabled = true,
}: CurrentTimerHeaderProps) => {
  // 根据状态决定显示的时长（学习模式显示剩余，正计时显示已用）
  const displayMs = useMemo(() => {
    if (state === 'countup_studying') {
      return elapsedMs
    }
    // studying, short_breaking, long_breaking 显示剩余时间
    return remainingMs
  }, [state, elapsedMs, remainingMs])

  const showElapsedCompanion = currentCategory ? ['输入', '输出'].includes(currentCategory.name) && state === 'studying' : false
  const formattedTime = useMemo(() => formatTimerDuration(displayMs, showElapsedCompanion), [displayMs, showElapsedCompanion])
  const elapsedTime = useMemo(() => formatTimerDuration(elapsedMs), [elapsedMs])
  const stateLabel = useMemo(() => getStateLabel(state, isPaused), [state, isPaused])

  return (
    <div className="px-0 py-1">
      <div className="flex min-h-12 items-center gap-3">
        <button
          type="button"
          onClick={onEditNote}
          disabled={!commandsEnabled}
          aria-label="编辑计时备注"
          className="min-w-0 flex-1 rounded-lg py-1 text-left transition-colors hover:bg-gray-50 active:bg-gray-100"
        >
          <div className="relative min-w-0">
            <div className="flex min-h-8 min-w-0 items-center gap-2">
              <CategoryIcon icon={currentCategory?.icon} color={currentCategory?.color} className="h-8 w-8 shrink-0" />
              <span className="max-w-24 truncate text-sm font-semibold text-gray-900">{currentCategory?.name || '未知分类'}</span>
              <span className="shrink-0 font-mono text-2xl font-bold text-gray-900">{formattedTime}</span>
              {showElapsedCompanion ? (
                <span className="ml-2 shrink-0 font-mono text-xs font-semibold text-gray-400">{elapsedTime}</span>
              ) : null}
              <span className="ml-2 inline-flex shrink-0 items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                {stateLabel}
              </span>
            </div>
              {currentNote ? (
                <span className="absolute left-0 top-7 block w-full max-w-[calc(100vw-8rem)] truncate text-xs font-normal leading-4 text-gray-500">
                  {currentNote}
                </span>
              ) : null}
          </div>
        </button>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
          onClick={onStop}
            disabled={!commandsEnabled}
            aria-disabled={!commandsEnabled}
            aria-label="停止"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-red-500 text-white shadow-md transition-all hover:bg-red-600 active:scale-95"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <rect x="7" y="7" width="10" height="10" rx="1" fill="currentColor" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
})

CurrentTimerHeader.displayName = 'CurrentTimerHeader'
