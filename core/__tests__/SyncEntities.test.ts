import { describe, expect, it } from 'vitest'
import { SYNC_TABLES } from '../core/SyncWorker'
import { isOutboxEnabledTable, isServerOwnedTable, primaryKeyForTable, SYNC_ENTITIES } from '../core/SyncEntities'
import { createBetterSqliteAdapter } from '../models/BetterSqliteAdapter'
import { Database } from '../models/Database'

describe('SyncEntities registry', () => {
  it('drives client sync tables and primary keys', () => {
    expect(new Set(SYNC_ENTITIES.map(entity => entity.clientTable)).size).toBe(SYNC_ENTITIES.length)
    expect(SYNC_TABLES).toEqual(SYNC_ENTITIES.map(entity => entity.clientTable))
    expect(primaryKeyForTable('exercise_plan_versions')).toBe('version')
    expect(primaryKeyForTable('external_rewards')).toBe('ext_id')
    expect(primaryKeyForTable('system_config')).toBe('key')
    expect(primaryKeyForTable('user_wallets')).toBe('user_id')
  })

  it('keeps server-owned entities pull-only while preserving system_config key-level denial', () => {
    for (const table of ['goals', 'goal_category_bindings', 'rewards', 'external_rewards']) {
      expect(isServerOwnedTable(table)).toBe(true)
      expect(isOutboxEnabledTable(table)).toBe(false)
    }
    expect(isServerOwnedTable('reward_ledger')).toBe(true)
    expect(isOutboxEnabledTable('reward_ledger')).toBe(false)
    expect(isServerOwnedTable('flash_cards')).toBe(false)
    expect(isOutboxEnabledTable('flash_cards')).toBe(true)
    expect(isServerOwnedTable('flash_task_recommendations')).toBe(true)
    expect(isOutboxEnabledTable('flash_task_recommendations')).toBe(false)
    for (const table of ['management_plans', 'management_plan_revisions']) {
      expect(isServerOwnedTable(table)).toBe(true)
      expect(isOutboxEnabledTable(table)).toBe(false)
    }
    expect(isServerOwnedTable('exercise_plan_versions')).toBe(true)
    expect(isOutboxEnabledTable('exercise_plan_versions')).toBe(false)
    expect(isOutboxEnabledTable('system_config')).toBe(true)
    for (const table of ['sleep_automation_commands', 'sleep_notifications', 'sleep_score_settlements']) {
      expect(isServerOwnedTable(table)).toBe(true)
      expect(isOutboxEnabledTable(table)).toBe(false)
    }

    const db = new Database(createBetterSqliteAdapter())
    db.setConfig('auth_token', 'secret-token')

    expect(db.getPendingOutbox(10).some(item => item.table_name === 'system_config' && item.record_id === 'auth_token')).toBe(false)
  })

  it('uses authoritative ATM ids and hard deletes replaced activities', () => {
    const summary = SYNC_ENTITIES.find(entity => entity.clientTable === 'atm_summary')!
    const activities = SYNC_ENTITIES.find(entity => entity.clientTable === 'atm_activities')!
    expect(summary.primaryKey).toBe('id')
    expect(activities.primaryKey).toBe('id')
    expect(activities.naturalKeys).toEqual([])
    expect(activities.deletePolicy).toBe('hard_delete')
  })
})
