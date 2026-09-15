import { CapacitorHttp } from '@capacitor/core'
import { getElectronApi } from './electron'
import type { NativeHttpService } from './services'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'

export interface PlatformFetchResponse {
  ok: boolean
  status: number
  headers: Record<string, string>
  text: () => Promise<string>
  json: () => Promise<any>
}

let nativeHttp: NativeHttpService | null = null
type FetchAuditSink = (detail: { url: string; method: string; status: number; ok: boolean; errorCode?: string }) => void
let fetchAuditSink: FetchAuditSink | null = null
export const setPlatformFetchAuditSink = (sink: FetchAuditSink | null) => { fetchAuditSink = sink }
const reportFetch = (url: string, method: string, status: number, ok: boolean, errorCode?: string) => { try { fetchAuditSink?.({ url, method, status, ok, errorCode }) } catch {} }

export const formatPlatformNetworkError = (error: any): string => {
  const message = String(error?.message || '')
  if (error?.name === 'AbortError' || /abort|timeout|timed out/i.test(message)) return '请求超时（服务端无响应）'
  if (/cleartext/i.test(message)) return 'Android 阻止了明文 HTTP，请更新 Debug APK 或改用 HTTPS'
  return '无法连接服务端，请检查服务器地址、网络连通性及服务状态'
}

type CapacitorHttpPort = { request(options: { url: string, method: string, headers?: Record<string, string>, data?: unknown, dataType?: 'formData', connectTimeout?: number, readTimeout?: number }): Promise<{ status: number, headers: Record<string, unknown>, data: unknown }> }

const fileToBase64 = async (file: File): Promise<string> => {
  try {
    const bytes = new Uint8Array(await file.arrayBuffer())
    let binary = ''
    for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000))
    return btoa(binary)
  } catch {
    throw new Error('SLEEP_FILE_READ_FAILED')
  }
}

export function createCapacitorNativeHttpService(runtime: PlatformRuntime = detectPlatformRuntime(), http: CapacitorHttpPort = CapacitorHttp): NativeHttpService {
  const available = runtime === 'capacitor-android'
  const normalize = (response: { status: number, headers: Record<string, unknown>, data: unknown }) => {
    const text = typeof response.data === 'string' ? response.data : response.data == null ? '' : JSON.stringify(response.data)
    const headers = Object.fromEntries(Object.entries(response.headers || {}).map(([key, value]) => [key, String(value)]))
    return { status: response.status, headers, text }
  }
  return { available, async request(url, options = {}) {
    if (!available) throw new Error('CAPACITOR_HTTP_UNAVAILABLE')
    const response = await http.request({ url, method: options.method || 'GET', headers: options.headers, data: options.body, connectTimeout: options.timeoutMs, readTimeout: options.timeoutMs })
    return normalize(response)
  }, async uploadMultipart(url, file, options = {}) {
    if (!available) throw new Error('CAPACITOR_HTTP_UNAVAILABLE')
    const headers = Object.fromEntries(Object.entries(options.headers || {}).filter(([key]) => key.toLowerCase() !== 'content-type'))
    headers['Content-Type'] = 'multipart/form-data'
    const response = await http.request({
      url, method: 'POST', headers, dataType: 'formData', connectTimeout: options.timeoutMs, readTimeout: options.timeoutMs,
      data: [{ key: options.fieldName || 'file', value: await fileToBase64(file), type: 'base64File', contentType: file.type || 'application/octet-stream', fileName: file.name || 'upload.bin' }],
    })
    return normalize(response)
  } }
}

export const setNativeHttpTransport = (transport: NativeHttpService | null) => { nativeHttp = transport }

export const platformUploadMultipart = async (url: string, file: File, options: { fieldName?: string; headers?: Record<string, string>; timeoutMs?: number } = {}): Promise<PlatformFetchResponse> => {
  if (nativeHttp?.available && nativeHttp.uploadMultipart) {
    const res = await nativeHttp.uploadMultipart(url, file, options)
    return { ok: res.status >= 200 && res.status < 300, status: res.status, headers: res.headers, text: async () => res.text, json: async () => { try { return JSON.parse(res.text) } catch { return res.text } } }
  }
  const body = new FormData()
  body.append(options.fieldName || 'file', file)
  const res = await fetch(url, { method: 'POST', headers: options.headers, body })
  return { ok: res.ok, status: res.status, headers: Object.fromEntries(res.headers.entries()), text: () => res.text(), json: () => res.json() }
}

export const platformFetch = async (url: string, options?: RequestInit): Promise<PlatformFetchResponse> => {
  const method = String(options?.method || 'GET').toUpperCase()
  if (nativeHttp?.available) {
    try { const res = await nativeHttp.request(url, { method: options?.method, headers: options?.headers as Record<string, string> | undefined, body: options?.body as string | undefined, timeoutMs: (options as any)?.timeoutMs })
    reportFetch(url, method, res.status, res.status >= 200 && res.status < 300)
    return { ok: res.status >= 200 && res.status < 300, status: res.status, headers: res.headers, text: async () => res.text, json: async () => { try { return JSON.parse(res.text) } catch { return res.text } } }
    } catch (error: any) { reportFetch(url, method, 0, false, error?.name || 'network_error'); throw error }
  }
  const api = getElectronApi()
  let electronFailure = ''
  if (api?.ticktickFetch) {
    try {
      const res = await api.ticktickFetch(url, { method: options?.method || 'GET', headers: options?.headers, body: options?.body })
      if (res.status > 0) { reportFetch(url, method, res.status, res.ok); return {
        ok: res.ok, status: res.status, headers: (res as any).headers || {}, text: async () => res.body,
        json: async () => { try { return JSON.parse(res.body) } catch { return res.body } },
      } }
      electronFailure = String((res as any).statusText || 'Electron IPC returned status 0')
    } catch (error: any) {
      electronFailure = String(error?.message || 'Electron IPC request failed')
      // 旧 Electron 主进程可能没有此 IPC handler；已获 CORS 允许时回退渲染页请求。
    }
  }

  let res: Response
  try {
    res = await fetch(url, options)
  } catch (error: any) {
    reportFetch(url, method, 0, false, error?.name || 'network_error')
    if (!electronFailure) throw error
    const combined = new Error(`Electron请求失败：${electronFailure}；页面回退失败：${String(error?.message || 'Failed to fetch')}`)
    combined.name = error?.name || 'TypeError'
    throw combined
  }
  reportFetch(url, method, res.status, res.ok)
  return {
    ok: res.ok,
    status: res.status,
    headers: res.headers ? Object.fromEntries(res.headers.entries()) : {},
    text: () => res.text(),
    json: () => res.json(),
  }
}
