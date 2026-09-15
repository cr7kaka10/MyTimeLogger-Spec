import { useRef, type PointerEvent, type ReactNode } from 'react'

export function PressableCheckRow({ children, onTap, onLong, className = '', disabled = false }: {
  children: ReactNode; onTap: () => void; onLong: () => void; className?: string; disabled?: boolean
}) {
  const timer = useRef<number>(), start = useRef([0, 0]), moved = useRef(false), long = useRef(false)
  const isBox = (e: PointerEvent | React.MouseEvent) => !!(e.target as HTMLElement).closest('.ex-box')
  const down = (e: PointerEvent) => {
    if (disabled || e.button !== 0 || !isBox(e)) return
    start.current = [e.clientX, e.clientY]; moved.current = false; long.current = false
    timer.current = window.setTimeout(() => { if (!moved.current) { long.current = true; onLong(); navigator.vibrate?.(15) } }, 480)
  }
  const move = (e: PointerEvent) => {
    if (Math.abs(e.clientX - start.current[0]) > 10 || Math.abs(e.clientY - start.current[1]) > 10) {
      moved.current = true; clearTimeout(timer.current)
    }
  }
  const up = (e: PointerEvent) => {
    if (disabled || e.button !== 0 || !isBox(e)) return
    clearTimeout(timer.current); if (!moved.current && !long.current) onTap()
  }
  return <div className={`ex-check-row ${className}`} onPointerDown={down} onPointerMove={move} onPointerUp={up}
    onPointerCancel={() => clearTimeout(timer.current)} onContextMenu={e => {
      if (disabled || !isBox(e)) return; e.preventDefault(); clearTimeout(timer.current); onLong()
    }}>{children}</div>
}
