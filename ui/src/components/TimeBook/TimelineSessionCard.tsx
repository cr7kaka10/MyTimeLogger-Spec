import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import { formatClockTime, formatDurationHms, resolveSessionDurationSeconds } from '@core/displayFormat'
import { CategoryIcon } from '../common/CategoryIcon'
import type { TimeBookTimelineEntry } from '../../hooks/useTimeBook'

export const TimelineSessionCard = memo(({ entry, onClick }: { entry: Extract<TimeBookTimelineEntry, { kind: 'session' }>; onClick: () => void }) => {
  const session: any = entry.session
  return <button type="button" onClick={onClick} className="theme-surface w-full rounded-md border border-l-4 p-2.5 text-left shadow-sm active:bg-gray-50 md:hover:bg-gray-50" style={{ borderLeftColor: session.category_color ?? 'var(--color-border)' }}><div className="flex flex-col items-start gap-0.5 text-xs text-gray-400 md:flex-row md:items-center md:justify-between md:gap-4"><span className="whitespace-nowrap">{formatClockTime(session.start_time)} - {formatClockTime(session.end_time)}</span><span>{formatDurationHms(resolveSessionDurationSeconds(session))}</span></div><div className="mt-1 flex items-center justify-between gap-3 text-sm font-semibold text-gray-900"><span className="flex items-center gap-1.5"><CategoryIcon icon={session.category_icon} color={session.category_color} className="h-4 w-4" />{session.category_name || '未知分类'}</span><span className="text-gray-400">›</span></div>{session.session_summary && <div className="mt-1 break-words text-xs leading-5 text-gray-600 dark:text-gray-300"><ReactMarkdown>{session.session_summary}</ReactMarkdown></div>}</button>
})

TimelineSessionCard.displayName = 'TimelineSessionCard'
