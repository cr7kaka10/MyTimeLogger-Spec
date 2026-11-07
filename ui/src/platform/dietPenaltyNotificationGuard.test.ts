import { hasEarlierLocalDietCheckin } from './dietPenaltyNotificationGuard'

const fact = { source_type: 'exercise_diet_penalty', source_id: 'exercise-diet-penalty:1:2026-10-28:v5:lunch_on_time', target_date: '2026-10-28' }
const valid = { rule_key: 'lunch_on_time', status: 'completed', occurred_at: '2026-10-28 13:30:00' }
const pending = { table_name: 'exercise_diet_checkins', record_id: 'diet:1:2026-10-28:v5:lunch_on_time', payload_json: JSON.stringify(valid) }
if (!hasEarlierLocalDietCheckin(fact, [valid], [])) throw new Error('local timely checkin suppresses penalty')
if (!hasEarlierLocalDietCheckin(fact, [], [pending])) throw new Error('unsynced outbox suppresses penalty')
if (hasEarlierLocalDietCheckin(fact, [{ ...valid, occurred_at: '2026-10-28 13:31:00' }], [])) throw new Error('late checkin cannot suppress')
if (hasEarlierLocalDietCheckin(fact, [], [])) throw new Error('unconfirmed checkin cannot suppress')
console.log('diet notification guard tests passed')
