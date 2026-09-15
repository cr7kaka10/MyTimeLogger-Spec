import { buildLedgerCsv, ledgerCsvFilename } from './ledgerCsv'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const csv = buildLedgerCsv([{
  id: 'row-1', amount: 0.5, source_type: 'habit_checkin', source_id: 'habit-1',
  display_title: '=晨练', description: '中文,"两行"\n完成', target_date: '2026-08-24',
  occurred_at: '2026-08-24 09:08:07', created_at: '2026-08-24 09:09:00',
}, {
  id: 'row-2', amount: -2, source_type: 'task_fail', description: '@延误', target_date: '2026-08-24',
}, {
  id: 'row-3', amount: -50, source_type: 'body_metric_deadline_penalty', description: '体重体脂逾期未填写（09:00）', target_date: '2026-08-24',
}, {
  id: 'row-4', amount: 0, source_type: 'future_internal_key', description: '', target_date: '2026-08-24',
}])

assert(csv.startsWith('\uFEFF业务日期,发生时间,类型,标题,说明,收入,支出,净额,来源类型,来源 ID,流水 ID,创建时间'), 'CSV must carry BOM and fixed columns')
assert(csv.includes("'=晨练") && csv.includes("'@延误"), 'formula-like text must be neutralized')
assert(csv.includes('"中文,""两行""\n完成"'), 'commas, quotes and newlines must use CSV escaping')
assert(csv.includes(',0.5,,0.5,习惯打卡,') && csv.includes(',,2,-2,任务失败,'), 'numeric columns must remain numeric')
assert(csv.includes('2026-08-24 09:08:07') && csv.includes('中文'), 'Chinese and business time must be retained')
assert(csv.includes('体重体脂逾期处罚,体重体脂逾期未填写（09:00）') && !csv.includes('body_metric_deadline_penalty'), 'CSV uses readable penalty type and title')
assert(csv.includes('系统流水,系统流水') && !csv.includes('future_internal_key'), 'CSV never exposes an unknown internal source key')
assert(ledgerCsvFilename('reward', new Date('2026-08-23T17:02:03Z')) === 'MyTimeLogger-金币流水-兑换-20260824-010203.csv', 'filename must use Beijing time and filter')
console.log('ledger CSV tests passed')
