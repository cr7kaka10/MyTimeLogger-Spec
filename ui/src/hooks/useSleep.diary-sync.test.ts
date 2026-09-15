import { isDiaryRewardLocallyConfirmed, saveSleepDiaryAndSync } from './useSleep'
import { syncChangeNow } from '../db'

const saves: Array<[string, string, string]> = []
let sequence = 0
const db = { saveSleepDiary: (date: string, type: string, text: string) => {
  saves.push([date, type, text]); return { changeId: `change-${++sequence}`, recordId: sequence }
} }
const syncResult = (delivery: 'accepted' | 'duplicate' | 'pending' | 'rejected', pullOk: boolean, reason?: string, ledgerConfirmed = pullOk) =>
  async () => ({ delivery, pullOk, ledgerConfirmed, reason, sync: { ok: pullOk, merged: 0 } })

const confirmed = await saveSleepDiaryAndSync(db, '2026-09-08', 'morning', '晨记', syncResult('accepted', true))
if (confirmed.state !== 'confirmed' || saves[0][1] !== 'morning') throw new Error('online save must confirm its own change')

const delivered = await saveSleepDiaryAndSync(db, '2026-09-08', 'morning', '修改晨记', syncResult('accepted', false))
if (delivered.state !== 'delivered') throw new Error('accepted diary must stay delivered when unrelated pull fails')

const unconfirmed = await saveSleepDiaryAndSync(db, '2026-09-08', 'evening', '未确认奖励', syncResult('accepted', true, undefined, false))
if (unconfirmed.state !== 'delivered') throw new Error('accepted diary must stay delivered until its ledger fact is merged')

const pending = await saveSleepDiaryAndSync(db, '2026-09-08', 'evening', '离线晚记', syncResult('pending', false, 'offline'))
if (pending.state !== 'pending') throw new Error('offline save must remain locally saved and pending')

const rejected = await saveSleepDiaryAndSync(db, '2026-09-08', 'evening', '被拒绝', syncResult('rejected', true, 'invalid_diary'))
if (rejected.state !== 'rejected' || rejected.reason !== 'invalid_diary') throw new Error('target rejection must expose its reason')

const duplicate = await saveSleepDiaryAndSync(db, '2026-09-08', 'morning', '', syncResult('duplicate', true))
if (duplicate.state !== 'confirmed' || saves[5][2] !== '') throw new Error('explicit clear and duplicate replay must be confirmed')

const singled = await syncChangeNow('diary-change', { reason: 'test' }, async () => ({
  ok: false, merged: 0, error: 'unrelated_pull_failed', diagnostics: { push: { operation_results: [
    { change_id: 'diary-change', status: 'accepted' }, { change_id: 'other-change', status: 'rejected' },
  ] } },
}))
if (singled.delivery !== 'accepted' || singled.pullOk) throw new Error('wrapper must separate target delivery from pull result')

const confirmedLocalState = (delivery: string, rewardPresent: boolean, rewardStatus: string) => ({
  allRaw: (sql: string) => sql.includes('sync_outbox') ? [{ status: delivery }]
    : sql.includes('reward_ledger') ? (rewardPresent ? [{ id: 'morning-reward' }] : [])
      : [{ morning_diary_reward_status: rewardStatus }],
})
if (isDiaryRewardLocallyConfirmed(confirmedLocalState('pending', true, 'completed'), '2026-09-14', 'morning', true, 'change-1')) {
  throw new Error('a local reward must not confirm an unsent diary operation')
}
if (isDiaryRewardLocallyConfirmed(confirmedLocalState('synced', false, 'completed'), '2026-09-14', 'morning', true, 'change-1')) {
  throw new Error('a delivered diary must not confirm before the reward ledger row arrives')
}
if (!isDiaryRewardLocallyConfirmed(confirmedLocalState('synced', true, 'completed'), '2026-09-14', 'morning', true, 'change-1')) {
  throw new Error('a later core or checklist pull must resolve the diary confirmation')
}
if (!isDiaryRewardLocallyConfirmed(confirmedLocalState('synced', false, 'pending'), '2026-09-14', 'morning', false, 'change-1')) {
  throw new Error('clearing a diary must confirm only after the reward row is removed')
}

console.log('sleep diary per-change sync contracts passed')
