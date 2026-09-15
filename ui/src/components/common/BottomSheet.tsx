// ui/src/components/common/BottomSheet.tsx
import { memo, type MouseEvent, type ReactNode } from 'react'

interface BottomSheetProps {
  open: boolean
  onClose: () => void
  children: ReactNode
  layerClass?: string
}

export const BottomSheet = memo(({ open, onClose, children, layerClass = 'z-50' }: BottomSheetProps) => {
  if (!open) return null

  return (
    <div className={`fixed inset-0 ${layerClass} flex h-screen h-[100dvh] items-end bg-black/20`} role="dialog" aria-modal="true">
      <button type="button" aria-label="关闭" className="absolute inset-0 z-0 h-full w-full" onClick={onClose} />
      <div className="relative z-10 max-h-[calc(100dvh-1rem)] w-full overflow-y-auto rounded-t-2xl bg-white p-6" onClick={(event: MouseEvent<HTMLDivElement>) => event.stopPropagation()}>{children}</div>
    </div>
  )
})

BottomSheet.displayName = 'BottomSheet'
