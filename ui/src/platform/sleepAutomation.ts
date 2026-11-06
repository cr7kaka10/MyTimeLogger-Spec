export type SleepAutomationError = 'unavailable' | 'native_error' | 'rejected' | 'invalid_status'
export type SleepAutomationResult = { ok: boolean, error?: SleepAutomationError }
export type SleepCaptureTest = { runId: string, date: string, stage: string, reason: string, startedAt?: number, savedAt: string, width: number, height: number, fileName?: string, album?: string }
export type SleepAutomationStatus = { available: boolean, enabled: boolean, configured?: boolean, stage?: string, phase?: string, sleepDate?: string, updatedAt?: number, reason?: string, captureBlockedReason?: string, captureStep?: string, captureWindow?: string, captureTest?: SleepCaptureTest, mediaSelected?: boolean, requestIdPresent?: boolean, nextRunAt?: string, nextRetryAt?: string, history?: unknown[], error?: SleepAutomationError }
export function sleepAutomationProgress(status: SleepAutomationStatus): string {
  if (status.stage === 'SUCCESS') return '本次睡眠分析完成，正在刷新报告'
  const failures: Record<string, string> = { login_required: '请登录后重试', date_mismatch: '截图日期与今天不符', ocr_failed: '图片识别失败', vision_model_unconfigured: '尚未配置视觉模型', network_error: '网络连接失败', retry_window_elapsed: '今日重试窗口已结束' }
  if (status.stage === 'FAILED' && !status.nextRetryAt) return `自动化失败：${failures[status.reason || ''] || status.reason || '未知错误'}`
  const labels: Record<string, string> = {
    ocr: status.requestIdPresent ? '图片已上传，OCR 正在排队或识别' : '正在上传睡眠图片',
    ocr_ready: 'OCR 已完成，正在请求睡眠分析',
    report: '正在生成本次睡眠分析报告',
  }
  const label = labels[status.phase || ''] || '正在处理睡眠图片'
  return status.nextRetryAt && status.reason ? `${label}；下次重试：${status.nextRetryAt}` : label
}
type NativeSleepAutomation = { status(): string, enable(): boolean, disable(): void, test(): boolean, retry(): boolean, generateReport(): boolean, oneClick?(): boolean, previewCapture(): boolean, exportCapture?(): string, cancel(): void, configure(url: string, token: string, userId: string): boolean, authorize(permission: string): boolean, clearConfiguration(): void }
type Host = { MTLSleepAutomation?: NativeSleepAutomation }

export function createSleepAutomation(host: Host = globalThis as unknown as Host) {
  const native = host.MTLSleepAutomation
  const action = (run?: () => boolean): SleepAutomationResult => {
    if (!run) return { ok: false, error: 'unavailable' }
    try { return run() ? { ok: true } : { ok: false, error: 'rejected' } } catch { return { ok: false, error: 'native_error' } }
  }
  return {
    status(): SleepAutomationStatus {
      if (!native) return { available: false, enabled: false, error: 'unavailable' }
      try {
        const value = JSON.parse(native.status()) as Record<string, unknown>
        if (!value || typeof value.enabled !== 'boolean') return { available: true, enabled: false, error: 'invalid_status' }
        return { ...value, available: true, enabled: value.enabled } as SleepAutomationStatus
      } catch { return { available: true, enabled: false, error: 'native_error' } }
    },
    enable: () => action(native && (() => native.enable())),
    disable: () => action(native && (() => { native.disable(); return true })),
    test: () => action(native && (() => native.test())),
    retry: () => action(native && (() => native.retry())),
    generateReport: () => action(native && (() => native.generateReport())),
    oneClick: () => action(native?.oneClick ? () => native.oneClick!() : undefined),
    previewCapture: () => action(native && (() => native.previewCapture())),
    exportCapture: () => { try { return native?.exportCapture?.() || 'unavailable' } catch { return 'gallery_write_failed' } },
    cancel: () => action(native && (() => { native.cancel(); return true })),
    configure: (url: string, token: string, userId: string) => action(native && (() => native.configure(url, token, userId))),
    authorize: (permission: string) => action(native && (() => native.authorize(permission))),
    clearConfiguration: () => action(native && (() => { native.clearConfiguration(); return true })),
  }
}
export const sleepAutomation = createSleepAutomation()
export type SleepAutomationConfig = { url: string, token: string, userId: string } | null
const SLEEP_AUDIT_FIELDS = ['stage', 'result', 'reason', 'huaweiVersion', 'selectorType', 'attempt', 'durationMs'] as const
export function normalizeSleepAutomationAudit(metadata: Record<string, unknown>) {
  const output: Record<string, string | number> = {}
  for (const key of SLEEP_AUDIT_FIELDS) {
    const value = metadata[key]
    if (typeof value === 'number' && Number.isFinite(value)) output[key] = value
    else if (typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,80}$/.test(value)) output[key] = value
  }
  return output
}
export function createSleepAutomationConfigSync(api = sleepAutomation) {
  let previous: SleepAutomationConfig | undefined
  return (config: SleepAutomationConfig) => {
    const status = api.status()
    if (previous !== undefined && previous?.url === config?.url && previous?.token === config?.token && previous?.userId === config?.userId && (config === null || status.configured)) return
    if (previous !== undefined) api.cancel()
    if (config) api.configure(config.url, config.token, config.userId)
    else { api.disable(); api.clearConfiguration() }
    previous = config
  }
}
