/** 同步功能统一配置 — API 路径、超时、去重、重试 */

export const SYNC_API_ENDPOINTS = {
  push: '/api/sync/push',
  pull: '/api/sync/pull',
  events: '/api/sync/events',
} as const

export const SYNC_TIMEOUTS = {
  /** ApiClient 默认请求超时 */
  default: 5_000,
  push: 20_000,
  pull: 30_000,
  refresh: 45_000,
} as const

export const SYNC_DEDUPE = {
  /** SSE/可见性等被动 Pull 去重窗口 */
  passivePullMs: 15_000,
} as const

export const SYNC_RETRY = {
  maxAttempts: 5,
  backoffMs: 1_000,
} as const

export const SYNC_CONFIG = {
  api: SYNC_API_ENDPOINTS,
  timeout: SYNC_TIMEOUTS,
  dedupe: SYNC_DEDUPE,
  retry: SYNC_RETRY,
} as const

export type SyncConfig = typeof SYNC_CONFIG
