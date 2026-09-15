// ui/src/components/Timer/StateLabel.tsx
import { memo, useMemo } from 'react'
import type { Category, TimerState } from '../../types'

interface StateLabelProps {
  state: TimerState
  cycleCount: number
  currentCategory: Category | null
}

const labelMap: Record<TimerState, { text: string; className: string }> = {
  stopped: { text: '准备就绪', className: 'text-gray-400' },
  studying: { text: '学习中', className: 'text-blue-600' },
  countup_studying: { text: '正计时中', className: 'text-blue-600' },
  short_breaking: { text: '短休息', className: 'text-orange-500' },
  long_breaking: { text: '长休息', className: 'text-purple-500' },
  long_break_finished: { text: '休息完成', className: 'text-green-600' },
}

export const StateLabel = memo(({ state, cycleCount, currentCategory }: StateLabelProps) => {
  const label = useMemo(() => labelMap[state], [state])
  const text = useMemo(() => (state === 'studying' ? `${label.text} · 第 ${cycleCount} 轮` : label.text), [cycleCount, label.text, state])

  return (
    <div className="text-center">
      <div className={`inline-flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-4 text-sm font-medium ${label.className}`}>{text}</div>
      <div className="mt-2 text-sm text-gray-400">{currentCategory ? `${currentCategory.icon} ${currentCategory.name}` : '选择分类后开始'}</div>
    </div>
  )
})

StateLabel.displayName = 'StateLabel'
