// ui/src/components/common/BlueIcon.tsx
import { memo } from 'react'

export type BlueIconName = 'target' | 'book' | 'checklist' | 'habit' | 'moon' | 'gift' | 'bag' | 'settings'

interface BlueIconProps {
  name: BlueIconName
  className?: string
}

const pathMap: Record<BlueIconName, string[]> = {
  target: ['M12 4a8 8 0 1 0 8 8', 'M12 8a4 4 0 1 0 4 4', 'M12 12h9', 'm18 9 3 3-3 3'],
  book: ['M5 5h10a4 4 0 0 1 4 4v10H9a4 4 0 0 0-4-4V5Z', 'M5 15a4 4 0 0 1 4-4h10', 'M9 5v10'],
  checklist: ['M8 7h11', 'M8 12h11', 'M8 17h11', 'm4 7 1 1 2-3', 'm4 12 1 1 2-3', 'm4 17 1 1 2-3'],
  habit: ['M20 7 9 18l-5-5', 'M17 7h3v3'],
  moon: ['M20 15.5A8 8 0 1 1 8.5 4 6 6 0 0 0 20 15.5Z'],
  gift: ['M4 10h16v10H4V10Z', 'M4 10h16', 'M12 10v10', 'M7 10a3 3 0 1 1 5 0', 'M17 10a3 3 0 1 0-5 0'],
  bag: ['M6 8h12l1 12H5L6 8Z', 'M9 8a3 3 0 0 1 6 0'],
  settings: ['M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z', 'M4 12h2', 'M18 12h2', 'M12 4v2', 'M12 18v2', 'm6 6-1.4 1.4', 'M7.4 16.6 6 18', 'm18 18-1.4-1.4', 'M7.4 7.4 6 6'],
}

export const BlueIcon = memo(({ name, className = 'h-5 w-5' }: BlueIconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    {pathMap[name].map((d) => (
      <path key={d} d={d} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    ))}
  </svg>
))

BlueIcon.displayName = 'BlueIcon'
