// ui/src/components/Sleep/SleepTrendChart.tsx
import { memo, useEffect, useRef, useState } from 'react'

interface SleepDay {
  date: string
  deep_sleep_min?: number
  light_sleep_min?: number
  rem_sleep_min?: number
  total_sleep_min?: number
  sleep_score?: number
  fall_asleep_min?: number
  wake_up_min?: number
  sleep_cycles?: number
}

interface Props {
  data: SleepDay[]
}

const H = 180; const PAD = { top: 20, right: 16, bottom: 28, left: 36 }

export const SleepTrendChart = memo(({ data }: Props) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [selectedMetric, setSelectedMetric] = useState<'total' | 'score' | 'deep' | 'fall_asleep' | 'wake_up' | 'cycles'>('total')

  // Chronological order: ascending by date YYYY-MM-DD
  const sortedData = [...data].sort((a, b) => a.date.localeCompare(b.date))

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || sortedData.length === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const containerWidth = canvas.parentElement?.clientWidth || 320
    const CW = containerWidth - PAD.left - PAD.right
    const CH = H - PAD.top - PAD.bottom

    const dpr = window.devicePixelRatio || 1
    canvas.width = containerWidth * dpr; canvas.height = H * dpr
    canvas.style.width = containerWidth + 'px'; canvas.style.height = H + 'px'
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, containerWidth, H)

    // Calculate max value for scaling
    let maxVal = 1
    if (selectedMetric === 'total') {
      maxVal = Math.max(1, ...sortedData.map(d => d.total_sleep_min || 0))
    } else if (selectedMetric === 'score') {
      maxVal = 100
    } else if (selectedMetric === 'deep') {
      maxVal = Math.max(1, ...sortedData.map(d => d.deep_sleep_min || 0))
    } else if (selectedMetric === 'fall_asleep') {
      maxVal = Math.max(1, ...sortedData.map(d => d.fall_asleep_min || 0))
    } else if (selectedMetric === 'wake_up') {
      maxVal = Math.max(1, ...sortedData.map(d => d.wake_up_min || 0))
    } else if (selectedMetric === 'cycles') {
      maxVal = Math.max(1, ...sortedData.map(d => d.sleep_cycles || 0))
    }

    const stepX = CW / Math.max(1, sortedData.length - 1)

    // Grid lines and Y labels
    ctx.strokeStyle = '#f3f4f6'; ctx.lineWidth = 1
    for (let i = 0; i <= 4; i++) {
      const y = PAD.top + (CH / 4) * i
      ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(containerWidth - PAD.right, y); ctx.stroke()

      ctx.fillStyle = '#9ca3af'; ctx.font = '9px sans-serif'; ctx.textAlign = 'right'
      const gridVal = maxVal * (4 - i) / 4
      let label = `${Math.round(gridVal)}`
      if (selectedMetric === 'total' || selectedMetric === 'deep') {
        label = gridVal >= 60 ? `${Math.round(gridVal / 60)}h` : `${Math.round(gridVal)}m`
      } else if (selectedMetric === 'score') {
        label = `${Math.round(gridVal)}分`
      } else if (selectedMetric === 'cycles') {
        label = `${gridVal.toFixed(1)}次`
      } else {
        label = `${Math.round(gridVal)}m`
      }
      ctx.fillText(label, PAD.left - 6, y + 3)
    }

    // Render based on selectedMetric
    if (selectedMetric === 'total') {
      // Stacked areas: deep + light + rem
      const drawArea = (key: 'deep_sleep_min' | 'light_sleep_min' | 'rem_sleep_min', color: string, offsetKeys: ('deep_sleep_min' | 'light_sleep_min' | 'rem_sleep_min')[]) => {
        ctx.fillStyle = color; ctx.beginPath()
        sortedData.forEach((d, i) => {
          const x = PAD.left + i * stepX
          const base = offsetKeys.reduce((sum, k) => sum + (d[k] || 0), 0)
          const val = d[key] || 0
          const y = PAD.top + CH - ((base + val) / maxVal) * CH
          if (i === 0) {
            ctx.moveTo(x, PAD.top + CH)
            ctx.lineTo(x, y)
          } else {
            ctx.lineTo(x, y)
          }
        })
        for (let i = sortedData.length - 1; i >= 0; i--) {
          const x = PAD.left + i * stepX
          const base = offsetKeys.reduce((sum, k) => sum + (sortedData[i][k] || 0), 0)
          const y = PAD.top + CH - (base / maxVal) * CH
          ctx.lineTo(x, y)
        }
        ctx.closePath(); ctx.fill()
      }

      drawArea('rem_sleep_min', 'rgba(168,85,247,0.3)', [])
      drawArea('light_sleep_min', 'rgba(56,189,248,0.3)', ['rem_sleep_min'])
      drawArea('deep_sleep_min', 'rgba(59,130,246,0.4)', ['rem_sleep_min', 'light_sleep_min'])
    } else {
      // Line + Gradient Area Chart for other metrics
      const fieldMap = {
        score: 'sleep_score',
        deep: 'deep_sleep_min',
        fall_asleep: 'fall_asleep_min',
        wake_up: 'wake_up_min',
        cycles: 'sleep_cycles'
      } as const

      const field = fieldMap[selectedMetric]
      const colorMap = {
        score: '#3b82f6',
        deep: '#4f46e5',
        fall_asleep: '#f59e0b',
        wake_up: '#ec4899',
        cycles: '#8b5cf6'
      } as const
      const color = colorMap[selectedMetric]

      // Draw Gradient Area
      const grad = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + CH)
      grad.addColorStop(0, color + '33')
      grad.addColorStop(1, color + '00')
      ctx.fillStyle = grad
      ctx.beginPath()
      sortedData.forEach((d, i) => {
        const x = PAD.left + i * stepX
        const val = d[field] || 0
        const y = PAD.top + CH - (val / maxVal) * CH
        if (i === 0) {
          ctx.moveTo(x, PAD.top + CH)
          ctx.lineTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      })
      ctx.lineTo(PAD.left + (sortedData.length - 1) * stepX, PAD.top + CH)
      ctx.closePath(); ctx.fill()

      // Draw line
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath()
      sortedData.forEach((d, i) => {
        const x = PAD.left + i * stepX
        const val = d[field] || 0
        const y = PAD.top + CH - (val / maxVal) * CH
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()

      // Draw dots
      ctx.fillStyle = '#ffffff'; ctx.strokeStyle = color; ctx.lineWidth = 1.5
      sortedData.forEach((d, i) => {
        const x = PAD.left + i * stepX
        const val = d[field] || 0
        const y = PAD.top + CH - (val / maxVal) * CH
        ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
      })
    }

    // Date labels
    ctx.fillStyle = '#9ca3af'; ctx.font = '9px sans-serif'; ctx.textAlign = 'center'
    sortedData.forEach((d, i) => {
      const x = PAD.left + i * stepX
      const label = (d.date || '').slice(5) // MM-DD
      ctx.fillText(label, x, H - 6)
    })
  }, [sortedData, selectedMetric])

  if (sortedData.length === 0) {
    return <div className="flex h-48 items-center justify-center text-sm text-gray-400 dark:text-gray-500">暂无睡眠数据</div>
  }

  const buttons = [
    { key: 'total', label: '总时长' },
    { key: 'deep', label: '深睡' },
    { key: 'score', label: '评分' },
    { key: 'fall_asleep', label: '入睡' },
    { key: 'wake_up', label: '醒来' },
    { key: 'cycles', label: '周期' }
  ] as const

  return (
    <div className="space-y-3 font-sans">
      <div className="flex flex-wrap gap-1.5 pb-1">
        {buttons.map(b => (
          <button
            key={b.key}
            type="button"
            onClick={() => setSelectedMetric(b.key)}
            className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all duration-200 ${
              selectedMetric === b.key
                ? 'bg-blue-600 text-white shadow-sm shadow-blue-200'
                : 'bg-gray-50 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600 dark:hover:text-white'
            }`}
          >
            {b.label}
          </button>
        ))}
      </div>
      <div className="relative">
        <canvas ref={canvasRef} className="w-full" style={{ height: H }} />
      </div>
    </div>
  )
})

SleepTrendChart.displayName = 'SleepTrendChart'
