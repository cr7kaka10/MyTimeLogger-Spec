import { getAndroidBulkCapability, SqliteBridgeError, type AndroidBulkDatabaseAdapter } from './capacitorDatabase'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const ordinary = { run() {}, exec() {}, prepare() { throw new Error('unused') } }
assert(getAndroidBulkCapability(ordinary) === undefined, 'ordinary adapters must not expose Android bulk capability')

const android = { ...ordinary, androidBulk: {
  query: () => [], transaction: () => {}, yieldToUi: async () => {},
} } as AndroidBulkDatabaseAdapter
assert(getAndroidBulkCapability(android) === android.androidBulk, 'Android bulk capability must be detectable')

const calls: string[] = []
const bridge = {
  open: (name: string) => { calls.push(`open:${name}`); return '{"ok":true}' },
  execute: (sql: string) => { calls.push(`execute:${sql}`); return '{"ok":true}' },
  query: (sql: string) => { calls.push(`query:${sql}`); return '{"ok":true,"rows":[{"id":1}]}' },
  transaction: (operations: string) => { calls.push(`transaction:${operations}`); return '{"ok":true}' },
}
const { accountDatabaseName, createCapacitorDatabaseAdapter } = await import('./capacitorDatabase')
assert(accountDatabaseName('acct-0123456789abcdef0123456789abcdef') !== accountDatabaseName('acct-fedcba9876543210fedcba9876543210'), 'accounts must use different native databases')
assert(!accountDatabaseName('acct-0123456789abcdef0123456789abcdef').includes('/'), 'native database names must not contain paths')
const adapter = createCapacitorDatabaseAdapter({ MyTimeLoggerSqlite: bridge })
adapter.run('UPDATE sample SET value = ?', ['kept'])
const statement = adapter.prepare('SELECT id FROM sample'); statement.bind(); statement.step(); statement.getAsObject()
adapter.androidBulk.transaction([{ sql: 'DELETE FROM sample WHERE id = ?', params: [1] }, { sql: 'DELETE FROM sample WHERE id = ?', params: [2] }])
assert(calls.filter(call => call.startsWith('transaction:')).length === 1, 'N operations must use one bridge transaction call')
assert(calls.some(call => call.startsWith('execute:UPDATE')), 'ordinary run must retain execute behavior')
assert(calls.some(call => call.startsWith('query:SELECT')), 'ordinary prepare must retain query behavior')

const privateValue = 'private-token-123'
const failedBridge = { ...bridge, open: () => '{"ok":true}', transaction: () =>
  '{"ok":false,"error":"sqlite_operation_failed","operation":"transaction","index":2,"error_category":"schema"}' }
const failedAdapter = createCapacitorDatabaseAdapter({ MyTimeLoggerSqlite: failedBridge })
try {
  failedAdapter.androidBulk.transaction([{ sql: 'private SQL', params: [privateValue] }])
  throw new Error('native failure expected')
} catch (error) {
  assert(error instanceof SqliteBridgeError, 'native category must use the safe bridge error')
  assert((error as SqliteBridgeError).operation === 'transaction' && (error as SqliteBridgeError).index === 2, 'operation/index must survive decode')
  assert((error as SqliteBridgeError).errorCategory === 'schema', 'native category must survive decode')
  assert(!(error as Error).message.includes(privateValue), 'decoded errors must not expose native values')
}
console.log('capacitor database capability tests passed')
