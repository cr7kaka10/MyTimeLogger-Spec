import { createCapacitorNativeHttpService, formatPlatformNetworkError, platformFetch, platformUploadMultipart, setNativeHttpTransport } from './fetch'

let calls = 0
let requestOptions: any
const originalFetch = globalThis.fetch
globalThis.fetch = (() => { throw new Error('global fetch must not be called') }) as typeof fetch
const native = createCapacitorNativeHttpService('capacitor-android', { request: async options => { calls += 1; requestOptions = options; return { status: 201, headers: { 'x-native': 1 }, data: { ok: true } } } })
setNativeHttpTransport(native)
const response = await platformFetch('https://atimelogger.example', { method: 'POST', headers: { authorization: 'Bearer test' }, body: '{"a":1}', timeoutMs: 4321 } as any)
if (calls !== 1 || response.status !== 201 || response.headers['x-native'] !== '1' || !(await response.json()).ok || (await response.text()) !== '{"ok":true}') throw new Error('native response contract mismatch')
if (requestOptions.connectTimeout !== 4321 || requestOptions.readTimeout !== 4321 || requestOptions.data !== '{"a":1}') throw new Error('native request contract mismatch')
const image = new File(['sleep-image'], 'sleep.jpg', { type: 'image/jpeg' })
await platformUploadMultipart('https://server.example/upload', image, { headers: { Authorization: 'Bearer test' }, timeoutMs: 7654 })
if (requestOptions.dataType !== 'formData' || requestOptions.data?.[0]?.fileName !== 'sleep.jpg' || requestOptions.data?.[0]?.contentType !== 'image/jpeg') throw new Error('native multipart file contract mismatch')
if (requestOptions.headers.Authorization !== 'Bearer test' || requestOptions.headers['Content-Type'] !== 'multipart/form-data' || requestOptions.headers['Content-Type'].includes('boundary')) throw new Error('native multipart must preserve auth and let Capacitor generate the boundary')
setNativeHttpTransport(null)
globalThis.fetch = originalFetch
if (formatPlatformNetworkError({ name: 'AbortError' }) !== '请求超时（服务端无响应）') throw new Error('timeout must be actionable')
if (!formatPlatformNetworkError(new Error('Cleartext HTTP traffic not permitted')).includes('明文 HTTP')) throw new Error('cleartext policy must be identified')
if (formatPlatformNetworkError(new TypeError('Failed to fetch')).includes('Failed to fetch')) throw new Error('raw WebView fetch errors must not reach users')

let webBody: BodyInit | null | undefined
globalThis.fetch = (async (_url, init) => { webBody = init?.body; return new Response('{"ok":true}', { status: 200, headers: { 'Content-Type': 'application/json' } }) }) as typeof fetch
await platformUploadMultipart('https://server.example/upload', image, { headers: { Authorization: 'Bearer web' } })
globalThis.fetch = originalFetch
if (!(webBody instanceof FormData) || webBody.get('file') !== image) throw new Error('web multipart must use standard FormData')

const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const fetchSource = fs.readFileSync(new URL('./fetch.ts', import.meta.url), 'utf8') as string
if (!fetchSource.includes('if (res.status > 0) return') || !fetchSource.includes('旧 Electron 主进程可能没有此 IPC handler')) throw new Error('stale Electron IPC must fall back to the CORS-enabled renderer request')
if (!fetchSource.includes('Electron请求失败：${electronFailure}；页面回退失败')) throw new Error('Electron IPC failure details must survive a failed renderer fallback')
const dbSource = fs.readFileSync(new URL('../db.ts', import.meta.url), 'utf8') as string
if (!dbSource.includes("import { platformFetch } from './platform/fetch'")) throw new Error('db must import the shared platform requester')
if (!dbSource.includes("platformRuntime === 'capacitor-android' ? platformFetch : undefined")) throw new Error('Android SyncWorker must receive platformFetch')
if (!dbSource.includes('new apiMod.ApiClient(serverUrl, authToken, undefined, requester)')) throw new Error('startup pull and outbox push must share the injected requester')
console.log('platform fetch tests passed')
