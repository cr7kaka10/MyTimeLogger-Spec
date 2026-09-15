import type { NotificationChannel, NotificationRoute } from './services'

type ExternalFact = { id: string | number; ext_id?: string; item_type: string; item_name?: string; coins: number; status: number }
type LedgerFact = { id: string | number; amount: number; source_type: string; description?: string }
export type BusinessNotification = { eventKey: string; handledKeys: string[]; channel: NotificationChannel; title: string; body: string; route: NotificationRoute }
const amount = (value: number) => Math.abs(Number(value)).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
export const externalNotificationKey = (fact: ExternalFact) => `ext:${fact.ext_id || fact.id}`
export const ledgerNotificationKey = (fact: LedgerFact) => `ledger:${fact.id}`
const externalKey = externalNotificationKey
const ledgerKey = ledgerNotificationKey

export function classifyNotificationEvents(external: ExternalFact[], ledger: LedgerFact[]) {
  const notifications: BusinessNotification[] = []; const handledKeys = [...external.map(externalKey), ...ledger.map(ledgerKey)]
  for (const fact of external.filter(item => item.status === 0 && item.item_type === 'goal' && Number(item.coins) !== 0)) {
    const positive = Number(fact.coins) > 0; const key = externalKey(fact)
    notifications.push({ eventKey: key, handledKeys: [key], channel: 'achievements', title: positive ? '目标达成' : '目标未达成', body: positive ? `${fact.item_name || '目标'}，待领取 +${amount(fact.coins)} 金币` : `${fact.item_name || '目标'}，待扣除 -${amount(fact.coins)} 金币`, route: 'goals' })
  }
  const pending = external.filter(item => item.status === 0 && item.item_type !== 'goal')
  if (pending.length) { const keys = pending.map(externalKey); notifications.push({ eventKey: keys[0], handledKeys: keys, channel: 'rewards', title: '新奖励待领取', body: `${pending.length} 项奖励待领取`, route: 'rewards' }) }
  const purchases = ledger.filter(item => item.source_type === 'reward_buy')
  for (const fact of purchases) { const key = ledgerKey(fact); notifications.push({ eventKey: key, handledKeys: [key], channel: 'rewards', title: '兑换成功', body: `${fact.description || '奖励'}，已放入背包`, route: 'backpack' }) }
  const regular = ledger.filter(item => item.source_type !== 'reward_buy'); const positive = regular.filter(item => Number(item.amount) > 0); const negative = regular.filter(item => Number(item.amount) < 0)
  if (positive.length) { const keys = positive.map(ledgerKey); const total = positive.reduce((sum, item) => sum + Number(item.amount), 0); notifications.push({ eventKey: keys[0], handledKeys: keys, channel: 'rewards', title: '金币变动', body: `金币到账 +${amount(total)}`, route: 'rewards' }) }
  if (negative.length) { const keys = negative.map(ledgerKey); const total = negative.reduce((sum, item) => sum + Number(item.amount), 0); notifications.push({ eventKey: keys[0], handledKeys: keys, channel: 'rewards', title: '金币变动', body: `金币扣除 -${amount(total)}`, route: 'rewards' }) }
  return { handledKeys, notifications }
}

export function classifySleepNotificationEvents(rows: Array<{ id: string; event_type: string; title?: string; body?: string }>): BusinessNotification[] {
  return rows.filter(row => row.event_type.startsWith('analysis_')).map(row => ({
    eventKey: `sleep:${row.id}`, handledKeys: [`sleep:${row.id}`], channel: 'sleep', route: 'sleep',
    title: row.title || (row.event_type === 'analysis_done' ? '睡眠分析完成' : '睡眠分析未完成'),
    body: row.body || (row.event_type === 'analysis_done' ? '睡眠分析已完成' : '缺少有效睡眠数据，未执行完整分析'),
  }))
}
