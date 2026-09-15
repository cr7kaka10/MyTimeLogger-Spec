import { describe, expect, it } from 'vitest'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { Database } from '../models/Database'

describe('checklist reset local convergence', () => {
  it('clears only proven TickTick cache once for a new reset marker', () => {
    const db = new Database(createBetterSqliteAdapter())
    const now = '2026-07-29 12:00:00'
    db.runRaw("INSERT INTO tasks (id,title,raw_json,updated_at) VALUES ('tick-task','T','{}',?)", [now])
    db.runRaw("INSERT INTO tasks (id,title,raw_json,updated_at) VALUES ('manual-task','M',NULL,?)", [now])
    db.runRaw("INSERT INTO habits (id,name,raw_json,created_at,updated_at) VALUES ('tick-habit','H','{}',?,?)", [now, now])
    db.runRaw("INSERT INTO habit_checkins (id,habit_id,checkin_date,raw_json,updated_at) VALUES ('tick-check','tick-habit','2026-07-01','{}',?)", [now])
    db.runRaw("INSERT INTO habit_checkins (id,habit_id,checkin_date,raw_json,updated_at) VALUES ('derived-check','tick-habit','2026-07-02',NULL,?)", [now])
    db.runRaw("INSERT INTO reward_ledger (id,amount,source_type,source_id,created_at,updated_at) VALUES ('tick-reward',1,'task_complete','tick-task',?,?)", [now, now])
    db.runRaw("INSERT INTO reward_ledger (id,amount,source_type,source_id,created_at,updated_at) VALUES ('manual-reward',1,'exercise_checkin','exercise-1',?,?)", [now, now])
    db.runRaw("INSERT INTO user_wallets (user_id,balance,updated_at) VALUES (1,2,?)", [now])
    db.runRaw("INSERT INTO sync_outbox (change_id,device_id,table_name,record_id,operation,payload_json,status,created_at,updated_at) VALUES ('c1','d','tasks','tick-task','upsert','{}','pending',?,?)", [now, now])

    expect(db.applyChecklistResetMarker('marker-1')).toMatchObject({
      applied: true, tasks: 1, habits: 1, checkins: 2, rewards: 1, outbox: 1, wallets: 1,
    })
    expect(db.allRaw('SELECT id FROM tasks')).toEqual([{ id: 'manual-task' }])
    expect(db.allRaw('SELECT id FROM habits')).toEqual([])
    expect(db.allRaw('SELECT id FROM habit_checkins')).toEqual([])
    expect(db.allRaw('SELECT id FROM reward_ledger')).toEqual([{ id: 'manual-reward' }])
    expect(db.allRaw('SELECT user_id FROM user_wallets')).toEqual([])
    expect(db.allRaw("SELECT id FROM sync_outbox WHERE status IN ('pending','failed','sending')")).toEqual([])
    expect(db.applyChecklistResetMarker('marker-1')).toMatchObject({ applied: false })
  })
})
