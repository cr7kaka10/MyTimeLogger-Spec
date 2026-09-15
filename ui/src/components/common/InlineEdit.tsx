// ui/src/components/common/InlineEdit.tsx
import { memo, useCallback, useEffect, useRef, useState } from 'react'

interface InlineEditProps {
  value: string
  onSave: (v: string) => void
  type?: 'text' | 'password'
  placeholder?: string
}

export const InlineEdit = memo(({ value, onSave, type = 'text', placeholder }: InlineEditProps) => {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus()
  }, [editing])

  const save = useCallback(() => {
    if (draft !== value) onSave(draft)
    setEditing(false)
  }, [draft, value, onSave])

  const cancel = useCallback(() => {
    setDraft(value)
    setEditing(false)
  }, [value])

  if (editing) {
    return (
      <input
        ref={inputRef}
        type={type}
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancel() }}
        placeholder={placeholder}
        className="w-full rounded-md border border-blue-300 bg-transparent px-2 py-1 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-200"
      />
    )
  }

  return (
    <button type="button" onClick={() => setEditing(true)} className="text-right text-sm text-gray-400 active:text-blue-600">
      {value ? (type === 'password' ? '••••••••' : value) : (placeholder || '未设置')}
    </button>
  )
})

InlineEdit.displayName = 'InlineEdit'
