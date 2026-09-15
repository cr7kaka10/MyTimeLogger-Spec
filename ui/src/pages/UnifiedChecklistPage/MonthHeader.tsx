// ui/src/pages/UnifiedChecklistPage/MonthHeader.tsx
// 月份标题组件
import { memo } from 'react'

interface MonthHeaderProps {
  date: Date
  isExpanded?: boolean
  onToggle?: () => void
}

export const MonthHeader = memo(({ date, isExpanded, onToggle }: MonthHeaderProps) => {
  // 安全检查：确保 date 是有效的 Date 对象
  if (!date || !(date instanceof Date) || isNaN(date.getTime())) {
    return (
      <div className="px-4 py-4 bg-white rounded-2xl border border-gray-100/80 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900 tracking-tight">--</h2>
      </div>
    )
  }

  const monthNames = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']
  const monthName = monthNames[date.getMonth()]

  return (
    <div 
      className="px-4 py-4 bg-white rounded-2xl border border-gray-100/80 shadow-sm flex items-center justify-between cursor-pointer hover:bg-gray-50 transition-colors"
      onClick={onToggle}
      role="button"
      aria-expanded={isExpanded}
    >
      <h2 className="text-base font-semibold text-gray-900 tracking-tight">{monthName}</h2>
      <svg 
        xmlns="http://www.w3.org/2000/svg" 
        width="20" 
        height="20" 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="currentColor" 
        strokeWidth="2" 
        strokeLinecap="round" 
        strokeLinejoin="round" 
        className={`text-gray-400 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}
      >
        <path d="m6 9 6 6 6-6"/>
      </svg>
    </div>
  )
})

MonthHeader.displayName = 'MonthHeader'
