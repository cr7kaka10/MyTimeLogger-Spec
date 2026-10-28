import { prefetchMorningMotivation } from './morningMotivation'

const db: any = { getAllConfig: () => ({ active_environment: 'development', env_development_server_url: 'https://example.invalid', env_development_auth_token: 'account-token' }) }
let cached = ''; const native = { cacheWeek: (raw: string) => { cached = raw; return true }, clear: () => {} }
const response: any = { ok: true, json: async () => ({ version: 'morning-motivation-v1', items: [] }) }
const ok = await prefetchMorningMotivation(db, async (url, options) => {
  if (!url.endsWith('/api/morning-motivation/week') || (options?.headers as any)?.Authorization !== 'Bearer account-token') throw new Error('wrong account request')
  return response
}, native)
if (!ok || !cached.includes('morning-motivation-v1')) throw new Error('online response must reach native cache')
const offline = await prefetchMorningMotivation(db, async () => { throw new Error('offline') }, native)
if (offline || !cached.includes('morning-motivation-v1')) throw new Error('offline must preserve cached content')
console.log('morning motivation prefetch tests passed')
