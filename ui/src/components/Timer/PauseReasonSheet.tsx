// ui/src/components/Timer/PauseReasonSheet.tsx
import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { BottomSheet } from '../common/BottomSheet'
import { scheduleTimerInputFocus } from './summaryInputFocus'
import { createTimerInputTrace, observeEventLoopLag } from './timerInputTelemetry'

const PRESETS = ['喝水', '去洗手间', '接电话', '休息一下', '其他']

interface Props {
  onConfirm: (reason: string) => void
  onSkip: () => void
}

export const PauseReasonSheet = memo(({ onConfirm, onSkip }: Props) => {
  const [custom, setCustom] = useState('')
  const [selected, setSelected] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const trace = useRef(createTimerInputTrace('pause'))

  useEffect(() => {
    if (!inputRef.current) return
    trace.current.mark('sheet.mount.requested'); trace.current.mark('sheet.mount.completed')
    const stopLag = observeEventLoopLag(trace.current)
    const stopFocus = scheduleTimerInputFocus(inputRef.current, 0, undefined, { report: (event, details) => trace.current.mark(event, details) })
    return () => { stopLag(); stopFocus() }
  }, [])

  const handleConfirm = useCallback(() => {
    onConfirm(selected || custom || '未填写')
  }, [selected, custom, onConfirm])

  return (
    <BottomSheet open onClose={onSkip}>
      <div className="space-y-4 p-4">
        <h3 className="text-lg font-bold text-gray-900">暂停原因</h3>
        <div className="flex flex-wrap gap-2">{PRESETS.map(p => (
          <button key={p} type="button" onClick={() => { setSelected(p); setCustom('') }} className={`rounded-full px-4 py-1.5 text-sm ${selected === p ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 active:bg-gray-200'}`}>{p}</button>
        ))}</div>
        <input ref={inputRef} type="text" value={custom} onChange={e => { setCustom(e.target.value); setSelected('') }} placeholder="自定义原因..." className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
        <div className="flex gap-2">
          <button onClick={onSkip} className="flex-1 h-12 rounded-xl bg-gray-100 text-base font-semibold text-gray-500">跳过</button>
          <button onClick={handleConfirm} className="flex-1 h-12 rounded-xl bg-blue-500 text-base font-semibold text-white active:bg-blue-600">确认</button>
        </div>
      </div>
    </BottomSheet>
  )
})

PauseReasonSheet.displayName = 'PauseReasonSheet'
