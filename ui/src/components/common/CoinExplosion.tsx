// ui/src/components/common/CoinExplosion.tsx
import { memo, useEffect, useState } from 'react'

interface Particle {
  id: number
  x: number
  y: number
  angle: number
  distance: number
  emoji: string
}

const EMOJIS = ['🪙', '✨', '⭐', '💎', '🌟']

interface Props {
  x?: number
  y?: number
  onComplete?: () => void
}

export const CoinExplosion = memo(({ x, y, onComplete }: Props) => {
  const [particles, setParticles] = useState<Particle[]>([])

  useEffect(() => {
    const items: Particle[] = []
    for (let i = 0; i < 30; i++) {
      // 180度扇形，向上扩散：角度在 -Math.PI 到 0 之间
      const angle = -Math.PI + (Math.PI * i) / 29 + (Math.random() - 0.5) * 0.1
      items.push({
        id: i,
        x: x ?? (typeof window !== 'undefined' ? window.innerWidth / 2 : 200),
        y: y ?? (typeof window !== 'undefined' ? window.innerHeight / 2 : 400),
        angle: angle,
        distance: 50 + Math.random() * 150,
        emoji: EMOJIS[Math.floor(Math.random() * EMOJIS.length)],
      })
    }
    setParticles(items)
    const timer = setTimeout(() => {
      setParticles([])
      onComplete?.()
    }, 1500)
    return () => clearTimeout(timer)
  }, [x, y, onComplete])

  if (particles.length === 0) return null

  return (
    <div className="pointer-events-none fixed inset-0 z-[100]">
      {particles.map(p => (
        <span
          key={p.id}
          className="absolute text-2xl animate-coin-fly"
          style={{
            left: `${p.x}px`,
            top: `${p.y}px`,
            '--tx': `${Math.cos(p.angle) * p.distance}px`,
            '--ty': `${Math.sin(p.angle) * p.distance - 40}px`,
            animation: 'coinFly 1.5s ease-out forwards',
          } as any}
        >{p.emoji}</span>
      ))}
      <style>{`
        @keyframes coinFly {
          0% { opacity: 1; transform: translate(0, 0) scale(1); }
          100% { opacity: 0; transform: translate(var(--tx), var(--ty)) scale(0.3); }
        }
      `}</style>
    </div>
  )
})

CoinExplosion.displayName = 'CoinExplosion'
