import Database from 'better-sqlite3'
import { describe, expect, it } from 'vitest'
import { SyncWorker } from '../core/SyncWorker'

describe('learning tree deletion merge', () => {
  it('deletes children before KR under active SQLite foreign keys', () => {
    const db = new Database(':memory:')
    try {
      db.exec('PRAGMA foreign_keys=ON; CREATE TABLE learning_krs(id TEXT PRIMARY KEY); CREATE TABLE learning_tasks(id TEXT PRIMARY KEY, kr_id TEXT REFERENCES learning_krs(id))')
      db.exec("INSERT INTO learning_krs VALUES('kr-1'); INSERT INTO learning_tasks VALUES('task-1','kr-1')")
      const stages = (new SyncWorker({ enableSSE: false }) as any)._mergeTableStages({
        learning_krs: [{ id: 'kr-1', _sync_operation: 'delete' }],
        learning_tasks: [{ id: 'task-1', _sync_operation: 'delete' }],
      }) as Array<{ table: string; rows: Array<{ id: string }> }>
      expect(stages.map(stage => stage.table)).toEqual(['learning_tasks', 'learning_krs'])
      const inserts = (new SyncWorker({ enableSSE: false }) as any)._mergeTableStages({ learning_krs: [{ id: 'kr-2' }], learning_tasks: [{ id: 'task-2' }] })
      expect(inserts.map((stage: { table: string }) => stage.table)).toEqual(['learning_krs', 'learning_tasks'])
      for (const stage of stages) for (const row of stage.rows) db.prepare(`DELETE FROM ${stage.table} WHERE id=?`).run(row.id)
      expect(db.prepare('SELECT COUNT(*) AS count FROM learning_krs').get()).toMatchObject({ count: 0 })
      expect(db.prepare('SELECT COUNT(*) AS count FROM learning_tasks').get()).toMatchObject({ count: 0 })
    } finally { db.close() }
  })
})
