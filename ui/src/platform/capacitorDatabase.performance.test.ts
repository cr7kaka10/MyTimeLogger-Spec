import { createCapacitorDatabaseAdapter } from './capacitorDatabase'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
let transactionCalls = 0; let encodedOperations = 0
const bridge = {
  open: () => '{"ok":true}', execute: () => '{"ok":true}',
  query: () => '{"ok":true,"rows":[]}',
  transaction: (raw: string) => {
    transactionCalls++; encodedOperations += JSON.parse(raw).length
    return '{"ok":true}'
  },
}
const adapter = createCapacitorDatabaseAdapter({ MyTimeLoggerSqlite: bridge })
adapter.androidBulk.transaction(Array.from({ length: 250 }, (_, id) => ({ sql: 'INSERT INTO sample VALUES(?)', params: [id] })))
assert(transactionCalls === 1 && encodedOperations === 250, '250 operations must cross the bridge once')
console.log('capacitor database performance tests passed')
