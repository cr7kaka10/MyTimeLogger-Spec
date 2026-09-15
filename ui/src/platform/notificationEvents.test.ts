import { classifyNotificationEvents } from './notificationEvents'
import { classifySleepNotificationEvents } from './notificationEvents'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const external = [
  { id: 'a', ext_id: 'goal-ok', item_type: 'goal', item_name: '阅读', coins: 5, status: 0 },
  { id: 'b', ext_id: 'goal-fail', item_type: 'goal', item_name: '运动', coins: -2, status: 0 },
  { id: 'c', ext_id: 'task-1', item_type: 'task', item_name: '整理', coins: 1, status: 0 },
  { id: 'd', ext_id: 'habit-1', item_type: 'habit', item_name: '早起', coins: 1, status: 0 },
]
const ledger = [
  { id: 'l1', amount: 3, source_type: 'task_complete', description: '任务' },
  { id: 'l2', amount: -1, source_type: 'habit_fail', description: '习惯' },
  { id: 'l3', amount: -8, source_type: 'reward_buy', description: '电影券' },
]
const result = classifyNotificationEvents(external, ledger)
assert(result.handledKeys.includes('ext:goal-ok') && result.handledKeys.includes('ledger:l3'), 'stable authoritative event keys required')
assert(result.notifications.filter(item => item.channel === 'achievements').length === 2, 'goal success and actual penalty notify separately')
assert(result.notifications.some(item => item.body.includes('2 项奖励待领取')), 'non-goal pending rewards aggregate once')
assert(result.notifications.some(item => item.body === '金币到账 +3') && result.notifications.some(item => item.body === '金币扣除 -1'), 'coin credit and penalty use net summaries')
assert(result.notifications.some(item => item.body.includes('电影券') && item.route === 'backpack'), 'reward purchase routes to backpack')
assert(!result.notifications.some(item => item.body === '金币扣除 -9'), 'reward purchase must not duplicate generic deduction')
const sleep = classifySleepNotificationEvents([{ id: 'done', event_type: 'analysis_done' }, { id: 'error', event_type: 'analysis_error' }, { id: 'skip', event_type: 'analysis_skipped_missing_sleep_data' }])
assert(sleep.map(item => item.body).join('|') === '睡眠分析已完成|缺少有效睡眠数据，未执行完整分析|缺少有效睡眠数据，未执行完整分析', 'sleep result notifications cover done/error/skipped')
console.log('notification event tests passed')
