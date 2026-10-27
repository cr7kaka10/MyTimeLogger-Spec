import { useId, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { ChecklistItem } from '../../types'

const renderTitle = (title: string) => title.split(/(https?:\/\/[^\s]+)/g).map((part, index) =>
  /^https?:\/\//.test(part)
    ? <a key={index} href={part} target="_blank" rel="noopener noreferrer"
        className="break-all text-blue-600 underline decoration-blue-300 underline-offset-2 hover:text-blue-700 dark:text-blue-300 dark:decoration-blue-600"
        onClick={event => event.stopPropagation()}>{part}</a>
    : <span key={index}>{part}</span>
)

export function ChecklistItemsPreview({ items }: { items?: readonly ChecklistItem[] }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  if (!items?.length) return null
  const done = items.filter(item => item.status === 2).length

  return (
    <div className="mt-2 min-w-0">
      <button type="button" aria-expanded={open} aria-controls={listId}
        onClick={() => setOpen(value => !value)}
        className="group inline-flex max-w-full items-center gap-2 rounded-lg border border-blue-100 bg-blue-50/70 px-2.5 py-1 text-left text-xs font-medium text-blue-700 transition-colors hover:bg-blue-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/50">
        <span className="shrink-0 font-semibold">检查项</span>
        <span className="shrink-0 tabular-nums">{done}/{items.length}</span>
        <span className="h-1 w-10 shrink-0 overflow-hidden rounded-full bg-blue-200 dark:bg-blue-900" aria-hidden="true">
          <span className="block h-full rounded-full bg-blue-500" style={{ width: `${done / items.length * 100}%` }} />
        </span>
        <ChevronDown size={13} aria-hidden="true" className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <ol id={listId} hidden={!open} aria-label="滴答清单检查项（只读）"
        className="mt-2 overflow-hidden rounded-xl border border-gray-100 bg-gray-50/60 px-3 py-0.5 text-xs dark:border-gray-700 dark:bg-gray-900/35">
        {items.map(item => <li key={item.id} className="flex min-w-0 gap-2.5 border-b border-gray-100 py-2.5 last:border-b-0 dark:border-gray-700/70">
          <span role="img" aria-label={item.status === 2 ? '已完成' : '未完成'}
            className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px] ${item.status === 2 ? 'border-blue-500 bg-blue-500 text-white' : 'border-gray-300 bg-white dark:border-gray-500 dark:bg-gray-800'}`}>
            {item.status === 2 ? '✓' : ''}
          </span>
          <span className={`min-w-0 flex-1 break-words leading-5 ${item.status === 2 ? 'theme-muted line-through opacity-75' : 'text-gray-700 dark:text-gray-100'}`}>
            {renderTitle(item.title)}
          </span>
        </li>)}
      </ol>
    </div>
  )
}
