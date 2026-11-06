import { useEffect, useRef, useState } from 'react'
import { mealWheelDisplayPercentages, mealWheelProbabilities, type MealWheelConfig, type MealWheelItem } from '../../mealWheel/config'
import { pickMealWheelItem } from '../../mealWheel/selection'
import { loadMealWheel } from '../../mealWheel/store'

const colors = ['fill-rose-400 dark:fill-rose-600', 'fill-amber-400 dark:fill-amber-600', 'fill-emerald-400 dark:fill-emerald-600', 'fill-sky-400 dark:fill-sky-600', 'fill-violet-400 dark:fill-violet-600', 'fill-orange-400 dark:fill-orange-600']
const point = (degrees: number, radius: number) => ({ x: 150 + Math.cos(degrees * Math.PI / 180) * radius, y: 150 + Math.sin(degrees * Math.PI / 180) * radius })

function sections(items: MealWheelItem[]) {
  const probabilities = mealWheelProbabilities(items)
  let angle = -90
  return items.map((item, index) => {
    const start = angle, sweep = probabilities[index] * 360, end = angle += sweep
    const a = point(start, 143), b = point(end, 143), label = point(start + sweep / 2, 93)
    const labelChars = sweep >= 45 ? 5 : sweep >= 30 ? 3 : sweep >= 18 ? 2 : 0
    return <g key={item.id}>
      <title>{item.name}</title>
      <path d={`M 150 150 L ${a.x} ${a.y} A 143 143 0 ${sweep > 180 ? 1 : 0} 1 ${b.x} ${b.y} Z`} className={colors[index % colors.length]} stroke="currentColor" strokeWidth="2" />
      {labelChars > 0 && <text x={label.x} y={label.y} textAnchor="middle" dominantBaseline="middle" className="fill-gray-950 text-[13px] font-bold dark:fill-white">{Array.from(item.name).slice(0, labelChars).join('')}</text>}
    </g>
  })
}

export function MealWheelSheet({ onClose }: { onClose: () => void }) {
  const [config, setConfig] = useState<MealWheelConfig | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [rotation, setRotation] = useState(0)
  const [spinning, setSpinning] = useState(false)
  const [result, setResult] = useState<MealWheelItem | null>(null)
  const timer = useRef<number | null>(null)
  const spinningRef = useRef(false)
  useEffect(() => {
    let active = true
    const refresh = () => { void loadMealWheel().then(value => { if (active && !spinningRef.current) { setConfig(value); setLoadError(false) } }).catch(() => { if (active) setLoadError(true) }) }
    refresh()
    window.addEventListener('sync-pull-complete', refresh)
    window.addEventListener('mtl:meal-wheel-changed', refresh)
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', escape)
    return () => { active = false; if (timer.current !== null) window.clearTimeout(timer.current); window.removeEventListener('sync-pull-complete', refresh); window.removeEventListener('mtl:meal-wheel-changed', refresh); window.removeEventListener('keydown', escape) }
  }, [])

  const spin = () => {
    if (!config || spinning) return
    const item = pickMealWheelItem(config.items)
    const total = config.items.reduce((sum, entry) => sum + entry.weight, 0)
    const before = config.items.slice(0, config.items.findIndex(entry => entry.id === item.id)).reduce((sum, entry) => sum + entry.weight, 0)
    const midpoint = (before + item.weight / 2) / total * 360
    const target = (360 - midpoint) % 360
    const delta = (target - rotation % 360 + 360) % 360
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 4000
    spinningRef.current = true; setResult(null); setSpinning(true); setRotation(rotation + 1800 + delta)
    timer.current = window.setTimeout(() => { spinningRef.current = false; setResult(item); setSpinning(false); timer.current = null }, duration)
  }

  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section role="dialog" aria-modal="true" aria-label="选餐转盘" className="theme-surface max-h-[94dvh] w-full max-w-[480px] overflow-y-auto rounded-3xl border p-5 shadow-2xl">
      <header className="mb-3 flex items-center justify-between"><h2 className="text-lg font-bold">今天吃什么？</h2><button type="button" onClick={onClose} aria-label="关闭转盘" className="rounded-lg px-3 py-1 text-sm hover:bg-gray-100 dark:hover:bg-gray-700">关闭</button></header>
      {loadError ? <p role="alert">读取餐食选项失败，请关闭后重试</p> : !config ? <p role="status">正在读取餐食选项…</p> : <>
        <div className="relative mx-auto aspect-square w-full max-w-[310px]">
          <span aria-hidden="true" className="absolute left-1/2 top-0 z-10 -translate-x-1/2 text-3xl text-gray-900 dark:text-white">▼</span>
          <svg viewBox="0 0 300 300" className="h-full w-full drop-shadow-lg" style={{ transform: `rotate(${rotation}deg)`, transition: `transform ${window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 4000}ms cubic-bezier(.16,.72,.12,1)` }} aria-label="餐食概率转盘">{sections(config.items)}<circle cx="150" cy="150" r="19" className="fill-white dark:fill-gray-900" /></svg>
        </div>
        <p className="my-3 min-h-8 text-center text-lg font-bold" aria-live="polite">{spinning ? '转盘转动中…' : result ? `就吃：${result.name}` : '转动转盘，决定这一餐'}</p>
        <button type="button" onClick={spin} disabled={spinning} className="w-full rounded-xl bg-blue-600 py-3 font-bold text-white disabled:opacity-50">{result ? '再转一次' : '开始转动'}</button>
        <ul className="mt-4 grid grid-cols-2 gap-1 text-xs text-gray-600 dark:text-gray-300">{config.items.map((item, index) => <li key={item.id}>{item.name} · {mealWheelDisplayPercentages(config.items)[index].toFixed(1)}%</li>)}</ul>
      </>}
    </section>
  </div>
}
