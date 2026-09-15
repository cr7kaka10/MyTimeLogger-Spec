// ui/src/components/Timer/MicroBreakBanner.tsx
import { memo } from 'react'

interface MicroBreakBannerProps {
  remainingSeconds: number
}

export const MicroBreakBanner = memo(({ remainingSeconds }: MicroBreakBannerProps) => {
  if (remainingSeconds <= 0) return null

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-amber-900 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold">护眼休息中</div>
        <div className="font-mono text-lg font-bold tabular-nums">{remainingSeconds}s</div>
      </div>
    </div>
  )
})

MicroBreakBanner.displayName = 'MicroBreakBanner'
