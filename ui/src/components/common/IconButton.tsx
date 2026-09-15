// ui/src/components/common/IconButton.tsx
import { memo, type ReactNode } from 'react'

interface IconButtonProps {
  label: string
  children: ReactNode
  onClick?: () => void
  active?: boolean
}

export const IconButton = memo(({ label, children, onClick, active = false }: IconButtonProps) => (
  <button
    type="button"
    aria-label={label}
    onClick={onClick}
    className={`flex h-11 w-11 items-center justify-center rounded-lg text-gray-600 active:bg-gray-200 md:hover:bg-gray-100 ${active ? 'text-blue-600' : ''}`}
  >
    {children}
  </button>
))

IconButton.displayName = 'IconButton'
