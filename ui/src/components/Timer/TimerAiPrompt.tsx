import { useEffect, useRef, useState } from 'react'

interface TimerAiPromptProps {
  available: boolean
  busy?: boolean
  error?: string
  focusRequest?: number
  onFocusHandled?: () => void
  onSubmit: (requestText: string) => Promise<string | undefined>
}

export function TimerAiPrompt({ available, busy = false, error = '', focusRequest = 0, onFocusHandled, onSubmit }: TimerAiPromptProps) {
  const [value, setValue] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const isBusy = busy || submitting
  const canSubmit = available && !isBusy && value.trim().length > 0

  const resizeInput = (input: HTMLTextAreaElement) => {
    input.style.height = '0px'
    input.style.height = `${Math.min(input.scrollHeight, 88)}px`
  }

  const submit = async () => {
    const requestText = value.trim()
    if (!requestText || !available || isBusy) return
    setSubmitting(true); setSubmitError('')
    try {
      const warning = await onSubmit(requestText)
      setValue('')
      inputRef.current?.style.setProperty('height', '0px')
      if (warning) setSubmitError(warning)
    } catch (cause: any) {
      setSubmitError(String(cause?.message || '闪念保存失败，请稍后重试'))
    } finally { setSubmitting(false) }
  }

  useEffect(() => {
    if (focusRequest <= 0 || !available || isBusy) return
    inputRef.current?.focus()
    onFocusHandled?.()
  }, [available, focusRequest, isBusy, onFocusHandled])

  return (
    <section className="mx-auto w-full max-w-2xl" aria-label="记录闪念">
      <div className="flex items-center gap-2 rounded-[1.15rem] border border-slate-200/90 bg-white/95 px-2.5 py-2 shadow-[0_5px_18px_rgba(37,99,235,0.08)] transition focus-within:border-blue-300 focus-within:shadow-[0_7px_22px_rgba(37,99,235,0.13)] dark:border-slate-700 dark:bg-slate-900/90 dark:shadow-none dark:focus-within:border-blue-700">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50 text-sm text-blue-600 dark:bg-blue-950/70 dark:text-blue-300" aria-hidden="true">✦</span>
        <textarea
          ref={inputRef}
          value={value}
          rows={1}
          disabled={isBusy}
          aria-label="输入闪念"
          placeholder="记录此刻闪念…"
          onChange={event => { setValue(event.target.value); setSubmitError(''); resizeInput(event.currentTarget) }}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault()
              void submit()
            }
          }}
          className="min-h-9 min-w-0 flex-1 resize-none overflow-y-auto bg-transparent px-0.5 py-1.5 text-sm leading-5 text-gray-900 outline-none placeholder:text-slate-400 disabled:cursor-wait disabled:opacity-60 dark:text-gray-100 dark:placeholder:text-slate-500"
        />
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => void submit()}
          aria-label="记录闪念"
          title="记录闪念"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-lg font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-white dark:disabled:bg-slate-700"
        >
          <span aria-hidden="true">↑</span>
        </button>
      </div>
      {!available ? <p className="mt-1.5 px-2 text-[11px] text-amber-700 dark:text-amber-300">连接服务端后可记录闪念</p> : null}
      {isBusy ? <p className="mt-1.5 px-2 text-[11px] text-blue-700 dark:text-blue-300" aria-live="polite">正在整理闪念…</p> : null}
      {error || submitError ? <p className="mt-1.5 break-words px-2 text-[11px] text-red-700 dark:text-red-300" role="alert">{error || submitError}</p> : null}
    </section>
  )
}
