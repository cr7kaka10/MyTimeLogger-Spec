// ui/src/components/common/MarkdownInput.tsx
import { memo, useCallback, useRef } from 'react'

interface Props {
  value: string
  onChange: (val: string) => void
  placeholder?: string
  onSubmit?: () => void
  onBlur?: () => void
  className?: string
  rows?: number
  autoFocus?: boolean
}

export const MarkdownInput = memo(({ value, onChange, placeholder, onSubmit, onBlur, className, rows = 4, autoFocus = false }: Props) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const el = textareaRef.current
    if (!el) return

    // Ctrl+Enter or Cmd+Enter to submit
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      onSubmit?.()
      return
    }

    // Auto list conversion on Enter
    if (e.key === 'Enter' && !e.shiftKey) {
      const selectionStart = el.selectionStart
      const selectionEnd = el.selectionEnd
      const textBefore = value.substring(0, selectionStart)
      const textAfter = value.substring(selectionEnd)

      const lastLine = textBefore.substring(textBefore.lastIndexOf('\n') + 1)
      const listMatch = lastLine.match(/^(\s*[-*]\s+)/)

      if (listMatch) {
        e.preventDefault()
        const prefix = listMatch[1]

        // If user presses Enter on an empty list item (e.g. "- " with no content), clear that prefix and end list
        if (lastLine.trim() === '-' || lastLine.trim() === '*') {
          const lineStart = textBefore.lastIndexOf('\n') + 1
          const newValue = value.substring(0, lineStart) + textAfter
          onChange(newValue)

          setTimeout(() => {
            if (textareaRef.current) {
              textareaRef.current.selectionStart = textareaRef.current.selectionEnd = lineStart
            }
          }, 0)
        } else {
          const insertText = '\n' + prefix
          const newValue = textBefore + insertText + textAfter
          onChange(newValue)

          setTimeout(() => {
            if (textareaRef.current) {
              textareaRef.current.selectionStart = textareaRef.current.selectionEnd = selectionStart + insertText.length
            }
          }, 0)
        }
      }
    }
  }, [value, onChange, onSubmit])

  return (
    <textarea
      ref={textareaRef}
      value={value}
      onChange={e => onChange(e.target.value)}
      onKeyDown={handleKeyDown}
      onBlur={onBlur}
      placeholder={placeholder}
      className={className}
      rows={rows}
      autoFocus={autoFocus}
    />
  )
})

MarkdownInput.displayName = 'MarkdownInput'
