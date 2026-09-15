// ui/src/components/common/DatePicker.tsx
import { memo } from 'react'

interface DatePickerProps {
  date: string
  onPrev: () => void
  onNext: () => void
}

export const DatePicker = memo(({ date, onPrev, onNext }: DatePickerProps) => (
  <div className="grid h-12 grid-cols-[44px_1fr_44px] items-center border-b border-gray-100 bg-white text-center text-sm font-semibold text-gray-900">
    <button type="button" aria-label="前一天" className="h-11 rounded-lg active:bg-gray-100 md:hover:bg-gray-50" onClick={onPrev}>
      ‹
    </button>
    <span>{date}</span>
    <button type="button" aria-label="后一天" className="h-11 rounded-lg active:bg-gray-100 md:hover:bg-gray-50" onClick={onNext}>
      ›
    </button>
  </div>
))

DatePicker.displayName = 'DatePicker'
