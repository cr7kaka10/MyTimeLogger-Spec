// ui/src/components/Timer/StatusSwitchNoteSheet.tsx
import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { BottomSheet } from '../common/BottomSheet'
import { toggleStatusSwitchPreset } from '../../hooks/statusSwitchFlow'
import { scheduleTimerInputFocus } from './summaryInputFocus'
import { createTimerInputTrace, observeEventLoopLag } from './timerInputTelemetry'
import { TIMER_NOTE_PRESETS } from './notePresets'

interface Props {
  onConfirm: (note: string) => void
  onClose: () => void
}

export const StatusSwitchNoteSheet = memo(({ onConfirm, onClose }: Props) => {
  const [custom, setCustom] = useState('')
  const [selected, setSelected] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const trace = useRef(createTimerInputTrace('status'))

  useEffect(() => {
    if (!inputRef.current) return
    trace.current.mark('sheet.mount.requested'); trace.current.mark('sheet.mount.completed')
    const stopLag = observeEventLoopLag(trace.current)
    const stopFocus = scheduleTimerInputFocus(inputRef.current, 0, undefined, { report: (event, details) => trace.current.mark(event, details) })
    return () => { stopLag(); stopFocus() }
  }, [])

  const handleConfirm = useCallback(() => {
    onConfirm(selected || custom || '状态切换')
  }, [selected, custom, onConfirm])

  return (
    <BottomSheet open onClose={onClose}>
      <div className="space-y-4 p-4">
        <h3 className="text-lg font-bold text-gray-900">状态切换备注</h3>
        <div className="flex flex-wrap gap-2">{TIMER_NOTE_PRESETS.map(p => (
          <button key={p} type="button" onClick={() => { setSelected(current => toggleStatusSwitchPreset(current, p)); setCustom('') }} className={`rounded-full px-4 py-1.5 text-sm ${selected === p ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 active:bg-gray-200'}`}>{p}</button>
        ))}</div>
        <input ref={inputRef} type="text" value={custom} onChange={e => { setCustom(e.target.value); setSelected('') }} placeholder="自定义备注..." className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        <div className="flex gap-2">
          <button onClick={onClose} className="flex-1 h-12 rounded-xl bg-gray-100 text-base font-semibold text-gray-500">稍后</button>
          <button onClick={handleConfirm} className="flex-1 h-12 rounded-xl bg-blue-500 text-base font-semibold text-white active:bg-blue-600">确认</button>
        </div>
      </div>
    </BottomSheet>
  )
})

StatusSwitchNoteSheet.displayName = 'StatusSwitchNoteSheet'
