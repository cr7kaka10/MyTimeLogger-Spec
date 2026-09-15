// ui/src/components/common/ProgressBar.tsx
import { memo, useMemo } from 'react'

interface ProgressBarProps {
  percent: number
  color: string
}

export const ProgressBar = memo(({ percent, color }: ProgressBarProps) => {
  const width = useMemo(() => `${Math.min(100, Math.max(0, percent))}%`, [percent])

  return (
    <div className="h-2 overflow-hidden rounded-full bg-gray-200">
      <div className="h-2 rounded-full" style={{ width, backgroundColor: color }} />
    </div>
  )
})

ProgressBar.displayName = 'ProgressBar'
