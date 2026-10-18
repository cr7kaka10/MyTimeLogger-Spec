// ui/src/components/common/BottomSheet.tsx
import { memo, useEffect, type MouseEvent, type ReactNode } from 'react'

interface BottomSheetProps {
  open: boolean
  onClose: () => void
  children: ReactNode
  layerClass?: string
  panelClass?: string
  ariaLabel?: string
}

export const BottomSheet = memo(({ open, onClose, children, layerClass = 'z-50', panelClass = '', ariaLabel }: BottomSheetProps) => {
  useEffect(() => {
    if (!open) return
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose, open])
  if (!open) return null
  const contentClass = panelClass || 'overflow-y-auto p-6'

  return (
    <div className={`fixed inset-0 ${layerClass} flex h-screen h-[100dvh] items-end justify-center bg-black/30 backdrop-blur-[1px]`} role="dialog" aria-modal="true" aria-label={ariaLabel}>
      <button type="button" aria-label="关闭" className="absolute inset-0 z-0 h-full w-full" onClick={onClose} />
      <div className={`theme-surface relative z-10 max-h-[calc(100dvh-1rem)] w-full rounded-t-2xl border bg-white shadow-2xl dark:bg-gray-900 ${contentClass}`} onClick={(event: MouseEvent<HTMLDivElement>) => event.stopPropagation()}>{children}</div>
    </div>
  )
})

BottomSheet.displayName = 'BottomSheet'
