import { useEffect } from 'react'

interface ConfirmSheetProps {
  open: boolean
  title: string
  message: string
  confirmLabel: string
  busy?: boolean
  error?: string
  onClose: () => void
  onConfirm: () => void
}

export function ConfirmSheet({ open, title, message, confirmLabel, busy = false, error, onClose, onConfirm }: ConfirmSheetProps) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [busy, onClose, open])
  if (!open) return null
  return <div className="fixed inset-0 z-[80] flex items-end bg-black/40 p-0 sm:items-center sm:justify-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}>
    <button type="button" className="absolute inset-0" aria-label="关闭" disabled={busy} onClick={onClose} />
    <section className="relative w-full max-w-sm space-y-4 rounded-t-xl bg-white p-5 shadow-xl dark:bg-gray-900 sm:rounded-xl">
      <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{title}</h2><p className="text-sm text-gray-600 dark:text-gray-300">{message}</p>
      {error && <p className="text-sm text-red-600 dark:text-red-300" role="alert">{error}</p>}
      <div className="flex justify-end gap-2"><button type="button" disabled={busy} onClick={onClose} className="h-10 px-4 text-sm text-gray-600 dark:text-gray-300">取消</button><button type="button" disabled={busy} onClick={onConfirm} className="h-10 rounded bg-red-600 px-4 text-sm font-medium text-white disabled:opacity-50">{busy ? '删除中…' : confirmLabel}</button></div>
    </section>
  </div>
}
