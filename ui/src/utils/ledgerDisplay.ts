import type { LedgerEntry } from '../types'

type LedgerSourcePresentation = { name: string; badge: string; isFail?: boolean }

export const LEDGER_SOURCE_CATALOG: Record<string, LedgerSourcePresentation> = {
  habit_checkin: { name: '习惯打卡', badge: '习惯' }, habit_fail: { name: '习惯未完成', badge: '习惯', isFail: true },
  habit: { name: '习惯奖励', badge: '习惯' }, task_complete: { name: '清单完成', badge: '清单' },
  task_fail: { name: '任务失败', badge: '清单', isFail: true }, task: { name: '清单奖励', badge: '清单' },
  goal_reward: { name: '目标达成奖励', badge: '目标' }, goal_penalty: { name: '目标未达成处罚', badge: '目标', isFail: true },
  learning_checkin: { name: '学习打卡', badge: '学习' }, learning_objective_complete: { name: '学习目标完成', badge: '学习' }, learning: { name: '学习奖励', badge: '学习' },
  exercise_checkin: { name: '运动打卡', badge: '运动' }, exercise_score: { name: '运动日结', badge: '运动' },
  exercise_completion_reward: { name: '运动全完成奖励', badge: '运动' }, body_metric_deadline_penalty: { name: '体重体脂逾期处罚', badge: '运动', isFail: true },
  exercise_diet_penalty: { name: '饮食约束逾期处罚', badge: '饮食', isFail: true },
  sleep_settlement_reward: { name: '睡眠评分结果', badge: '睡眠' }, sleep_cycle_penalty: { name: '睡眠周期不足处罚', badge: '睡眠', isFail: true },
  sleep_deep_penalty: { name: '深睡不足处罚', badge: '睡眠', isFail: true }, sleep_no_sleep_penalty: { name: '无睡眠严重处罚', badge: '睡眠', isFail: true },
  sleep_completion_reward: { name: '睡眠全完成奖励', badge: '睡眠' }, sleep_bedtime_adjustment: { name: '入睡时间奖惩', badge: '睡眠' },
  sleep_diary_completion_reward: { name: '睡眠日记完成奖励', badge: '睡眠' }, sleep_morning_diary_reward: { name: '晨间日记奖励', badge: '睡眠' }, sleep_evening_diary_reward: { name: '晚间日记奖励', badge: '睡眠' },
  reward_buy: { name: '兑换奖励', badge: '兑换' }, store_custom_spend: { name: '自定义消费', badge: '兑换', isFail: true },
  manual_adjustment: { name: '人工调整', badge: '系统流水' }, backpack_use: { name: '背包使用', badge: '兑换' }, backpack_discard: { name: '背包丢弃', badge: '兑换', isFail: true },
  external_claim: { name: '外部奖励', badge: '系统流水' },
}

const SYSTEM_FALLBACK: LedgerSourcePresentation = { name: '系统流水', badge: '系统流水' }
const PREFIXES = ['习惯', '清单', '目标', '学习', '运动', '饮食', '睡眠', '兑换']

export const ledgerSourcePresentation = (sourceType: string): LedgerSourcePresentation => (
  LEDGER_SOURCE_CATALOG[sourceType] || SYSTEM_FALLBACK
)

export const ledgerSourceName = (sourceType: string) => ledgerSourcePresentation(sourceType).name

export const parseLedgerDisplay = (item: Pick<LedgerEntry, 'description' | 'source_type' | 'source_id' | 'amount' | 'target_date' | 'display_title'>) => {
  const raw = (item.description || '').trim(); let rest = raw; let marker = ''; let prefix = ''
  while (true) {
    const nextMarker = rest.match(/^([√×✕❌])\s*/)
    if (nextMarker) { marker ||= nextMarker[1]; rest = rest.slice(nextMarker[0].length).trim(); continue }
    const nextPrefix = PREFIXES.find(candidate => rest === candidate || rest.startsWith(`${candidate} `))
    if (!nextPrefix) break
    prefix = nextPrefix; rest = rest.slice(nextPrefix.length).trim()
  }
  const presentation = ledgerSourcePresentation(item.source_type)
  const isGoalUnlock = item.source_type === 'reward_buy' && String(item.source_id || '').includes(':goal:goal_')
  if (isGoalUnlock) rest = rest.replace(/^目标自动解锁兑换:\s*/, '')
  const isCanonical = isGoalUnlock || ['goal_reward', 'goal_penalty', 'exercise_checkin', 'exercise_score'].includes(item.source_type)
  const rawName = item.display_title || (item.source_type === 'exercise_checkin' ? '运动打卡' : rest || presentation.name)
  const name = isCanonical ? rawName.replace(/\s+(?:\d{4}-)?\d{2}-\d{2}$/, '') : rawName
  const date = (item.target_date || '').slice(-5)
  return {
    isFail: marker ? marker !== '√' : Boolean(presentation.isFail) || item.amount < 0,
    label: isGoalUnlock ? '目标' : prefix || presentation.badge,
    sourceName: presentation.name,
    title: isCanonical && date ? `${name}【${date}】` : name,
  }
}
