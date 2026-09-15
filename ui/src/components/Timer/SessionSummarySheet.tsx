// ui/src/components/Timer/SessionSummarySheet.tsx
import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { BottomSheet } from '../common/BottomSheet'
import { scheduleTimerInputFocus } from './summaryInputFocus'
import { createTimerInputTrace, observeEventLoopLag, type TimerInputTrace } from './timerInputTelemetry'

const INITIAL_SUMMARY = '1. '

interface Props {
  trace?: TimerInputTrace
  isEarlyEnd?: boolean
  onSave: (summary: string) => void
  onClose: () => void
}

export const SessionSummarySheet = memo(({ trace, isEarlyEnd, onSave, onClose }: Props) => {
  const [text, setText] = useState(INITIAL_SUMMARY)
  const [error, setError] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const localTrace = useRef(trace || createTimerInputTrace('summary'))
  const createdHere = useRef(!trace)

  const meaningfulText = (value: string) => value
    .split('\n')
    .map(line => line.replace(/^\s*(?:\d+\.\s*|[+•]\s*)/, '').trim())
    .join('')

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    if (createdHere.current) localTrace.current.mark('sheet.mount.requested')
    localTrace.current.mark('sheet.mount.completed')
    const stopLag = observeEventLoopLag(localTrace.current)
    const stopFocus = scheduleTimerInputFocus(textarea, INITIAL_SUMMARY.length, undefined, { report: (event, details) => localTrace.current.mark(event, details) })
    return () => { stopLag(); stopFocus() }
  }, [])

  const handleSave = useCallback(() => {
    const value = text.trim()
    const content = meaningfulText(value)
    if (isEarlyEnd && !content) {
      setError('请先填写提前结束原因')
      return
    }
    onSave(content ? value : '')
  }, [isEarlyEnd, text, onSave])

  const handleChange = useCallback((value: string) => {
    setText(value)
    if (error) setError('')
  }, [error])

  const handleEnterNumbering = useCallback((textarea: HTMLTextAreaElement) => {
    const cursorStart = textarea.selectionStart
    const cursorEnd = textarea.selectionEnd
    const beforeCursor = text.slice(0, cursorStart)
    const currentLine = beforeCursor.slice(beforeCursor.lastIndexOf('\n') + 1)
    const match = currentLine.match(/^\s*(\d+)\.\s/)
    if (!match) return false

    const nextNumber = Number(match[1]) + 1
    const insertion = `\n${nextNumber}. `
    const nextText = `${text.slice(0, cursorStart)}${insertion}${text.slice(cursorEnd)}`
    setText(nextText)
    if (error) setError('')

    const nextCursor = cursorStart + insertion.length
    window.setTimeout(() => {
      textarea.setSelectionRange(nextCursor, nextCursor)
    }, 0)
    return true
  }, [error, text])

  return (
    <BottomSheet open onClose={onClose}>
      <div className="space-y-3 p-4 font-sans">
        <h3 className="text-base font-bold text-gray-900">
          {isEarlyEnd ? '提前结束原因 / 失败原因' : '会话总结'}
        </h3>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={e => handleChange(e.target.value)}
          onKeyDown={e => {
            if (e.nativeEvent.isComposing || e.keyCode === 229) return
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
              e.preventDefault()
              handleSave()
            } else if (e.key === 'Enter' && !e.shiftKey && !e.altKey) {
              if (handleEnterNumbering(e.currentTarget)) {
                e.preventDefault()
              }
            }
          }}
          rows={4}
          placeholder={
            isEarlyEnd
              ? '这段时间为什么提前结束了？碰到了什么阻碍？'
              : '这次专注完成了什么？有什么收获？'
          }
          className="w-full resize-none rounded-xl border border-gray-200 px-3.5 py-2.5 text-sm leading-6 outline-none focus:border-blue-400"
        />
        {error ? <div className="text-sm font-medium text-red-500">{error}</div> : null}
        <div className="flex gap-2">
          <button onClick={onClose} className="flex-1 h-12 rounded-xl bg-gray-100 text-base font-semibold text-gray-500 hover:bg-gray-200 transition-all">取消</button>
          <button onClick={handleSave} className="flex-1 h-12 rounded-xl bg-blue-600 text-base font-semibold text-white active:bg-blue-700 transition-all shadow-md shadow-blue-100">保存</button>
        </div>
      </div>
    </BottomSheet>
  )
})

SessionSummarySheet.displayName = 'SessionSummarySheet'
