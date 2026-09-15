// ui/src/components/Sleep/SleepPage.tsx
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { SleepData } from '../../types'
import { SleepAutoScorePanel } from './SleepAutoScorePanel'
import type { UseSleepReturn } from '../../hooks/useSleep'
import { EmptyState } from '../common/EmptyState'
import { SleepTrendChart } from './SleepTrendChart'
import { WeekCalendar } from '../../pages/UnifiedChecklistPage/WeekCalendar'
import { BottomSheet } from '../common/BottomSheet'
import { applySleepReportHeadingAnchors, extractSleepReportOutline } from './sleepReportOutline'
import { hasSleepSourceEvidence } from '../../utils/sleepSourceStatus'
import { selectSleepReportSource } from './sleepReportSource'

interface SleepPageProps extends UseSleepReturn {
  onSelectSleepDate?: (date: string) => void
  onPickImage?: (file: File) => Promise<void>
  onSleepAnalysis?: () => void
  onFullAnalysis?: () => void
  onForceRefresh?: () => void
}

type DiaryType = 'morning' | 'evening'
type MarkdownTable = { headers: string[]; rows: string[][] }
export const EVENING_DIARY_TEMPLATE = '今天满意的三件事：\n1. '
export const diaryInitialValue = (title: string, value: string) => value || (title === '晚间日记' ? EVENING_DIARY_TEMPLATE : '1. ')
export const continueDiaryNumbering = (value: string, cursorStart: number, cursorEnd: number) => {
  const beforeCursor = value.slice(0, cursorStart)
  const currentLine = beforeCursor.slice(beforeCursor.lastIndexOf('\n') + 1)
  const match = currentLine.match(/^\s*(\d+)\.\s/)
  if (!match) return null
  const insertion = `\n${Number(match[1]) + 1}. `
  return {
    value: `${value.slice(0, cursorStart)}${insertion}${value.slice(cursorEnd)}`,
    cursor: cursorStart + insertion.length,
  }
}

function parseInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = []
  let currentText = text
  let key = 0

  while (currentText) {
    const boldIndex = currentText.indexOf('**')
    const codeIndex = currentText.indexOf('`')
    const emphasisMatch = currentText.match(/(^|[^*])\*([^*\n]+)\*/)
    const emphasisIndex = emphasisMatch?.index === undefined ? -1 : emphasisMatch.index + emphasisMatch[1].length

    if (boldIndex === -1 && codeIndex === -1 && emphasisIndex === -1) {
      parts.push(currentText)
      break
    }

    if (boldIndex !== -1 && (codeIndex === -1 || boldIndex < codeIndex)) {
      if (boldIndex > 0) {
        parts.push(currentText.substring(0, boldIndex))
      }
      const nextBold = currentText.indexOf('**', boldIndex + 2)
      if (nextBold !== -1) {
        parts.push(<strong key={key++} className="font-bold text-gray-800">{currentText.substring(boldIndex + 2, nextBold)}</strong>)
        currentText = currentText.substring(nextBold + 2)
      } else {
        parts.push(currentText.substring(boldIndex))
        break
      }
    } else if (emphasisIndex !== -1 && (codeIndex === -1 || emphasisIndex < codeIndex)) {
      if (emphasisIndex > 0) {
        parts.push(currentText.substring(0, emphasisIndex))
      }
      const nextEmphasis = currentText.indexOf('*', emphasisIndex + 1)
      if (nextEmphasis !== -1) {
        parts.push(<em key={key++} className="font-medium italic text-gray-700">{currentText.substring(emphasisIndex + 1, nextEmphasis)}</em>)
        currentText = currentText.substring(nextEmphasis + 1)
      } else {
        parts.push(currentText.substring(emphasisIndex))
        break
      }
    } else {
      if (codeIndex > 0) {
        parts.push(currentText.substring(0, codeIndex))
      }
      const nextCode = currentText.indexOf('`', codeIndex + 1)
      if (nextCode !== -1) {
        parts.push(<code key={key++} className="rounded bg-gray-50 px-1 py-0.5 font-mono text-xs text-red-500">{currentText.substring(codeIndex + 1, nextCode)}</code>)
        currentText = currentText.substring(nextCode + 1)
      } else {
        parts.push(currentText.substring(codeIndex))
        break
      }
    }
  }

  return parts
}

function splitTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
}

function isTableDivider(line: string): boolean {
  const cells = splitTableRow(line)
  return cells.length > 1 && cells.every(cell => /^:?-{3,}:?$/.test(cell))
}

function isTableLine(line: string): boolean {
  const trimmed = line.trim()
  return trimmed.startsWith('|') && trimmed.endsWith('|') && splitTableRow(trimmed).length > 1
}

function parseTable(lines: string[]): MarkdownTable | null {
  if (lines.length < 2) return null
  if (!isTableDivider(lines[1])) {
    return lines.length > 1 ? { headers: splitTableRow(lines[0]), rows: lines.slice(1).map(splitTableRow) } : null
  }
  return {
    headers: splitTableRow(lines[0]),
    rows: lines.slice(2).filter(line => !isTableDivider(line)).map(splitTableRow),
  }
}

function compactText(value: string | undefined): string {
  const text = (value || '').trim()
  return !text || /^none|null|无|-$/.test(text.toLowerCase()) ? '' : text
}

function tableKind(table: MarkdownTable): 'metrics' | 'records' | 'generic' {
  const headers = table.headers.join(' ')
  if (/指标/.test(headers) && /(当前值|区间评价|趋势评价)/.test(headers)) return 'metrics'
  if (/(类别|时间段)/.test(headers) && /(时长|备注|#)/.test(headers)) return 'records'
  return 'generic'
}

function renderMetricsTable(table: MarkdownTable, key: string): React.ReactNode {
  const headers = table.headers
  const idxMetric = Math.max(headers.findIndex(header => /指标/.test(header)), 0)
  const idxValue = headers.findIndex(header => /当前值|数值|值/.test(header))
  const idxTrend = headers.findIndex(header => /趋势|较上次|变化/.test(header))
  const idxEval = headers.findIndex(header => /评价|区间/.test(header))
  return (
    <div key={key} className="my-2 divide-y divide-gray-100 rounded-lg border border-gray-100 bg-white text-[12px] shadow-sm">
      {table.rows.map((row, index) => {
        const trend = compactText(row[idxTrend])
        const evaluation = compactText(row[idxEval])
        return (
          <div key={index} className="grid gap-1.5 px-2.5 py-1.5 sm:grid-cols-[minmax(90px,140px)_1fr_auto] sm:items-center">
            <div className="font-semibold text-gray-800">{parseInline(compactText(row[idxMetric]))}</div>
            <div className="min-w-0 text-gray-700">
              <span className="font-medium text-gray-900">{parseInline(compactText(row[idxValue]) || '--')}</span>
              {trend && <span className="ml-0 block text-[11px] text-gray-500 sm:ml-2 sm:inline">{parseInline(trend)}</span>}
            </div>
            {evaluation && (
              <span className="w-fit rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-700">
                {parseInline(evaluation)}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function renderRecordsTable(table: MarkdownTable, key: string): React.ReactNode {
  const headers = table.headers
  const idxNo = Math.max(headers.findIndex(header => /^#|序号/.test(header)), 0)
  const idxCategory = headers.findIndex(header => /类别/.test(header))
  const idxRange = headers.findIndex(header => /时间段/.test(header))
  const idxDuration = headers.findIndex(header => /时长/.test(header))
  const idxNote = headers.findIndex(header => /备注/.test(header))
  return (
    <div key={key} className="my-2 overflow-x-auto rounded-lg border border-gray-100 bg-white shadow-sm">
      <table className="min-w-full border-collapse text-left text-[12px] leading-5 text-gray-700">
        <thead className="bg-gray-50 text-[11px] font-semibold text-gray-500">
          <tr>
            {['#', '类别', '时间段', '时长', '备注'].map(header => (
              <th key={header} className="whitespace-nowrap px-2 py-1">{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, index) => {
            const note = compactText(row[idxNote])
            return (
              <tr key={index} className="border-t border-gray-50">
                <td className="whitespace-nowrap px-2 py-1 font-mono text-[11px] text-gray-400">{compactText(row[idxNo]) || index + 1}</td>
                <td className="whitespace-nowrap px-2 py-1 font-semibold text-gray-800">{parseInline(compactText(row[idxCategory]) || '--')}</td>
                <td className="whitespace-nowrap px-2 py-1 font-mono text-[11px] text-gray-700">{parseInline(compactText(row[idxRange]) || '--')}</td>
                <td className="whitespace-nowrap px-2 py-1 font-mono text-[11px] font-semibold text-gray-900">{parseInline(compactText(row[idxDuration]) || '--')}</td>
                <td className="whitespace-nowrap px-2 py-1 text-[11px] text-gray-500">{parseInline(note || '--')}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function renderGenericTable(table: MarkdownTable, key: string): React.ReactNode {
  return (
    <div key={key} className="my-2 overflow-x-auto rounded-lg border border-gray-100 bg-white shadow-sm">
      <table className="min-w-full border-collapse text-left text-[12px] leading-5 text-gray-700">
        <thead className="bg-gray-50 text-[11px] font-semibold text-gray-500">
          <tr>{table.headers.map((header, index) => <th key={index} className="whitespace-nowrap px-2 py-1">{parseInline(header)}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-gray-50">
              {table.headers.map((_, cellIndex) => (
                <td key={cellIndex} className="whitespace-nowrap px-2 py-1">{parseInline(compactText(row[cellIndex]) || '--')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function renderTable(table: MarkdownTable, key: string): React.ReactNode {
  const kind = tableKind(table)
  if (kind === 'metrics') return renderMetricsTable(table, key)
  if (kind === 'records') return renderRecordsTable(table, key)
  return renderGenericTable(table, key)
}

function sanitizeReportHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '')
    .replace(/\son\w+="[^"]*"/gi, '')
    .replace(/\son\w+='[^']*'/gi, '')
    .replace(/\s(?:href|src)=["']javascript:[^"']*["']/gi, '')
}

function stripReportHeaderMarkdown(markdown: string): string {
  const lines = markdown.split('\n')
  let idx = 0
  if (lines[idx]?.trim().startsWith('# ')) idx += 1
  while (idx < lines.length && !lines[idx].trim()) idx += 1
  if (lines[idx]?.trim().startsWith('>') && lines[idx].includes('生成时间')) idx += 1
  while (idx < lines.length && !lines[idx].trim()) idx += 1
  if (lines[idx]?.trim() === '---') idx += 1
  while (idx < lines.length && !lines[idx].trim()) idx += 1
  return lines.slice(idx).join('\n')
}

function stripReportHeaderHtml(html: string): string {
  return html
    .replace(/^\s*<h1[\s\S]*?<\/h1>\s*/i, '')
    .replace(/^\s*<blockquote[\s\S]*?生成时间[\s\S]*?<\/blockquote>\s*/i, '')
    .replace(/^\s*<hr\s*\/?>\s*/i, '')
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function diaryMarkdownToHtml(value: string): string {
  const lines = escapeHtml(value.trim()).split('\n')
  const html: string[] = []
  let listOpen = false

  const closeList = () => {
    if (listOpen) {
      html.push('</ul>')
      listOpen = false
    }
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      closeList()
      continue
    }
    const inline = trimmed
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    const heading = inline.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      closeList()
      const level = Math.min(heading[1].length + 2, 6)
      html.push(`<h${level}>${heading[2]}</h${level}>`)
      continue
    }
    const bullet = inline.match(/^[-+*]\s+(.+)$/)
    if (bullet) {
      if (!listOpen) {
        html.push('<ul>')
        listOpen = true
      }
      html.push(`<li>${bullet[1]}</li>`)
      continue
    }
    closeList()
    html.push(`<p>${inline}</p>`)
  }
  closeList()
  return html.join('')
}

function injectDiaryButtonsHtml(html: string, morning: string, evening: string): string {
  const replaceBlock = (input: string, type: DiaryType, value: string, emptyText: string) => {
    const headingPattern = type === 'morning' ? '晨间日记' : '(晚间复盘|晚间日记)'
    const pattern = new RegExp(`(<h3[^>]*>[^<]*${headingPattern}[^<]*<\\/h3>\\s*)(<blockquote[\\s\\S]*?<\\/blockquote>)?`, 'i')
    const text = diaryMarkdownToHtml(value.trim() || emptyText)
    const button = `<div role="button" tabindex="0" data-diary-edit="${type}" class="sleep-diary-edit">${text}</div>`
    return input.replace(pattern, `$1${button}`)
  }
  return replaceBlock(
    replaceBlock(html, 'morning', morning, '今日未记录晨间日记'),
    'evening',
    evening,
    '今日未记录晚间复盘',
  )
}

function replaceDiaryBlocks(text: string, morning: string, evening: string): string {
  const lines = text.split('\n')
  const out: string[] = []
  for (let idx = 0; idx < lines.length; idx += 1) {
    const line = lines[idx]
    const trimmed = line.trim()
    const isMorning = /^###\s+.*晨间日记/.test(trimmed)
    const isEvening = /^###\s+.*(晚间复盘|晚间日记)/.test(trimmed)
    if (!isMorning && !isEvening) {
      out.push(line)
      continue
    }

    out.push(line)
    while (idx + 1 < lines.length && !lines[idx + 1].trim()) {
      out.push(lines[idx + 1])
      idx += 1
    }
    if (idx + 1 < lines.length && lines[idx + 1].trim().startsWith('>')) {
      idx += 1
      while (idx + 1 < lines.length && lines[idx + 1].trim().startsWith('>')) {
        idx += 1
      }
    }
    const value = isMorning ? morning : evening
    out.push(`> ${value.trim() || (isMorning ? '今日未记录晨间日记' : '今日未记录晚间复盘')}`)
  }
  return out.join('\n')
}

function renderMarkdown(text: string, onDiaryEdit?: (type: DiaryType) => void): React.ReactNode {
  if (!text) return null
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let codeLines: string[] = []
  let inCodeBlock = false
  let pendingDiaryType: DiaryType | null = null
  const outline = extractSleepReportOutline(text, 'markdown')
  let outlineIndex = 0

  const flushCode = (idx: number) => {
    if (!codeLines.length) return
    nodes.push(
      <pre key={`code-${idx}`} className="my-3 overflow-x-auto rounded-lg bg-gray-50 p-3 text-[13px] leading-6 text-gray-600">
        <code>{codeLines.join('\n')}</code>
      </pre>,
    )
    codeLines = []
  }

  for (let idx = 0; idx < lines.length; idx += 1) {
    const line = lines[idx]
    const trimmed = line.trim()
    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        flushCode(idx)
        inCodeBlock = false
      } else {
        inCodeBlock = true
        codeLines = []
      }
      continue
    }

    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }

    if (isTableLine(trimmed)) {
      const tableLines = [trimmed]
      while (idx + 1 < lines.length && isTableLine(lines[idx + 1])) {
        idx += 1
        tableLines.push(lines[idx].trim())
      }
      const table = parseTable(tableLines)
      if (table) {
        nodes.push(renderTable(table, `table-${idx}`))
        continue
      }
      if (/^\|\s*#?\s*\|/.test(trimmed) || /详细时间记录|时间段|备注/.test(trimmed)) continue
      nodes.push(
        <p key={idx} className="my-1 text-[14px] leading-6">
          {parseInline(trimmed)}
        </p>,
      )
      continue
    }

    if (!trimmed) {
      nodes.push(<div key={idx} className="h-1" />)
      continue
    }

    if (trimmed === '---' || trimmed === '***') {
      nodes.push(<hr key={idx} className="my-2 border-gray-100" />)
      continue
    }

    if (trimmed.startsWith('>')) {
      if (pendingDiaryType && onDiaryEdit) {
        const type = pendingDiaryType
        pendingDiaryType = null
        nodes.push(
          <button
            key={idx}
            type="button"
            onClick={() => onDiaryEdit(type)}
            className="my-3 block w-full rounded-lg border-l-4 border-rose-200 bg-rose-50/70 px-4 py-3 text-left text-[14px] leading-7 text-gray-700 active:bg-rose-100"
          >
            {parseInline(trimmed.replace(/^>\s?/, ''))}
          </button>,
        )
        continue
      }
      nodes.push(
        <blockquote key={idx} className="my-2 rounded-lg border-l-4 border-blue-100 bg-blue-50/50 px-3 py-2 text-[14px] leading-6 text-gray-700">
          {parseInline(trimmed.replace(/^>\s?/, ''))}
        </blockquote>,
      )
      continue
    }

    if (trimmed.startsWith('# ')) {
      nodes.push(<h1 id={outline[outlineIndex++]?.anchor} key={idx} className="mt-3 mb-2 text-[18px] font-bold leading-7 text-gray-900">{parseInline(trimmed.slice(2))}</h1>)
      continue
    }
    if (trimmed.startsWith('## ')) {
      nodes.push(<h2 id={outline[outlineIndex++]?.anchor} key={idx} className="mt-4 mb-2 border-t border-gray-100 pt-3 text-[16px] font-bold leading-7 text-gray-900">{parseInline(trimmed.slice(3))}</h2>)
      continue
    }
    if (trimmed.startsWith('### ')) {
      if (/晨间日记/.test(trimmed)) pendingDiaryType = 'morning'
      if (/晚间复盘|晚间日记/.test(trimmed)) pendingDiaryType = 'evening'
      nodes.push(<h3 id={outline[outlineIndex++]?.anchor} key={idx} className="mt-3 mb-1.5 text-[14px] font-bold leading-6 text-gray-800">{parseInline(trimmed.slice(4))}</h3>)
      continue
    }
    if (trimmed.startsWith('#### ')) {
      nodes.push(<h4 id={outline[outlineIndex++]?.anchor} key={idx} className="mt-2.5 mb-1 text-[14px] font-semibold leading-6 text-gray-800">{parseInline(trimmed.slice(5))}</h4>)
      continue
    }

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      nodes.push(
        <ul key={idx} className="my-1.5 list-disc pl-5 text-[14px] leading-6">
          <li>{parseInline(trimmed.slice(2))}</li>
        </ul>,
      )
      continue
    }

    const orderedListMatch = trimmed.match(/^(\d+)\.\s+(.+)$/)
    if (orderedListMatch) {
      nodes.push(
        <ol key={idx} className="my-1.5 list-decimal pl-5 text-[14px] leading-6" start={Number(orderedListMatch[1])}>
          <li>{parseInline(orderedListMatch[2])}</li>
        </ol>,
      )
      continue
    }

    nodes.push(
      <p key={idx} className="my-1.5 text-[14px] leading-6">
        {parseInline(trimmed)}
      </p>,
    )
  }

  flushCode(lines.length)
  return (
    <div className="space-y-1 text-[14px] leading-6 text-gray-700">
      {nodes}
    </div>
  )
}

const DiaryModal = memo(({ title, value, onChange, onClose, onSave }: {
  title: string
  value: string
  onChange: (value: string) => void
  onClose: () => void
  onSave: () => void
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const textValue = diaryInitialValue(title, value)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    const cursor = textValue.length
    const focusTimer = window.setTimeout(() => {
      textarea.focus()
      textarea.setSelectionRange(cursor, cursor)
    }, 0)
    return () => window.clearTimeout(focusTimer)
  }, [title])

  const handleEnterNumbering = useCallback((textarea: HTMLTextAreaElement) => {
    const cursorStart = textarea.selectionStart
    const cursorEnd = textarea.selectionEnd
    const next = continueDiaryNumbering(textValue, cursorStart, cursorEnd)
    if (!next) return false
    onChange(next.value)
    window.setTimeout(() => {
      textarea.setSelectionRange(next.cursor, next.cursor)
    }, 0)
    return true
  }, [onChange, textValue])

  return (
    <BottomSheet open onClose={onClose}>
      <div className="space-y-3 p-4 font-sans">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-gray-900">{title}</h3>
          <button type="button" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 text-base font-bold text-gray-400">×</button>
        </div>
        <textarea
          ref={textareaRef}
          value={textValue}
          onChange={event => onChange(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
              event.preventDefault()
              onSave()
            } else if (event.key === 'Enter' && !event.shiftKey && !event.altKey) {
              if (handleEnterNumbering(event.currentTarget)) {
                event.preventDefault()
              }
            }
          }}
          rows={10}
          placeholder={title === '晨间日记' ? '今天起床后的状态、计划、风险点。' : '今晚复盘一下完成情况、问题和明天调整。'}
          className="w-full resize-none rounded-xl border border-gray-200 px-3.5 py-2.5 text-sm leading-6 outline-none focus:border-blue-400"
          autoFocus
        />
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className="h-12 flex-1 rounded-xl bg-gray-100 text-base font-semibold text-gray-500 transition-all hover:bg-gray-200">取消</button>
          <button type="button" onClick={onSave} className="h-12 flex-1 rounded-xl bg-blue-600 text-base font-semibold text-white shadow-md shadow-blue-100 transition-all active:bg-blue-700">保存</button>
        </div>
      </div>
    </BottomSheet>
  )
})

DiaryModal.displayName = 'DiaryModal'

const ReportContent = memo(({ data, onSaveDiary }: { data: SleepData; onSaveDiary: (type: DiaryType, text: string) => void }) => {
  const [editing, setEditing] = useState<DiaryType | null>(null)
  const [morning, setMorning] = useState(data.morning_diary || '')
  const [evening, setEvening] = useState(data.evening_diary || '')
  const reportSource = selectSleepReportSource(data)
  const hasHtml = reportSource.format === 'html'

  useEffect(() => {
    setMorning(data.morning_diary || '')
    setEvening(data.evening_diary || '')
  }, [data.date, data.morning_diary, data.evening_diary])

  const openDiary = (type: DiaryType) => setEditing(type)
  const saveCurrentDiary = () => {
    if (!editing) return
    const value = editing === 'morning' ? morning : evening
    onSaveDiary(editing, value)
    setEditing(null)
  }

  if (hasHtml) {
    const sourceHtml = stripReportHeaderHtml(sanitizeReportHtml(reportSource.source))
    const html = applySleepReportHeadingAnchors(injectDiaryButtonsHtml(sourceHtml, morning, evening), extractSleepReportOutline(sourceHtml, 'html'))
    return (
      <>
        <div
          className="sleep-report max-w-none text-[15px] leading-7 text-gray-700
          [&_h1]:mt-3 [&_h1]:mb-2 [&_h1]:text-[22px] [&_h1]:font-bold [&_h1]:leading-8 [&_h1]:text-gray-900
          [&_h2]:mt-5 [&_h2]:mb-2 [&_h2]:border-t [&_h2]:border-gray-100 [&_h2]:pt-4 [&_h2]:text-[19px] [&_h2]:font-bold [&_h2]:leading-8 [&_h2]:text-gray-900
          [&_h3]:mt-4 [&_h3]:mb-2 [&_h3]:text-[17px] [&_h3]:font-bold [&_h3]:leading-7 [&_h3]:text-gray-900
          [&_h4]:mt-3 [&_h4]:mb-1.5 [&_h4]:text-[15px] [&_h4]:font-semibold [&_h4]:leading-7 [&_h4]:text-gray-800
          [&_p]:my-2 [&_p]:text-[15px] [&_p]:leading-7 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5 [&_li]:my-0 [&_li]:text-[15px] [&_li]:leading-7
          [&_blockquote]:my-2 [&_blockquote]:rounded-lg [&_blockquote]:border-l-4 [&_blockquote]:border-blue-100 [&_blockquote]:bg-blue-50/50 [&_blockquote]:px-3 [&_blockquote]:py-2 [&_blockquote]:text-[15px] [&_blockquote]:leading-7
          [&_.sleep-diary-edit]:my-3 [&_.sleep-diary-edit]:block [&_.sleep-diary-edit]:w-full [&_.sleep-diary-edit]:rounded-lg [&_.sleep-diary-edit]:border-l-4 [&_.sleep-diary-edit]:border-rose-200 [&_.sleep-diary-edit]:bg-rose-50/70 [&_.sleep-diary-edit]:px-4 [&_.sleep-diary-edit]:py-3 [&_.sleep-diary-edit]:text-left [&_.sleep-diary-edit]:text-[15px] [&_.sleep-diary-edit]:leading-7 [&_.sleep-diary-edit]:text-gray-700 [&_.sleep-diary-edit_p]:my-1 [&_.sleep-diary-edit_ul]:my-1 [&_.sleep-diary-edit_ul]:list-disc [&_.sleep-diary-edit_ul]:pl-5
          [&_table]:my-2 [&_table]:block [&_table]:w-full [&_table]:overflow-x-auto [&_table]:rounded-lg [&_table]:border [&_table]:border-gray-100 [&_table]:text-[15px] [&_table]:leading-7 [&_th]:whitespace-nowrap [&_th]:bg-gray-50 [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left [&_td]:whitespace-nowrap [&_td]:border-t [&_td]:border-gray-50 [&_td]:px-2 [&_td]:py-1.5
          [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-gray-50 [&_pre]:p-3 [&_pre]:text-[14px] [&_pre]:leading-6 [&_pre]:text-gray-600
          [&_hr]:my-2 [&_hr]:border-gray-100"
          onClickCapture={event => {
            const target = event.target as HTMLElement
            const button = target.closest<HTMLButtonElement>('[data-diary-edit]')
            const type = button?.dataset.diaryEdit
            if (type === 'morning' || type === 'evening') openDiary(type)
          }}
          dangerouslySetInnerHTML={{ __html: html }}
        />
        {editing && (
          <DiaryModal
            title={editing === 'morning' ? '晨间日记' : '晚间日记'}
            value={editing === 'morning' ? morning : evening}
            onChange={editing === 'morning' ? setMorning : setEvening}
            onClose={() => setEditing(null)}
            onSave={saveCurrentDiary}
          />
        )}
      </>
    )
  }
  const report = stripReportHeaderMarkdown(replaceDiaryBlocks(reportSource.source, morning, evening))
  return (
    <>
      {renderMarkdown(report, openDiary)}
      {editing && (
        <DiaryModal
          title={editing === 'morning' ? '晨间日记' : '晚间日记'}
          value={editing === 'morning' ? morning : evening}
          onChange={editing === 'morning' ? setMorning : setEvening}
          onClose={() => setEditing(null)}
          onSave={saveCurrentDiary}
        />
      )}
    </>
  )
})

ReportContent.displayName = 'ReportContent'

const formatMinutes = (minutes = 0): string => `${Math.floor(minutes / 60)}h${minutes % 60}m`

const DiaryRewardState = ({ value, type, label }: { value: any; type: 'morning' | 'evening'; label: string }) => {
  const completed = value[`${type}_diary_reward_status`] === 'completed'
  return <p className={`mt-2 font-medium ${completed ? 'text-emerald-700' : 'text-amber-700'}`}>{completed ? `${label}日记奖励 +${value[`${type}_diary_reward_amount`] || 0} 金币` : `${label}日记奖励待完成：${value[`${type}_diary_reward_reason`] || `${label}日记尚未完成`}`}</p>
}

const SleepStatsGrid = memo(({ data }: { data: SleepData }) => {
  const metrics = [
    { label: '睡眠周期', value: data.sleep_cycles !== undefined ? `${data.sleep_cycles} 次` : '--', highlight: true },
    { label: '深睡时长', value: data.deep_sleep_min ? formatMinutes(data.deep_sleep_min) : '--', highlight: true },
    { label: '清醒时长', value: data.awake_min !== undefined ? `${data.awake_min}m` : '--', highlight: true },
    { label: '清醒次数', value: data.awake_count !== undefined ? `${data.awake_count} 次` : '--', highlight: true },
    { label: '入睡用时', value: data.fall_asleep_min !== undefined ? `${data.fall_asleep_min}m` : '--', highlight: true },
    { label: '起床用时', value: data.wake_up_min !== undefined ? `${data.wake_up_min}m` : '--', highlight: true },
    { label: '上床时间', value: data.atm_sleep_start || '--' },
    { label: '入睡时间', value: data.sleep_start || '--' },
    { label: '醒来时间', value: data.sleep_end || '--' },
    { label: '下床时间', value: data.atm_sleep_end || '--' },
  ]

  return (
    <div className="grid grid-cols-2 gap-2.5">
      {metrics.map(m => (
        <div key={m.label} className={m.highlight ? "rounded-xl border border-red-200 bg-red-50 p-3 text-center shadow-sm dark:border-red-900/70 dark:bg-red-950/45" : "rounded-xl border border-gray-100 bg-white p-3 shadow-sm text-center dark:border-gray-700 dark:bg-gray-900"}>
          <div className={m.highlight ? "text-[10px] font-bold text-red-700 tracking-wide dark:text-red-200" : "text-[10px] font-bold text-gray-500 tracking-wide dark:text-gray-300"}>{m.label}</div>
          <div className={m.highlight ? "mt-1 text-[15px] font-bold text-gray-900 dark:text-red-50" : "mt-1 text-[13px] font-semibold text-gray-900 dark:text-gray-100"}>{m.value}</div>
        </div>
      ))}
    </div>
  )
})

SleepStatsGrid.displayName = 'SleepStatsGrid'

const sourceLabels: Record<string, string> = {
  huawei_official: '官方同步',
  huawei_user_import: '用户导入',
  local_automation: '本机自动化',
  screenshot_ocr: '截图 OCR',
}

const formatTrackedDuration = (seconds = 0): string => `${Math.floor(seconds / 3600)}h${Math.floor((seconds % 3600) / 60)}m`

const SleepModuleStatus = memo(({ data, statusMessage }: { data?: SleepData | null; statusMessage?: string }) => (
  <section data-testid="sleep-module-status" className="rounded-xl border border-gray-100 bg-white p-3 text-xs text-gray-500">
    {statusMessage ? <span>{statusMessage}</span> : !data ? <span>等待睡眠数据同步</span> : !hasSleepSourceEvidence(data) ? <span>等待截图上传</span> : <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-gray-700">{sourceLabels[data.source || 'screenshot_ocr'] || data.source || '未知来源'}</span>
        <span>{data.sync_status === 'error' ? '同步失败' : '已同步'}</span>
        {Number(data.report_status || 0) >= 1 && <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">睡眠报告已生成</span>}
        {Number(data.report_status || 0) >= 2 && data.full_report_state === 'generated' && selectSleepReportSource(data).isComplete && <span className="rounded-full bg-blue-50 px-2 py-0.5 font-medium text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">完整报告已生成</span>}
        {data.full_report_state === 'insufficient_time_records' && <span className="rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-700 dark:bg-amber-950/50 dark:text-amber-300">时间记录过少（已记录 {formatTrackedDuration(data.tracked_duration_seconds)}）</span>}
        {data.synced_at && <span>{data.synced_at}</span>}
      </div>
      {data.sync_error && <div className="mt-2 text-red-500">{data.sync_error}</div>}
    </>}
  </section>
))
SleepModuleStatus.displayName = 'SleepModuleStatus'

export const SleepPage = memo(({ sleepData, selectedDate, setSelectedDate, saveDiary, sleepHistory, onSelectSleepDate, onPickImage, onSleepAnalysis, onFullAnalysis, onForceRefresh, statusMessage, uploadMessage }: SleepPageProps) => {
  const imageInputRef = useRef<HTMLInputElement>(null)
  const reportReaderContentRef = useRef<HTMLDivElement>(null)
  const [isReportReaderOpen, setIsReportReaderOpen] = useState(false)
  const reportOutline = useMemo(() => {
    if (!sleepData) return []
    const reportSource = selectSleepReportSource(sleepData)
    return extractSleepReportOutline(reportSource.source, reportSource.format)
  }, [sleepData?.analysis_html, sleepData?.analysis_report])
  useEffect(() => {
    if (!isReportReaderOpen) return
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setIsReportReaderOpen(false) }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isReportReaderOpen])
  const calendarDate = useMemo(() => {
    const [year, month, day] = selectedDate.split('-').map(Number)
    return new Date(year, month - 1, day)
  }, [selectedDate])
  const markedSleepDates = useMemo(() => new Set(sleepHistory.map(item => item.date)), [sleepHistory])
  const handleCalendarSelect = useCallback((d: Date) => {
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    ;(onSelectSleepDate || setSelectedDate)(value)
  }, [onSelectSleepDate, setSelectedDate])

  return (
    <div className="theme-page min-h-full">
      <div className="px-6 pb-2 pt-4">
        <WeekCalendar selectedDate={calendarDate} onDateSelect={handleCalendarSelect} markedDates={markedSleepDates} />
      </div>
      <div className="space-y-4 p-6">
        <SleepModuleStatus data={sleepData} statusMessage={statusMessage} />
        {/* PC 版操作按钮：始终显示，调用服务端睡眠分析服务 */}
        <div className="grid grid-cols-4 gap-2 font-sans">
          <input ref={imageInputRef} type="file" accept="image/*" className="hidden" onChange={async event => {
            const input = event.currentTarget
            const file = input.files?.[0]
            if (!file) return
            try {
              await onPickImage?.(file)
            } finally {
              input.value = ''
            }
          }} />
          <button type="button" onClick={() => imageInputRef.current?.click()}
            className="h-10 rounded-xl bg-blue-50 dark:bg-gray-800 px-1 text-xs font-semibold text-blue-600 dark:text-blue-400 active:bg-blue-100 dark:active:bg-gray-700">
            📸 上传图片
          </button>
          <button type="button" onClick={onSleepAnalysis}
            className="h-10 rounded-xl bg-blue-50 dark:bg-gray-800 px-1 text-xs font-semibold text-blue-600 dark:text-blue-400 active:bg-blue-100 dark:active:bg-gray-700">
            🌙 睡眠分析
          </button>
          <button type="button" onClick={onFullAnalysis}
            className="h-10 rounded-xl bg-blue-50 dark:bg-gray-800 px-1 text-xs font-semibold text-blue-600 dark:text-blue-400 active:bg-blue-100 dark:active:bg-gray-700">
            📄 完整分析
          </button>
          <button type="button" onClick={onForceRefresh}
            className="h-10 rounded-xl bg-orange-50 dark:bg-gray-800 px-1 text-xs font-semibold text-orange-600 dark:text-orange-400 active:bg-orange-100 dark:active:bg-gray-700">
            🔄 强制分析
          </button>
        </div>
        {uploadMessage && (
          <div className="-mt-2 text-center text-xs text-green-600">{uploadMessage}</div>
        )}

        {statusMessage && (
          <div className="rounded-xl bg-blue-50/50 p-3 text-xs text-blue-600 text-center animate-pulse">
            {statusMessage}
          </div>
        )}

        <SleepAutoScorePanel data={sleepData || { date: selectedDate }} />

        {!sleepData ? (
          <EmptyState icon="🌙" title="还没有睡眠数据" description="点击上方按钮上传截图或开始分析。" />
        ) : (
          <>
            {sleepData.score_settlement && <section data-testid="sleep-diary-reward-status" className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-3 text-sm"><DiaryRewardState value={sleepData.score_settlement} type="morning" label="晨间" /><DiaryRewardState value={sleepData.score_settlement} type="evening" label="晚间" /></section>}
            <SleepStatsGrid data={sleepData} />

            {/* 趋势图 */}
            {sleepHistory.length > 0 && (
              <section className="rounded-xl border border-gray-100 bg-white p-4">
                <h3 className="mb-2 text-sm font-semibold text-gray-700">📈 14 天趋势</h3>
                <SleepTrendChart data={sleepHistory} />
              </section>
            )}

            {(sleepData.analysis_html || sleepData.analysis_report) && (
              <section className="rounded-xl border border-gray-100 bg-white p-4">
                <div className="flex items-center justify-between gap-4 font-semibold text-gray-900">
                  <span>📊 AI 分析报告</span>
                  <button type="button" aria-label="全屏阅读睡眠报告" onClick={() => setIsReportReaderOpen(true)} className="hidden rounded-md px-2 py-1 text-xs font-medium text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-400 md:inline-flex">全屏</button>
                </div>
                <div className="mt-3"><ReportContent data={sleepData} onSaveDiary={saveDiary} /></div>
              </section>
            )}
          </>
        )}
      </div>
      {isReportReaderOpen && sleepData && (
        <div data-testid="sleep-report-reader" className="fixed inset-0 z-50 hidden bg-white/95 p-4 backdrop-blur-sm dark:bg-slate-950/95 md:block">
          <div className="mx-auto flex h-full max-w-7xl overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
            <nav aria-label="睡眠报告目录" className="w-64 shrink-0 overflow-y-auto border-r border-gray-100 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-950">
              <div className="mb-4 flex items-center justify-between"><span className="font-semibold text-slate-700 dark:text-slate-200">报告目录</span><button type="button" aria-label="缩小睡眠报告" onClick={() => setIsReportReaderOpen(false)} className="rounded px-2 py-1 text-xs text-slate-500 hover:bg-white hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-violet-400 dark:hover:bg-slate-800 dark:hover:text-white">缩小</button></div>
              {reportOutline.length ? <div className="space-y-1">{reportOutline.map(item => <button key={item.anchor} type="button" onClick={() => reportReaderContentRef.current?.querySelector<HTMLElement>(`#${item.anchor}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })} className="block w-full rounded px-2 py-1 text-left text-sm text-slate-600 hover:bg-white hover:text-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-400 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-violet-300" style={{ paddingLeft: `${(item.level - 1) * 12 + 8}px` }}>{item.title}</button>)}</div> : <p className="text-sm text-slate-500 dark:text-slate-400">此报告没有可用目录。</p>}
            </nav>
            <main ref={reportReaderContentRef} className="min-w-0 flex-1 overflow-y-auto p-8 text-gray-700 dark:text-slate-200"><div className="mx-auto max-w-4xl"><ReportContent data={sleepData} onSaveDiary={saveDiary} /></div></main>
          </div>
        </div>
      )}
    </div>
  )
})

SleepPage.displayName = 'SleepPage'
