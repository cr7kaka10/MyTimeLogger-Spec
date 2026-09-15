import BetterSqlite3 from 'better-sqlite3'

type BetterSqliteDatabase = ReturnType<typeof BetterSqlite3>

export interface BetterSqliteAdapter {
  run(sql: string, params?: any[]): void
  exec(sql: string): void
  prepare(sql: string): {
    bind(params?: any[]): void
    step(): boolean
    getAsObject(): Record<string, any>
    free(): void
  }
  close(): void
}

export function createBetterSqliteAdapter(filename = ':memory:'): BetterSqliteAdapter {
  const db: BetterSqliteDatabase = new BetterSqlite3(filename)

  return {
    run(sql: string, params: any[] = []) {
      db.prepare(sql).run(params)
    },
    exec(sql: string) {
      db.exec(sql)
    },
    prepare(sql: string) {
      const stmt = db.prepare(sql)
      let rows: Record<string, any>[] = []
      let cursor = 0
      let bound = false

      return {
        bind(params: any[] = []) {
          rows = stmt.all(params) as Record<string, any>[]
          cursor = 0
          bound = true
        },
        step() {
          if (!bound) {
            rows = stmt.all() as Record<string, any>[]
            cursor = 0
            bound = true
          }
          return cursor < rows.length
        },
        getAsObject() {
          return rows[cursor++] ?? {}
        },
        free() {
          rows = []
          cursor = 0
          bound = false
        },
      }
    },
    close() {
      db.close()
    },
  }
}
