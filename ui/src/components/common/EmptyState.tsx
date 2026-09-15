// ui/src/components/common/EmptyState.tsx
import { memo } from 'react'

interface EmptyStateProps {
  icon: string
  title: string
  description: string
  actionLabel?: string
  onAction?: () => void
}

export const EmptyState = memo(({ icon, title, description, actionLabel, onAction }: EmptyStateProps) => (
  <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
    <div className="text-3xl">{icon}</div>
    <h2 className="mt-4 text-lg font-semibold text-gray-900">{title}</h2>
    <p className="mt-2 text-sm text-gray-400">{description}</p>
    {actionLabel ? (
      <button type="button" onClick={onAction} className="mt-6 min-h-11 rounded-xl bg-blue-600 px-6 text-sm font-semibold text-white">
        {actionLabel}
      </button>
    ) : null}
  </div>
))

EmptyState.displayName = 'EmptyState'
