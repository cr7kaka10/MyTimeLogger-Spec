// ui/src/components/common/NumberSheet.tsx
import { memo, useCallback, useState } from 'react'
import { BottomSheet } from './BottomSheet'

interface NumberSheetProps {
  title: string
  value: number
  min?: number
  max?: number
  onSave: (v: number) => void
  onClose: () => void
}

export const NumberSheet = memo(({ title, value, min = 1, max = 180, onSave, onClose }: NumberSheetProps) => {
  const [draft, setDraft] = useState(value)

  const handleSave = useCallback(() => {
    const numericDraft = Number(draft)
    const nextValue = Number.isFinite(numericDraft) ? numericDraft : value
    const clamped = Math.max(min, Math.min(max, nextValue))
    if (clamped !== value) onSave(clamped)
    onClose()
  }, [draft, value, min, max, onSave, onClose])

  return (
    <BottomSheet open onClose={onClose}>
      <div className="space-y-4 p-4">
        <h3 className="text-lg font-bold text-gray-900">{title}</h3>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setDraft(prev => Math.max(min, prev - 1))}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-gray-100 text-xl font-bold text-gray-600 active:bg-gray-200"
          >−</button>
          <input
            type="number"
            value={draft}
            onChange={e => setDraft(Number(e.target.value))}
            min={min}
            max={max}
            className="flex-1 rounded-lg border border-gray-200 px-4 py-2 text-center text-2xl font-bold text-gray-900 outline-none focus:border-blue-400"
          />
          <button
            type="button"
            onClick={() => setDraft(prev => Math.min(max, prev + 1))}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-gray-100 text-xl font-bold text-gray-600 active:bg-gray-200"
          >+</button>
        </div>
        <div className="flex gap-2 text-xs text-gray-400 justify-center">
          <span>最小: {min}</span><span>最大: {max}</span>
        </div>
        <button
          type="button"
          onClick={handleSave}
          className="h-12 w-full rounded-xl bg-blue-500 text-base font-semibold text-white active:bg-blue-600"
        >保存</button>
      </div>
    </BottomSheet>
  )
})

NumberSheet.displayName = 'NumberSheet'
