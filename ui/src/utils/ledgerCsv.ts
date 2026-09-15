import type { LedgerEntry, LedgerFilter } from '../types'
import { ledgerSourceName, parseLedgerDisplay } from './ledgerDisplay'

const BOM = '\uFEFF'
const HEADERS = ['业务日期', '发生时间', '类型', '标题', '说明', '收入', '支出', '净额', '来源类型', '来源 ID', '流水 ID', '创建时间']
const FILTER_NAMES: Record<LedgerFilter, string> = { all: '全部', income: '收入', expense: '支出', reward: '兑换' }
const safeText = (value: unknown): string => {
  let text = value == null ? '' : String(value)
  if (/^\s*[=+\-@]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}
const numberText = (value: number): string => Number.isFinite(value) ? String(value) : ''

export const buildLedgerCsv = (entries: LedgerEntry[]): string => {
  const rows = entries.map(entry => {
    const amount = Number(entry.amount)
    const date = entry.target_date || (entry.occurred_at || entry.created_at || '').slice(0, 10)
    const display = parseLedgerDisplay(entry)
    return [date, entry.occurred_at || '', ledgerSourceName(entry.source_type),
      display.title, entry.description || '',
      amount > 0 ? numberText(amount) : '', amount < 0 ? numberText(-amount) : '', numberText(amount),
      ledgerSourceName(entry.source_type), entry.source_id ?? '', entry.id, entry.created_at || '']
      .map((value, index) => index >= 5 && index <= 7 ? String(value) : safeText(value)).join(',')
  })
  return `${BOM}${HEADERS.join(',')}\r\n${rows.join('\r\n')}${rows.length ? '\r\n' : ''}`
}

export const ledgerCsvFilename = (filter: LedgerFilter, now = new Date()): string => {
  const values = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(now).map(part => [part.type, part.value]))
  return `MyTimeLogger-金币流水-${FILTER_NAMES[filter]}-${values.year}${values.month}${values.day}-${values.hour}${values.minute}${values.second}.csv`
}
