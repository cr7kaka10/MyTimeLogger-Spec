import { formatSyncFailure } from './useTimeBook'

const assert = (value: unknown, message: string) => {
  if (!value) throw new Error(message)
}

assert(
  formatSyncFailure({ error: 'server_error', diagnostics: { stage: 'pull', request_id: 'sync-server-500' } } as any)
    === '服务端返回错误，请检查服务日志后重试 · 拉取失败 · 请求 sync-ser',
  'timebook server errors must expose a short request trace',
)
assert(
  !formatSyncFailure({ error: 'request_timeout', diagnostics: { request_id: 'sync-timeout' } } as any).includes('请求 '),
  'timebook timeout guidance must not mislabel a client-side timeout as a server trace',
)
assert(
  !formatSyncFailure({ error: 'server_unreachable', diagnostics: { request_id: 'sync-network' } } as any).includes('请求 '),
  'timebook unavailable guidance must not mislabel a network failure as a server trace',
)

console.log('timebook sync feedback contracts passed')
