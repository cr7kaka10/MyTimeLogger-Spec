// ui/src/components/TimeBook/SessionEditSheet.tsx
import { memo, useCallback, useEffect, useState } from 'react'
import type { SessionEditData } from '../../types'
import { BottomSheet } from '../common/BottomSheet'
import { CategoryIcon } from '../common/CategoryIcon'
import { formatBeijingDate, parseBeijingDateTimeMs } from '@core/BeijingTime'
import { sessionBusinessDate } from '@core/SessionBusinessDate'
import { detectPlatformRuntime } from '../../platform/runtime'

const toDateTimeLocalSeconds = (value?: string): string => {
  if (!value) return ''
  const match = value.match(/^(\d{4}-\d{2}-\d{2})(?:T|\s)(\d{2}:\d{2})(?::(\d{2}))?/)
  return match ? `${match[1]}T${match[2]}:${match[3] ?? '00'}` : value.slice(0, 19)
}

const androidDateTimeText = (value: string): string => value.replace('T', ' ')
const normalizeAndroidDateTime = (value: string): string | null => /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value) ? value.replace(' ', 'T') : null
const isValidDateTime = (value: string): boolean => {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/)
  if (!match) return false
  const [, year, month, day, hour, minute, second] = match
  const check = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second)))
  return check.getUTCFullYear() === Number(year) && check.getUTCMonth() === Number(month) - 1 && check.getUTCDate() === Number(day) && check.getUTCHours() === Number(hour) && check.getUTCMinutes() === Number(minute) && check.getUTCSeconds() === Number(second) && Number.isFinite(parseBeijingDateTimeMs(value))
}

interface SessionEditSheetProps {
  session?: SessionEditData
  categories?: Array<{ id: number; name: string; icon?: string; color?: string }>
  onSave: (data: SessionEditData) => void
  onDelete?: (id: string | number) => void
  onClose: () => void
}

export const SessionEditSheet = memo(({ session, categories = [], onSave, onDelete, onClose }: SessionEditSheetProps) => {
  const [startTime, setStartTime] = useState(toDateTimeLocalSeconds(session?.start_time))
  const [endTime, setEndTime] = useState(toDateTimeLocalSeconds(session?.end_time))
  const [duration, setDuration] = useState(session?.net_duration_minutes || 0)
  const [durationSeconds, setDurationSeconds] = useState(session?.net_duration_seconds ?? (session?.net_duration_minutes || 0) * 60)
  const [categoryId, setCategoryId] = useState<number | null>(session?.category_id ?? null)
  const [categoryPickerOpen, setCategoryPickerOpen] = useState(false)
  const [summary, setSummary] = useState(session?.session_summary || '')
  const [timeError, setTimeError] = useState('')
  const isAndroid = detectPlatformRuntime() === 'capacitor-android'
  const selectedCategory = categories.find(category => category.id === categoryId)

  useEffect(() => {
    if (startTime && endTime) {
      const diffMs = parseBeijingDateTimeMs(endTime) - parseBeijingDateTimeMs(startTime)
      if (diffMs > 0) {
        setDuration(Math.round(diffMs / 60000))
        setDurationSeconds(Math.floor(diffMs / 1000))
      }
    }
  }, [startTime, endTime])

  const handleDurationChange = (val: number) => {
    setDuration(val)
    setDurationSeconds(val * 60)
  }

  const handleSave = useCallback(() => {
    const normalizedStart = isAndroid ? normalizeAndroidDateTime(androidDateTimeText(startTime)) : startTime
    const normalizedEnd = isAndroid ? normalizeAndroidDateTime(androidDateTimeText(endTime)) : endTime
    if (!normalizedStart || !normalizedEnd || !isValidDateTime(normalizedStart) || !isValidDateTime(normalizedEnd) || parseBeijingDateTimeMs(endTime) <= parseBeijingDateTimeMs(startTime)) {
      setTimeError('请输入有效的 24 小时时间（YYYY-MM-DD HH:mm:ss），且结束时间必须晚于开始时间。')
      return
    }
    setTimeError('')
    onSave({
      id: session?.id,
      start_time: normalizedStart,
      end_time: normalizedEnd,
      net_duration_minutes: duration,
      net_duration_seconds: durationSeconds,
      date: sessionBusinessDate(normalizedStart, normalizedEnd, formatBeijingDate()),
      category_id: categoryId,
      session_summary: summary,
    })
  }, [startTime, endTime, duration, durationSeconds, categoryId, summary, session, onSave, isAndroid])

  return (
    <BottomSheet open onClose={onClose}>
      <div className="space-y-4 p-4">
        <h3 className="text-lg font-bold text-gray-900">
          {session?.id ? '编辑会话' : '添加会话'}
        </h3>

        <label className="block">
          <span className="text-sm text-gray-500">开始时间</span>
          <input type={isAndroid ? 'text' : 'datetime-local'} step={isAndroid ? undefined : 1} inputMode={isAndroid ? 'numeric' : undefined} pattern={isAndroid ? '\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}' : undefined} placeholder={isAndroid ? 'YYYY-MM-DD HH:mm:ss' : undefined} aria-invalid={Boolean(timeError)} value={isAndroid ? androidDateTimeText(startTime) : startTime} onChange={e => { setTimeError(''); setStartTime(isAndroid ? e.target.value.replace(' ', 'T') : e.target.value) }}
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        </label>

        <label className="block">
          <span className="text-sm text-gray-500">结束时间</span>
          <input type={isAndroid ? 'text' : 'datetime-local'} step={isAndroid ? undefined : 1} inputMode={isAndroid ? 'numeric' : undefined} pattern={isAndroid ? '\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}' : undefined} placeholder={isAndroid ? 'YYYY-MM-DD HH:mm:ss' : undefined} aria-invalid={Boolean(timeError)} value={isAndroid ? androidDateTimeText(endTime) : endTime} onChange={e => { setTimeError(''); setEndTime(isAndroid ? e.target.value.replace(' ', 'T') : e.target.value) }}
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        </label>
        {timeError && <p role="alert" className="text-sm text-red-500">{timeError}</p>}

        <label className="block">
          <span className="text-sm text-gray-500">时长 (分钟)</span>
          <input type="number" value={duration} onChange={e => handleDurationChange(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        </label>

        <div className="block">
          <span className="text-sm text-gray-500">分类</span>
          <button type="button" onClick={() => setCategoryPickerOpen(true)} aria-haspopup="dialog"
            className="mt-1 flex w-full items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-left text-sm outline-none focus:border-blue-400">
            <CategoryIcon icon={selectedCategory?.icon} color={selectedCategory?.color || '#94a3b8'} className="h-5 w-5 shrink-0" />
            <span className="flex-1">{selectedCategory?.name || '无分类'}</span><span aria-hidden="true" className="text-gray-400">›</span>
          </button>
        </div>

        <label className="block">
          <span className="text-sm text-gray-500">备注</span>
          <textarea value={summary} onChange={e => setSummary(e.target.value)} rows={2}
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        </label>

        <div className="flex gap-2">
          <button onClick={handleSave}
            className="flex-1 h-12 rounded-xl bg-blue-500 text-base font-semibold text-white active:bg-blue-600">保存</button>
          {session?.id && onDelete && (
            <button onClick={() => onDelete(session.id!)}
              className="h-12 w-16 rounded-xl bg-red-50 text-base font-semibold text-red-500 active:bg-red-100">删除</button>
          )}
        </div>
      </div>
      <BottomSheet open={categoryPickerOpen} onClose={() => setCategoryPickerOpen(false)} layerClass="z-[60]">
        <div className="space-y-3">
          <h3 className="text-lg font-bold text-gray-900">选择分类</h3>
          <div className="space-y-2" role="radiogroup" aria-label="分类">
            {[{ id: null, name: '无分类', icon: undefined, color: '#94a3b8' }, ...categories].map(category => {
              const checked = category.id === categoryId
              return <button key={category.id ?? 'none'} type="button" role="radio" aria-checked={checked}
                onClick={() => { setCategoryId(category.id); setCategoryPickerOpen(false) }}
                className={`flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left ${checked ? 'border-blue-400 bg-blue-50' : 'border-gray-200'}`}>
                <CategoryIcon icon={category.icon} color={category.color} className="h-6 w-6 shrink-0" />
                <span className="flex-1 font-medium text-gray-900">{category.name}</span><span aria-hidden="true" className="text-blue-500">{checked ? '✓' : ''}</span>
              </button>
            })}
          </div>
        </div>
      </BottomSheet>
    </BottomSheet>
  )
})

SessionEditSheet.displayName = 'SessionEditSheet'
