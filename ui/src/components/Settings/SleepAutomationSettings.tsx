import type { SleepAutomationStatus } from '../../platform/sleepAutomation'

export type SleepPermission = 'accessibility' | 'notifications' | 'media' | 'battery'
export type SleepPermissions = Record<SleepPermission, boolean>
const labels: Record<SleepPermission, string> = { accessibility: '辅助功能控制', notifications: '通知提醒', media: '睡眠图片访问', battery: '忽略电池优化' }
export const canEnableSleepAutomation = (consented: boolean, permissions: SleepPermissions) => consented && Object.values(permissions).every(Boolean)
const safeText = (value: unknown) => typeof value === 'string' && !/(https?:|content:|file:|bearer|token|@|[{}])/i.test(value) ? value.slice(0, 80) : '已隐藏'

export function SleepAutomationSettings({ status, consented, permissions, onConsent, onToggle, onAuthorize, onTest, onRetry, onStop }: {
  status: SleepAutomationStatus; consented: boolean; permissions: SleepPermissions
  onConsent(value: boolean): void; onToggle(value: boolean): void; onAuthorize(key: SleepPermission): void
  onTest(): void; onRetry(): void; onStop(): void
}) {
  const ready = canEnableSleepAutomation(consented, permissions)
  const missing = (Object.keys(labels) as SleepPermission[]).filter(key => !permissions[key]).map(key => labels[key])
  const history = (status.history || []).filter(value => value && typeof value === 'object').slice(-7).reverse() as Array<Record<string, unknown>>
  return <section className="overflow-hidden rounded-xl border border-orange-100 bg-white">
    <div role="alert" className="bg-orange-50 px-4 py-3 text-sm text-orange-800">每天 08:40 将控制华为运动健康、保存睡眠图片并上传生成睡眠报告；仅在你解锁手机后执行。</div>
    <label className="flex min-h-12 items-center gap-3 border-b border-gray-50 px-4"><input type="checkbox" checked={consented} onChange={event => onConsent(event.target.checked)} /><span>我同意自动控制应用并上传当天睡眠图片</span></label>
    {(Object.keys(labels) as SleepPermission[]).map(key => <button type="button" key={key} onClick={() => onAuthorize(key)} className="flex h-11 w-full items-center justify-between border-b border-gray-50 px-4"><span>{labels[key]}</span><span>{permissions[key] ? '已允许' : '去授权 ›'}</span></button>)}
    <label className="flex h-12 items-center justify-between px-4"><span>每天 08:40 自动生成报告</span><input aria-label="睡眠自动化" type="checkbox" checked={status.enabled} disabled={!status.enabled && !ready} onChange={event => onToggle(event.target.checked)} /></label>
    {!ready && <div className="px-4 pb-2 text-xs text-amber-600">{!consented ? '请先确认自动化与图片上传同意。' : `尚未授权：${missing.join('、')}`}{status.enabled ? ' 已保留每日执行；补齐后自动恢复。' : ''}</div>}
    <div className="border-t border-gray-50 px-4 py-2 text-xs text-gray-400">下次执行：{status.nextRunAt || '开启后计算'}</div>
    {(status.stage || status.reason) && <div className="px-4 py-2 text-xs text-red-500">失败阶段：{safeText(status.stage)} · {safeText(status.reason)}</div>}
    <div className="flex gap-2 px-4 py-2"><button type="button" onClick={onTest}>立即测试</button><button type="button" onClick={onRetry}>重试</button><button type="button" onClick={onStop}>停止</button></div>
    {history.length > 0 && <div className="border-t border-gray-50 px-4 py-2 text-xs">最近七次运行{history.map((run, index) => <div data-run={index} key={index}>{safeText(run.stage)} · {safeText(run.result)} · {safeText(run.reason)}</div>)}</div>}
    <div className="px-4 py-2 text-xs text-gray-400">自动化失败时，可手动保存睡眠图片后到睡眠分析页上传。</div>
  </section>
}
