// ui/src/components/common/QuickEntryGrid.tsx
import { memo, useMemo } from 'react'
import { BlueIcon, type BlueIconName } from './BlueIcon'

export interface QuickEntry {
  id: string
  label: string
  icon: BlueIconName
  onClick?: () => void
}

interface QuickEntryGridProps {
  entries: QuickEntry[]
}

export const QuickEntryGrid = memo(({ entries }: QuickEntryGridProps) => {
  const visibleEntries = useMemo(() => entries.slice(0, 8), [entries])

  return (
    <div className="grid grid-cols-4 gap-2">
      {visibleEntries.map((entry) => (
        <button
          key={entry.id}
          type="button"
          onClick={entry.onClick}
          className="flex min-h-11 flex-col items-center justify-center gap-1 rounded-xl border border-gray-100 bg-white text-xs font-semibold text-gray-900 active:bg-gray-100 md:hover:bg-gray-50"
        >
          <span className="text-blue-600">
            <BlueIcon name={entry.icon} />
          </span>
          <span>{entry.label}</span>
        </button>
      ))}
    </div>
  )
})

QuickEntryGrid.displayName = 'QuickEntryGrid'
